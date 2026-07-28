import { Search, User, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { safeFormatDate, isWindowExpired } from './utils'

export default function ConversationSidebar({
  users,
  loadingUsers,
  activePhone,
  search,
  onSearchChange,
  page,
  totalPages,
  total,
  onPageChange,
  onSelectUser,
  agentFilter,
  onFilterChange,
  className,
}) {
  return (
    <div className={cn('w-full lg:w-80 shrink-0 min-h-0 overflow-hidden border-r flex flex-col bg-white/80', className)}>
      <div className="p-4 border-b bg-white shrink-0">
        <h1 className="text-xl font-bold tracking-tight mb-4 font-display text-foreground">Conversations</h1>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search users..."
            className="pl-9 h-9 bg-white border border-[rgb(var(--navy-rgb)/0.12)] focus-visible:bg-white focus-visible:border-primary placeholder:text-muted-foreground"
            value={search}
            onChange={e => onSearchChange(e.target.value)}
          />
        </div>
        <div className="flex gap-1.5 mt-3">
          <button
            onClick={() => onFilterChange(false)}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors border ${
              !agentFilter
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-white text-muted-foreground border-[rgb(var(--navy-rgb)/0.12)] hover:text-foreground hover:border-[rgb(var(--violet-rgb)/0.25)]'
            }`}
          >
            All
          </button>
          <button
            onClick={() => onFilterChange(true)}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors border ${
              agentFilter
                ? 'bg-[#f59e0b] text-white border-[#f59e0b]'
                : 'bg-white text-muted-foreground border-[rgb(var(--navy-rgb)/0.12)] hover:text-foreground hover:border-[rgb(var(--violet-rgb)/0.25)]'
            }`}
          >
            Agent Requested
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 basis-0 overflow-y-auto overscroll-y-contain">
        {loadingUsers ? (
          <div className="p-4 flex justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : users.length === 0 ? (
          <div className="p-6 text-center text-muted-foreground text-sm">
            No users found.
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {users.map((user) => (
              <div
                key={user._id || user.phone_number}
                className={`flex items-start gap-3 p-4 cursor-pointer transition-colors relative overflow-hidden
                  ${activePhone === user.phone_number
                    ? 'bg-[rgb(var(--violet-rgb)/0.08)]'
                    : user.live_agent_required
                      ? 'bg-yellow-50 dark:bg-yellow-950/20 hover:bg-yellow-100/70 dark:hover:bg-yellow-950/30'
                      : 'hover:bg-muted/50'
                  }`}
                onClick={() => onSelectUser(user.phone_number)}
              >
                {activePhone === user.phone_number && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />
                )}
                <div className={`h-10 w-10 rounded-full flex items-center justify-center shrink-0 border ${
                  user.live_agent_required
                    ? 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-300 dark:border-yellow-700'
                    : isWindowExpired(user.updated_at)
                      ? 'bg-muted border-border'
                      : 'border-[rgb(var(--violet-rgb)/0.18)] bg-[rgb(var(--violet-rgb)/0.08)]'
                }`}>
                  <User className={`h-5 w-5 ${
                    user.live_agent_required
                      ? 'text-yellow-500'
                      : isWindowExpired(user.updated_at)
                        ? 'text-muted-foreground'
                        : 'text-[var(--violet)]'
                  }`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <p className="text-sm font-semibold truncate text-foreground">
                      {user.username || 'Unknown User'}
                    </p>
                    <p className="text-[10px] text-muted-foreground shrink-0 uppercase tracking-widest font-medium">
                      {safeFormatDate(user.updated_at)}
                    </p>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-muted-foreground truncate font-mono">
                      +{user.phone_number}
                    </p>
                    <div className="flex items-center gap-1 shrink-0">
                      {user.live_agent_required && (
                        <span className="rounded-full border border-yellow-300 bg-yellow-50 dark:bg-yellow-950/30 dark:border-yellow-700 px-1.5 py-0 text-[9px] font-medium text-yellow-600 dark:text-yellow-400">
                          Agent Req
                        </span>
                      )}
                      {isWindowExpired(user.updated_at) ? (
                        <span className="rounded-full border border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-1.5 py-0 text-[9px] font-medium text-red-500 dark:text-red-400">
                          Closed
                        </span>
                      ) : (
                        <span
                          className="rounded-full px-1.5 py-0 text-[9px] font-medium"
                          style={{
                            border: '1px solid rgb(var(--violet-rgb) / 0.18)',
                            background: 'rgb(var(--violet-rgb) / 0.08)',
                            color: 'var(--violet)',
                          }}
                        >
                          Open
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t bg-white p-2.5 shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground font-medium">
            {total} user{total !== 1 ? 's' : ''}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost" size="icon" className="h-7 w-7"
              onClick={() => onPageChange(page - 1)}
              disabled={page === 1 || loadingUsers}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <span className="text-xs text-muted-foreground font-medium min-w-12 text-center">
              {page}/{totalPages}
            </span>
            <Button
              variant="ghost" size="icon" className="h-7 w-7"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages || loadingUsers}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
