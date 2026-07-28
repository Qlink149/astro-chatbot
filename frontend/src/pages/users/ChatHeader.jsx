import { Loader2, Bot, User, Phone, Package, Clock, CheckCircle2, UserCheck, ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function ChatHeader({
  activeUserData,
  isTakenOver,
  isWindowExpired,
  releasing,
  takingOver,
  resolvingAgent,
  showProfile,
  onTakeover,
  onRelease,
  onResolveAgent,
  onToggleProfile,
  onBack,
}) {
  if (!activeUserData) {
    return (
      <div className="h-16 border-b bg-card/95 backdrop-blur z-10 shrink-0 flex items-center px-4">
        <h2 className="text-sm font-semibold text-muted-foreground">Select a chat to view</h2>
      </div>
    )
  }

  return (
    <div className="h-16 px-4 py-3 flex items-center justify-between gap-2 border-b bg-card/95 backdrop-blur shadow-sm z-10 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        {onBack && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 lg:hidden"
            onClick={onBack}
            title="Back to conversations"
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
        )}
        <div
          className="h-10 w-10 rounded-full flex items-center justify-center shrink-0 border"
          style={{
            background: 'rgb(var(--violet-rgb) / 0.08)',
            borderColor: 'rgb(var(--violet-rgb) / 0.18)',
          }}
        >
          <User className="h-5 w-5" style={{ color: 'var(--violet)' }} />
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-bold truncate">{activeUserData.username || 'Unknown User'}</h2>
          <p className="text-xs text-muted-foreground font-mono flex items-center gap-1 truncate">
            <Phone className="h-3 w-3 shrink-0" /> +{activeUserData.phone_number}
          </p>
        </div>

        {isWindowExpired ? (
          <span className="hidden sm:inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-2 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400 shrink-0">
            <Clock className="h-3 w-3" /> Window Closed
          </span>
        ) : (
          <span
            className="hidden sm:inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0"
            style={{
              border: '1px solid rgb(var(--violet-rgb) / 0.18)',
              background: 'rgb(var(--violet-rgb) / 0.08)',
              color: 'var(--violet)',
            }}
          >
            <CheckCircle2 className="h-3 w-3" /> Window Open
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-1 shrink-0">
        {activeUserData.live_agent_required && (
          <Button
            size="sm" variant="outline"
            className="h-8 text-xs border-yellow-400 text-yellow-600 hover:bg-yellow-50 dark:hover:bg-yellow-950/30"
            onClick={onResolveAgent} disabled={resolvingAgent}
          >
            {resolvingAgent
              ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              : <UserCheck className="h-3.5 w-3.5 mr-1" />}
            Resolve Agent
          </Button>
        )}
        {isTakenOver ? (
          <Button
            size="sm" variant="outline"
            className="h-8 text-xs border-amber-500 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30"
            onClick={onRelease} disabled={releasing}
          >
            {releasing
              ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              : <Bot className="h-3.5 w-3.5 mr-1" />}
            Hand Back to Bot
          </Button>
        ) : (
          <Button
            size="sm" variant="outline"
            className="h-8 text-xs font-semibold border-[rgb(var(--violet-rgb)/0.25)] text-[var(--violet)] hover:bg-[rgb(var(--violet-rgb)/0.08)]"
            onClick={onTakeover} disabled={takingOver || isWindowExpired}
            title={isWindowExpired ? '24-hour messaging window has closed' : undefined}
          >
            {takingOver
              ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              : <User className="h-3.5 w-3.5 mr-1" />}
            Take Over
          </Button>
        )}

        <Button
          variant="ghost" size="icon"
          className={`h-8 w-8 ${showProfile ? 'text-primary bg-primary/10' : 'text-muted-foreground'}`}
          onClick={onToggleProfile}
          title="User Profile"
        >
          <Package className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
