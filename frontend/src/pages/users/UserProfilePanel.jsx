import { useState } from 'react'
import { User, Clock, Star, Coins, CalendarDays, X, CheckCircle2, XCircle, RotateCcw, Loader2, Trash2, Unlock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { resetUser, deleteUserChat, grantUserCredits, deleteUserFully } from '@/lib/api'
import { safeFormatDate } from './utils'

function Row({ label, value, badge, mono }) {
  if (value == null || value === '') return null
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      {badge ? (
        <Badge variant="secondary" className="text-xs">{value}</Badge>
      ) : (
        <span className={`text-xs font-medium text-right ${mono ? 'font-mono' : ''}`}>{value}</span>
      )}
    </div>
  )
}

function Panel({ icon: Icon, title, children, testId }) {
  return (
    <div data-testid={testId}>
      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1">
        <Icon className="h-3 w-3" /> {title}
      </p>
      <div className="rounded-lg border bg-muted/30 p-3 space-y-2.5">{children}</div>
    </div>
  )
}

function ActionButton({ state, error, idleLabel, confirmLabel, loadingLabel, doneLabel, onClick, testId, variant = 'destructive', className = '' }) {
  return (
    <Button
      variant={variant}
      size="sm"
      className={`w-full ${className}`}
      onClick={onClick}
      disabled={state === 'loading' || state === 'done'}
      data-testid={testId}
    >
      {state === 'loading' && (
        <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> {loadingLabel}</>
      )}
      {state === 'done' && (
        <><CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> {doneLabel}</>
      )}
      {state === 'confirm' && (
        <>{confirmLabel}</>
      )}
      {state === 'error' && (
        <><XCircle className="h-3.5 w-3.5 mr-1.5" /> {error || 'Retry'}</>
      )}
      {state === 'idle' && idleLabel}
    </Button>
  )
}

export default function UserProfilePanel({ userData, onClose, onUserUpdated, onUserDeleted }) {
  const birth = userData.birth_details || null
  const chart = userData.chart_json || null
  const chartType = chart?.meta?.chart_type
  const credits = userData.credits ?? 0
  const freeReadingUsed = Boolean(userData.free_reading_used)

  const [resetState, setResetState] = useState('idle')
  const [resetError, setResetError] = useState(null)
  const [chatState, setChatState] = useState('idle')
  const [chatError, setChatError] = useState(null)
  const [bypassState, setBypassState] = useState('idle')
  const [bypassError, setBypassError] = useState(null)
  const [bypassBalance, setBypassBalance] = useState(null)
  const [deleteState, setDeleteState] = useState('idle')
  const [deleteError, setDeleteError] = useState(null)

  const armConfirm = (setState) => {
    setState('confirm')
    setTimeout(() => setState((s) => (s === 'confirm' ? 'idle' : s)), 5000)
  }

  const handleReset = async () => {
    if (resetState === 'idle') {
      armConfirm(setResetState)
      return
    }
    if (resetState !== 'confirm') return
    setResetState('loading')
    setResetError(null)
    try {
      await resetUser(userData.phone_number)
      setResetState('done')
      onUserUpdated?.(userData.phone_number)
      setTimeout(() => onClose?.(), 800)
    } catch (err) {
      setResetError(err?.message || 'Reset failed')
      setResetState('error')
      setTimeout(() => setResetState('idle'), 3000)
    }
  }

  const handleDeleteChat = async () => {
    if (chatState === 'idle') {
      armConfirm(setChatState)
      return
    }
    if (chatState !== 'confirm') return
    setChatState('loading')
    setChatError(null)
    try {
      await deleteUserChat(userData.phone_number)
      setChatState('done')
      onUserUpdated?.(userData.phone_number)
      setTimeout(() => onClose?.(), 800)
    } catch (err) {
      setChatError(err?.message || 'Delete failed')
      setChatState('error')
      setTimeout(() => setChatState('idle'), 3000)
    }
  }

  const handleBypass = async () => {
    if (bypassState === 'idle') {
      armConfirm(setBypassState)
      return
    }
    if (bypassState !== 'confirm') return
    setBypassState('loading')
    setBypassError(null)
    try {
      const res = await grantUserCredits(userData.phone_number, 10)
      setBypassBalance(res?.credits ?? null)
      setBypassState('done')
      onUserUpdated?.(userData.phone_number)
      setTimeout(() => setBypassState('idle'), 2500)
    } catch (err) {
      setBypassError(err?.message || 'Bypass failed')
      setBypassState('error')
      setTimeout(() => setBypassState('idle'), 3000)
    }
  }

  const handleDeleteUser = async () => {
    if (deleteState === 'idle') {
      armConfirm(setDeleteState)
      return
    }
    if (deleteState !== 'confirm') return
    setDeleteState('loading')
    setDeleteError(null)
    try {
      await deleteUserFully(userData.phone_number)
      setDeleteState('done')
      onUserDeleted?.(userData.phone_number)
      setTimeout(() => onClose?.(), 600)
    } catch (err) {
      setDeleteError(err?.message || 'Delete failed')
      setDeleteState('error')
      setTimeout(() => setDeleteState('idle'), 3000)
    }
  }

  return (
    <div className="w-80 border-l flex flex-col min-h-0 bg-card overflow-hidden shrink-0" data-testid="user-profile-panel">
      <div className="h-16 px-4 flex items-center justify-between border-b shrink-0">
        <h3 className="text-sm font-bold">User Details</h3>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} data-testid="close-profile-panel-btn">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 overscroll-y-contain p-4 space-y-6">
        <div className="flex flex-col items-center text-center pb-4 border-b">
          <div
            className="h-20 w-20 rounded-full flex items-center justify-center mb-3 border-2"
            style={{
              background: 'linear-gradient(to bottom right, rgb(var(--lavender-rgb) / 0.18), rgb(var(--royal-rgb) / 0.12))',
              borderColor: 'rgb(var(--lavender-rgb) / 0.28)',
            }}
          >
            <User className="h-10 w-10" style={{ color: 'var(--violet)' }} />
          </div>
          <h4 className="text-base font-bold" data-testid="profile-username">{userData.username || 'Unknown User'}</h4>
          <p className="text-xs text-muted-foreground font-mono mt-1">+{userData.phone_number}</p>
          {userData.updated_at && (
            <p className="text-[10px] text-muted-foreground mt-2 flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Last active: {safeFormatDate(userData.updated_at)}
            </p>
          )}
        </div>

        <Panel icon={CalendarDays} title="Birth Details" testId="birth-details-panel">
          {birth ? (
            <>
              <Row label="Date of birth" value={birth.date_of_birth} mono />
              <Row label="Birth time" value={birth.time_of_birth || 'Unknown'} mono />
              <Row label="Place" value={birth.place_name} />
              <Row
                label="Chart type"
                value={chartType === 'surya_kundli' ? 'Surya Kundli (no time)' : chartType === 'full' ? 'Full chart' : null}
                badge
              />
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Not shared yet — flow not completed.</p>
          )}
        </Panel>

        <Panel icon={Star} title="Chart Summary" testId="chart-summary-panel">
          {chart ? (
            <>
              <Row
                label="Lagna"
                value={chart.lagna ? `${chart.lagna.sign_hi} (${chart.lagna.sign_en})` : 'Omitted — no birth time'}
              />
              <Row
                label="Rashi (Moon)"
                value={chart.rashi?.sign_hi ? `${chart.rashi.sign_hi} (${chart.rashi.sign_en})` : null}
              />
              <Row
                label="Nakshatra"
                value={chart.nakshatra?.name ? `${chart.nakshatra.name} — Pada ${chart.nakshatra.pada}` : null}
              />
              <Row label="Ayanamsa" value={chart.meta?.ayanamsa} />
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Chart not computed yet.</p>
          )}
        </Panel>

        <Panel icon={Coins} title="Credits" testId="credits-panel">
          <Row label="Credits balance" value={String(bypassBalance ?? credits)} badge />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">Free reading</span>
            {freeReadingUsed ? (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-[#22b07d]" data-testid="free-reading-used">
                <CheckCircle2 className="h-3 w-3" /> Used
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground" data-testid="free-reading-not-used">
                <XCircle className="h-3 w-3" /> Not used
              </span>
            )}
          </div>
        </Panel>

        <div className="pt-2" data-testid="reset-user-block">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1">
            <RotateCcw className="h-3 w-3" /> Testing tools
          </p>
          <div
            className="rounded-lg border p-3 space-y-2"
            style={{
              borderColor: 'rgba(220, 38, 38, 0.35)',
              background: 'rgba(220, 38, 38, 0.06)',
            }}
          >
            <p className="text-xs text-muted-foreground leading-snug">
              Testing helpers for this WhatsApp number.
            </p>

            <ActionButton
              state={bypassState}
              error={bypassError}
              testId="bypass-paywall-btn"
              variant="default"
              className="bg-emerald-700 hover:bg-emerald-800 text-white"
              idleLabel={<><Unlock className="h-3.5 w-3.5 mr-1.5" /> Bypass paywall (+10 credits)</>}
              confirmLabel={<><Unlock className="h-3.5 w-3.5 mr-1.5" /> Click again to grant 10</>}
              loadingLabel="Granting…"
              doneLabel={bypassBalance != null ? `Done — ${bypassBalance} credits` : 'Credits granted'}
              onClick={handleBypass}
            />

            <ActionButton
              state={resetState}
              error={resetError}
              testId="reset-user-btn"
              idleLabel={<><RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset this user</>}
              confirmLabel={<><RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Click again to confirm</>}
              loadingLabel="Resetting…"
              doneLabel="Reset complete"
              onClick={handleReset}
            />

            <ActionButton
              state={chatState}
              error={chatError}
              testId="delete-chat-btn"
              variant="outline"
              className="border-red-300 text-red-700 hover:bg-red-50"
              idleLabel={<><Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete chat only</>}
              confirmLabel={<><Trash2 className="h-3.5 w-3.5 mr-1.5" /> Click again to confirm</>}
              loadingLabel="Deleting chat…"
              doneLabel="Chat deleted"
              onClick={handleDeleteChat}
            />

            <ActionButton
              state={deleteState}
              error={deleteError}
              testId="delete-user-btn"
              idleLabel={<><Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete user from DB</>}
              confirmLabel={<><Trash2 className="h-3.5 w-3.5 mr-1.5" /> Click again — permanent</>}
              loadingLabel="Deleting user…"
              doneLabel="User deleted"
              onClick={handleDeleteUser}
            />

            <p className="text-[10px] text-muted-foreground leading-tight pt-1">
              <strong>Bypass</strong> adds 10 credits (skip Razorpay).<br />
              <strong>Reset</strong> wipes chart, birth details, language & chat.<br />
              <strong>Delete chat</strong> keeps profile, wipes conversation only.<br />
              <strong>Delete user</strong> removes everything — next WA message is fresh.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
