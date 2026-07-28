import { useEffect, useMemo, useRef, useState } from 'react'
import { Copy, Info, Loader2, Sparkles, User, MessageSquare, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { getMessageTrace } from '@/lib/api'

function formatMsgTime(ts) {
  if (!ts) return null
  return new Date(ts * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
}

function istDayKey(ts) {
  if (!ts) return null
  return new Date(ts * 1000).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

function formatDateChip(ts) {
  if (!ts) return null
  const day = istDayKey(ts)
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  const yesterdayDate = new Date()
  yesterdayDate.setDate(yesterdayDate.getDate() - 1)
  const yesterday = yesterdayDate.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  if (day === today) return 'Today'
  if (day === yesterday) return 'Yesterday'
  return new Date(ts * 1000).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata',
  })
}

const URL_RE = /(https?:\/\/[^\s]+)/g

function renderBracketHighlight(text, keyPrefix) {
  const parts = text.split(/(\[.*?\])/g)
  return parts.map((part, i) => {
    if (part.startsWith('[') && part.endsWith(']')) {
      return <span key={`${keyPrefix}-b-${i}`} className="font-semibold text-primary">{part}</span>
    }
    return part ? <span key={`${keyPrefix}-t-${i}`}>{part}</span> : null
  })
}

function renderMessageContent(content) {
  if (!content) return null
  const segments = content.split(URL_RE)
  return segments.map((segment, i) => {
    if (segment.startsWith('http://') || segment.startsWith('https://')) {
      return (
        <a
          key={`url-${i}`}
          href={segment}
          target="_blank"
          rel="noreferrer"
          className="break-all underline text-primary hover:opacity-80"
        >
          {segment}
        </a>
      )
    }
    return renderBracketHighlight(segment, `seg-${i}`)
  })
}

function StatusDot({ status }) {
  const color =
    status === 'error'
      ? 'bg-red-500'
      : status === 'warn'
      ? 'bg-amber-400'
      : 'bg-emerald-500'
  return <span className={cn('inline-block h-2 w-2 rounded-full', color)} />
}

function TracePanel({ requestId, onClose }) {
  const [trace, setTrace] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getMessageTrace(requestId)
      .then((doc) => {
        if (!cancelled) setTrace(doc)
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || 'Could not load details')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [requestId])

  const banner =
    trace?.outcome === 'no_products'
      ? "No results were returned for this request."
      : trace?.outcome === 'fallback_used'
      ? 'Exact filters returned nothing — showed closest matches instead.'
      : null

  return (
    <div className="mt-2 rounded-xl border border-[rgb(var(--navy-rgb)/0.12)] bg-[rgb(var(--mist-rgb)/0.45)] p-3 text-left">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          What happened
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            title="Copy request id"
            onClick={() => navigator.clipboard?.writeText(requestId)}
          >
            <Copy className="h-3 w-3" />
            ID
          </button>
          <button type="button" className="text-[10px] text-muted-foreground" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="text-xs text-red-600">{error}</p>
      ) : (
        <>
          {banner && (
            <div className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              {banner}
            </div>
          )}
          <ol className="space-y-2">
            {(trace?.steps || []).map((step) => (
              <li key={`${step.order}-${step.label}`} className="flex gap-2 text-xs">
                <div className="mt-1.5">
                  <StatusDot status={step.status} />
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-foreground">{step.label}</p>
                  <p className="text-muted-foreground break-words">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

function MessageBubble({ msg, outcomeHint }) {
  const [openTrace, setOpenTrace] = useState(false)
  const isBot = msg.role === 'assistant'
  const showDetails = isBot && !!msg.request_id
  const problemDot =
    outcomeHint === 'error'
      ? 'bg-red-500'
      : outcomeHint === 'no_products' || outcomeHint === 'fallback_used'
      ? 'bg-amber-400'
      : null

  return (
    <div className={cn('flex w-full min-w-0', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
      {msg.role === 'assistant' && (
        <div
          className="h-7 w-7 rounded-full flex items-center justify-center shrink-0 mr-2 mt-1 shadow-sm border relative"
          style={{
            background: 'linear-gradient(to bottom right, rgb(var(--violet-rgb) / 0.15), rgb(var(--royal-rgb) / 0.08))',
            borderColor: 'rgb(var(--violet-rgb) / 0.12)',
          }}
        >
          <Sparkles className="h-3.5 w-3.5" style={{ color: 'var(--violet)' }} />
          {problemDot && (
            <span className={cn('absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full ring-2 ring-white', problemDot)} />
          )}
        </div>
      )}

      {msg.role === 'agent' && (
        <div className="h-7 w-7 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0 mr-2 mt-1 shadow-sm border border-amber-500/20">
          <User className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
        </div>
      )}

      <div
        className={cn(
          'relative w-fit max-w-[75%] min-w-0 shrink px-3.5 py-2.5 rounded-2xl shadow-sm text-sm group',
          msg.role === 'user'
            ? 'bg-[#d9fdd3] dark:bg-[#005c4b] text-[#111b21] dark:text-[#e9edef] rounded-tr-none'
            : msg.role === 'agent'
            ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 rounded-tl-none border border-amber-200 dark:border-amber-800'
            : 'bg-white text-[var(--text)] rounded-tl-none border border-[rgb(var(--navy-rgb)/0.1)] shadow-sm'
        )}
      >
        {msg.role === 'agent' && (
          <p className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 mb-1 uppercase tracking-wider">
            Live Agent
          </p>
        )}
        <div className="whitespace-pre-wrap break-words leading-relaxed [overflow-wrap:anywhere]">
          {renderMessageContent(msg.content)}
        </div>
        <div className="mt-1 flex items-center justify-end gap-2">
          {showDetails && (
            <button
              type="button"
              onClick={() => setOpenTrace((v) => !v)}
              className="opacity-70 hover:opacity-100 text-[9px] inline-flex items-center gap-0.5 text-muted-foreground"
            >
              <Info className="h-3 w-3" />
              Details
            </button>
          )}
          <p className="text-[9px] text-right opacity-80 select-none">
            {formatMsgTime(msg.timestamp) ?? '—'}
          </p>
        </div>
        {openTrace && showDetails && (
          <TracePanel requestId={msg.request_id} onClose={() => setOpenTrace(false)} />
        )}
      </div>

      {msg.role === 'user' && (
        <div className="h-7 w-7 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center shrink-0 ml-2 mt-1 border border-border">
          <User className="h-4 w-4 text-zinc-500" />
        </div>
      )}
    </div>
  )
}

export default function ChatMessages({
  activePhone,
  loadingActive,
  chatHistory,
  scrollRef,
  showScrollBottom,
  onScroll,
  onScrollToBottom,
  loadingOlder = false,
  hasMore = false,
  beginningReached = false,
}) {
  const items = useMemo(() => {
    const out = []
    let lastDay = null
    for (let i = 0; i < (chatHistory || []).length; i++) {
      const msg = chatHistory[i]
      const day = istDayKey(msg?.timestamp)
      if (day && day !== lastDay) {
        out.push({ kind: 'date', key: `date-${day}-${i}`, label: formatDateChip(msg.timestamp) })
        lastDay = day
      } else if (!day) {
        // legacy without timestamp — no chip
      }
      out.push({ kind: 'msg', key: msg._id || `msg-${i}-${msg.timestamp || i}`, msg })
    }
    return out
  }, [chatHistory])

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      className="flex-1 min-h-0 basis-0 overflow-y-auto overflow-x-hidden overscroll-y-contain p-4 space-y-4 relative"
    >
      {!activePhone ? (
        <div className="h-full flex flex-col items-center justify-center text-center p-8">
          <div className="h-24 w-24 rounded-full bg-primary/5 flex items-center justify-center mb-6">
            <MessageSquare className="h-10 w-10 text-primary/40" />
          </div>
          <h2 className="text-xl font-medium text-foreground mb-2">Samara</h2>
          <p className="text-sm text-muted-foreground max-w-sm">
            Select a user from the sidebar to view their complete interaction history and AI responses.
          </p>
        </div>
      ) : loadingActive ? (
        <div className="h-full flex items-center justify-center">
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="text-sm">Loading history...</p>
          </div>
        </div>
      ) : chatHistory.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <p className="text-sm text-muted-foreground bg-card/50 px-4 py-2 rounded-full border shadow-sm">
            Conversation history is empty.
          </p>
        </div>
      ) : (
        <div className="relative pb-10 space-y-4 min-w-0">
          {loadingOlder && (
            <div className="flex justify-center py-1">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {beginningReached && !hasMore && (
            <div className="flex justify-center">
              <span className="rounded-full bg-muted px-3 py-1 text-[10px] text-muted-foreground">
                Beginning of conversation
              </span>
            </div>
          )}
          {items.map((item) =>
            item.kind === 'date' ? (
              <div key={item.key} className="flex justify-center sticky top-1 z-10">
                <span className="rounded-full bg-card/90 border px-3 py-1 text-[10px] font-medium text-muted-foreground shadow-sm">
                  {item.label}
                </span>
              </div>
            ) : (
              <MessageBubble key={item.key} msg={item.msg} outcomeHint={item.msg.trace_outcome} />
            )
          )}
        </div>
      )}

      {showScrollBottom && activePhone && (
        <div className="sticky bottom-4 left-0 right-0 flex justify-center z-20 pointer-events-none">
          <Button
            size="icon"
            variant="secondary"
            className="rounded-full shadow-lg h-10 w-10 animate-in fade-in slide-in-from-bottom-2 pointer-events-auto border bg-card/95 hover:bg-card"
            onClick={onScrollToBottom}
            title="Scroll to latest messages"
          >
            <ChevronDown className="h-5 w-5 text-foreground" />
          </Button>
        </div>
      )}
    </div>
  )
}
