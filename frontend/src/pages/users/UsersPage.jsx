import { useState, useEffect, useRef, useCallback } from 'react'
import notificationSound from '@/assets/notification_sound.mp3'
import { useSearchParams } from 'react-router-dom'
import { listUsers, searchUsers, getUserByPhone, getChatHistory, takeoverConversation, sendAgentMessage, releaseConversation, resolveAgentRequest, getToken } from '@/lib/api'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { isWindowExpired as checkWindowExpired } from './utils'
import ConversationSidebar from './ConversationSidebar'
import ChatHeader from './ChatHeader'
import ChatMessages from './ChatMessages'
import AgentFooter from './AgentFooter'
import UserProfilePanel from './UserProfilePanel'
import { Sheet, SheetContent } from '@/components/ui/sheet'

function useMediaQuery(query) {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    setMatches(mql.matches)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

export default function UsersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('search') || ''
  const page = parseInt(searchParams.get('page') || '1', 10)
  const limit = 20

  const setSearch = (val) => setSearchParams(prev => { const p = new URLSearchParams(prev); val ? p.set('search', val) : p.delete('search'); p.set('page', '1'); return p }, { replace: true })
  const setPage = (val) => setSearchParams(prev => { const p = new URLSearchParams(prev); p.set('page', String(val)); return p }, { replace: true })

  // Debounce search so the API isn't hit on every keystroke
  const [debouncedSearch, setDebouncedSearch] = useState(search)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(t)
  }, [search])

  // User list state
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(true)
  const [total, setTotal] = useState(0)
  const [agentFilter, setAgentFilter] = useState(false)

  // Active conversation state — driven by ?phone= param
  const [activePhone, setActivePhone] = useState(searchParams.get('phone') || null)
  const [userMap, setUserMap] = useState({})
  const [loadingActive, setLoadingActive] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [showScrollBottom, setShowScrollBottom] = useState(false)

  // Takeover state — keyed by phone so switching chats doesn't reset it
  const [takeoverMap, setTakeoverMap] = useState({}) // { [phone]: { active, takenBy } }
  const [agentInput, setAgentInput] = useState('')
  const [sendingMessage, setSendingMessage] = useState(false)
  const [takingOver, setTakingOver] = useState(false)
  const [releasing, setReleasing] = useState(false)
  const [resolvingAgent, setResolvingAgent] = useState(false)

  const isTakenOver = takeoverMap[activePhone]?.active ?? false
  const takeoverBy = takeoverMap[activePhone]?.takenBy ?? null

  const setTakeover = useCallback((phone, active, takenBy = null) => {
    setTakeoverMap(prev => ({ ...prev, [phone]: { active, takenBy } }))
  }, [])

  const chatScrollRef = useRef(null)
  const sseRef = useRef(null)
  const prevAgentPhonesRef = useRef(null)
  const loadingOlderRef = useRef(false)
  const scrollLoadDebounceRef = useRef(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [beginningReached, setBeginningReached] = useState(false)

  const totalPages = Math.ceil(total / limit) || 1

  // Play a chime when a new "agent required" lead appears in the list
  useEffect(() => {
    const current = new Set(users.filter(u => u.live_agent_required).map(u => u.phone_number))
    if (prevAgentPhonesRef.current !== null) {
      const hasNew = [...current].some(p => !prevAgentPhonesRef.current.has(p))
      if (hasNew) {
        try {
          new Audio(notificationSound).play()
        } catch {}
      }
    }
    prevAgentPhonesRef.current = current
  }, [users])

  const scrollToBottom = useCallback(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
      setShowScrollBottom(false)
    }
  }, [])

  const mergeHistoryUnique = (older, newer) => {
    const seen = new Set()
    const out = []
    for (const msg of [...older, ...newer]) {
      const key = msg._id || `${msg.role}|${msg.timestamp}|${msg.content}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push(msg)
    }
    return out
  }

  const loadOlderMessages = useCallback(async () => {
    if (!activePhone || loadingOlderRef.current || !hasMoreHistory) return
    const history = userMap[activePhone]?.chat_history || []
    const first = history[0]
    if (!first?.timestamp) {
      setHasMoreHistory(false)
      setBeginningReached(true)
      return
    }
    loadingOlderRef.current = true
    setLoadingOlder(true)
    const el = chatScrollRef.current
    const prevHeight = el?.scrollHeight || 0
    try {
      const page = await getChatHistory(activePhone, {
        before: first.timestamp,
        beforeId: first._id,
        limit: 50,
      })
      const older = page?.messages || page?.chat_history || []
      setHasMoreHistory(Boolean(page?.has_more))
      if (!page?.has_more) setBeginningReached(true)
      if (older.length) {
        setUserMap(prev => {
          const existing = prev[activePhone] || {}
          return {
            ...prev,
            [activePhone]: {
              ...existing,
              chat_history: mergeHistoryUnique(older, existing.chat_history || []),
            },
          }
        })
        requestAnimationFrame(() => {
          if (el) el.scrollTop = el.scrollHeight - prevHeight
        })
      }
    } catch {
      // ignore — user can retry by scrolling again
    } finally {
      loadingOlderRef.current = false
      setLoadingOlder(false)
    }
  }, [activePhone, hasMoreHistory, userMap])

  const handleChatScroll = useCallback((e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight >= 100)
    if (scrollTop <= 40) {
      if (scrollLoadDebounceRef.current) return
      scrollLoadDebounceRef.current = setTimeout(() => {
        scrollLoadDebounceRef.current = null
        loadOlderMessages()
      }, 250)
    }
  }, [loadOlderMessages])

  useEffect(() => {
    setHasMoreHistory(false)
    setBeginningReached(false)
    loadingOlderRef.current = false
  }, [activePhone])

  // Fetch user list + auto-refresh in the background (SSE handles real-time
  // updates for the active conversation; this poll is just a safety net for
  // the sidebar. Keeping it slow so the UI doesn't visibly refresh.)
  const fetchUsers = useCallback(() => {
    const req = debouncedSearch
      ? searchUsers(debouncedSearch).then(res => ({ users: res?.results || [], total: res?.count ?? 0 }))
      : listUsers(page, limit, agentFilter).then(res => ({ users: res.users, total: res.total }))
    req
      .then(({ users, total }) => { setUsers(users); setTotal(total) })
      .catch(() => {})
      .finally(() => setLoadingUsers(false))
  }, [page, limit, agentFilter, debouncedSearch])

  const handleFilterChange = (val) => {
    setAgentFilter(val)
    setPage(1)
  }

  useEffect(() => {
    setLoadingUsers(true)
    fetchUsers()
    const interval = setInterval(fetchUsers, 30000)
    return () => clearInterval(interval)
  }, [fetchUsers])

  // Silent background fallback for the active conversation. SSE below drives
  // real-time updates; this poll is intentionally slow (30s) so the panel
  // does not visibly refresh.
  useEffect(() => {
    if (!activePhone) return
    const interval = setInterval(() => {
      Promise.all([
        getUserByPhone(activePhone),
        getChatHistory(activePhone, { limit: 50 }),
      ])
        .then(([data, historyPage]) => {
          const serverHistory = historyPage?.messages || historyPage?.chat_history || data.chat_history || []
          setHasMoreHistory(Boolean(historyPage?.has_more))
          setUserMap(prev => {
            const existing = prev[activePhone] || {}
            const merged = mergeHistoryUnique(existing.chat_history || [], serverHistory)
            merged.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
            return {
              ...prev,
              [activePhone]: {
                ...existing,
                ...data,
                chat_history: merged,
              },
            }
          })
        })
        .catch(() => {})
    }, 30000)
    return () => clearInterval(interval)
  }, [activePhone])

  // SSE connection + initial history fetch for active conversation
  useEffect(() => {
    if (!activePhone) return

    const fetchUser = () => {
      setLoadingActive(true)
      Promise.all([
        getUserByPhone(activePhone),
        getChatHistory(activePhone, { limit: 50 }),
      ])
        .then(([data, historyPage]) => {
          const messages = historyPage?.messages || historyPage?.chat_history || data.chat_history || []
          setHasMoreHistory(Boolean(historyPage?.has_more))
          if (!historyPage?.has_more) setBeginningReached(true)
          setUserMap(prev => ({
            ...prev,
            [activePhone]: {
              ...(prev[activePhone] || {}),
              ...data,
              chat_history: messages,
            },
          }))
          setTakeover(activePhone, data.human_takeover?.active ?? false, data.human_takeover?.taken_by ?? null)
        })
        .catch(() => {})
        .finally(() => setLoadingActive(false))
    }
    fetchUser()

    const token = getToken()
    const baseUrl = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL || '')
    const es = new EventSource(
      `${baseUrl}/system/conversation/${activePhone}/stream${token ? `?token=${token}` : ''}`
    )
    sseRef.current = es

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        switch (event.type) {
          case 'connected':
            break

          // User replies (only pushed when takeover is active)
          case 'user_message':
            setUserMap(prev => {
              const user = prev[activePhone] || {}
              return { ...prev, [activePhone]: { ...user, chat_history: [...(user.chat_history || []), { role: 'user', content: event.content, timestamp: event.timestamp ?? Date.now() / 1000 }] } }
            })
            break

          // Agent messages + takeover/release system messages
          case 'agent_message':
            setUserMap(prev => {
              const user = prev[activePhone] || {}
              return { ...prev, [activePhone]: { ...user, chat_history: [...(user.chat_history || []), { role: 'agent', content: event.content, timestamp: event.timestamp ?? Date.now() / 1000 }] } }
            })
            break

          case 'takeover':
            setTakeover(activePhone, true)
            fetchUser()
            break

          case 'release':
            setTakeover(activePhone, false)
            toast.success('Agent handed back to bot')
            fetchUser()
            break
        }
      } catch {}
    }

    es.onerror = () => {
      fetchUser()
      es.close()
    }

    return () => {
      es.close()
      sseRef.current = null
    }
  }, [activePhone])

  // Scroll to bottom on conversation switch or initial load
  useEffect(() => {
    scrollToBottom()
  }, [activePhone, loadingActive, scrollToBottom])

  // Auto-scroll on new messages if already at bottom
  useEffect(() => {
    if (!showScrollBottom) scrollToBottom()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userMap, scrollToBottom])

  const handleSelectUser = useCallback(async (phone) => {
    setActivePhone(phone)
    setAgentInput('')
    setSearchParams(prev => { const p = new URLSearchParams(prev); p.set('phone', phone); return p }, { replace: true })
    if (!userMap[phone]) {
      setLoadingActive(true)
      try {
        const data = await getUserByPhone(phone)
        setUserMap(prev => ({ ...prev, [phone]: data }))
      } catch {
      } finally {
        setLoadingActive(false)
      }
    }
  }, [userMap, setSearchParams])

  // Open chat when ?phone= is present in URL (e.g. direct link or page refresh)
  useEffect(() => {
    const phone = searchParams.get('phone')
    if (phone && phone !== activePhone) {
      setActivePhone(phone)
      if (!userMap[phone]) {
        setLoadingActive(true)
        getUserByPhone(phone)
          .then(data => setUserMap(prev => ({ ...prev, [phone]: data })))
          .catch(() => {})
          .finally(() => setLoadingActive(false))
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Derived state
  const activeUserData = activePhone ? userMap[activePhone] : null
  const displayUsers = [...users]
  if (activeUserData && !displayUsers.find(u => u.phone_number === activePhone)) {
    displayUsers.unshift(activeUserData)
  }
  // Server handles filtering; just pin the active user on top if not in list
  const filteredUsers = displayUsers

  const isWindowExpired = checkWindowExpired(activeUserData?.updated_at)

  // Takeover / release / send handlers
  const handleTakeover = async () => {
    const agentName = localStorage.getItem('agent_username') || 'Agent'
    setTakingOver(true)
    try {
      await takeoverConversation(activePhone, agentName)
      setTakeover(activePhone, true, agentName)
      toast.success('You have taken over the conversation')
    } catch (err) {
      toast.error(err.message || 'Failed to take over')
    } finally {
      setTakingOver(false)
    }
  }

  const handleRelease = async () => {
    setReleasing(true)
    try {
      await releaseConversation(activePhone)
      setTakeover(activePhone, false)
    } catch (err) {
      toast.error(err.message || 'Failed to release')
    } finally {
      setReleasing(false)
    }
  }

  const handleResolveAgent = async () => {
    setResolvingAgent(true)
    try {
      await resolveAgentRequest(activePhone)
      setUserMap(prev => ({
        ...prev,
        [activePhone]: { ...(prev[activePhone] || {}), live_agent_required: false }
      }))
      fetchUsers()
      getUserByPhone(activePhone)
        .then(data => setUserMap(prev => ({ ...prev, [activePhone]: data })))
        .catch(() => {})
      toast.success('Agent request resolved')
    } catch (err) {
      toast.error(err.message || 'Failed to resolve agent request')
    } finally {
      setResolvingAgent(false)
    }
  }

  const handleSendMessage = async () => {
    const msg = agentInput.trim()
    if (!msg || sendingMessage) return
    setSendingMessage(true)
    setAgentInput('')
    try {
      await sendAgentMessage(activePhone, msg)
    } catch (err) {
      setAgentInput(msg)
      toast.error(err.message || 'Failed to send message')
    } finally {
      setSendingMessage(false)
    }
  }

  const isXl = useMediaQuery('(min-width: 1280px)')

  const handleBackToList = useCallback(() => {
    setActivePhone(null)
    setShowProfile(false)
    setSearchParams(prev => {
      const p = new URLSearchParams(prev)
      p.delete('phone')
      return p
    }, { replace: true })
  }, [setSearchParams])

  return (
    <div className="flex flex-1 flex-col min-h-0 basis-0 overflow-hidden">
      <div className="flex flex-1 min-h-0 basis-0 overflow-hidden bg-card md:rounded-xl border border-border shadow-sm">

        <ConversationSidebar
          className={activePhone ? 'hidden lg:flex' : 'flex'}
          users={filteredUsers}
          loadingUsers={loadingUsers}
          activePhone={activePhone}
          search={search}
          onSearchChange={setSearch}
          page={page}
          totalPages={totalPages}
          total={total}
          onPageChange={setPage}
          onSelectUser={handleSelectUser}
          agentFilter={agentFilter}
          onFilterChange={handleFilterChange}
        />

        {/* Chat pane */}
        <div className={cn(
          "flex-1 min-w-0 min-h-0 basis-0 flex flex-col overflow-hidden bg-[url('https://ik.imagekit.io/0rf6agnve/one%20reside/chat-bg-light.png')] dark:bg-[url('https://ik.imagekit.io/0rf6agnve/one%20reside/chat-bg-dark.png')] bg-cover bg-center",
          !activePhone && 'hidden lg:flex'
        )}>

          <ChatHeader
            activeUserData={activeUserData}
            isTakenOver={isTakenOver}
            isWindowExpired={isWindowExpired}
            releasing={releasing}
            takingOver={takingOver}
            resolvingAgent={resolvingAgent}
            showProfile={showProfile}
            onTakeover={handleTakeover}
            onRelease={handleRelease}
            onResolveAgent={handleResolveAgent}
            onToggleProfile={() => setShowProfile(p => !p)}
            onBack={handleBackToList}
          />

          {/* Live Agent Banner */}
          {activeUserData && isTakenOver && (
            <div className="bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 px-4 py-2 flex items-center gap-2 shrink-0">
              <div className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-xs text-amber-700 dark:text-amber-400 font-medium">
                Live agent mode — {takeoverBy || 'Agent'} is handling this conversation
              </span>
            </div>
          )}

          <ChatMessages
            activePhone={activePhone}
            loadingActive={loadingActive}
            chatHistory={activeUserData?.chat_history || []}
            scrollRef={chatScrollRef}
            showScrollBottom={showScrollBottom}
            onScroll={handleChatScroll}
            onScrollToBottom={scrollToBottom}
            loadingOlder={loadingOlder}
            hasMore={hasMoreHistory}
            beginningReached={beginningReached}
          />

          {activePhone && (
            <AgentFooter
              isTakenOver={isTakenOver}
              isWindowExpired={isWindowExpired}
              agentInput={agentInput}
              onAgentInputChange={setAgentInput}
              sendingMessage={sendingMessage}
              onSendMessage={handleSendMessage}
            />
          )}
        </div>

        {showProfile && activeUserData && isXl && (
          <UserProfilePanel
            userData={activeUserData}
            onClose={() => setShowProfile(false)}
          />
        )}

      </div>

      <Sheet open={showProfile && !!activeUserData && !isXl} onOpenChange={setShowProfile}>
        <SheetContent side="right" className="w-80 p-0 sm:max-w-80 [&>button]:hidden">
          {activeUserData && (
            <UserProfilePanel
              userData={activeUserData}
              onClose={() => setShowProfile(false)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
