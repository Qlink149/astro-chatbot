import { Loader2, Send, Check, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export default function AgentFooter({
  isTakenOver,
  isWindowExpired,
  agentInput,
  onAgentInputChange,
  sendingMessage,
  onSendMessage,
}) {
  if (!isTakenOver) {
    return (
      <div className="p-3 bg-[rgb(var(--mist-rgb)/0.5)] border-t text-center shrink-0">
        <p className="text-xs text-muted-foreground font-medium flex items-center justify-center gap-1.5">
          <Check className="h-3.5 w-3.5" /> Read-only — bot is handling this conversation
        </p>
      </div>
    )
  }

  return (
    <div className="bg-card border-t shrink-0">
      {isWindowExpired && (
        <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border-b border-destructive/20">
          <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />
          <p className="text-xs text-destructive">
            WhatsApp 24-hour window has expired — the user must message first before you can reply.
          </p>
        </div>
      )}
      <div className="p-3 flex items-center gap-2">
        <Input
          className="flex-1 h-10"
          placeholder="Type a message as live agent..."
          value={agentInput}
          onChange={e => onAgentInputChange(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSendMessage() } }}
          disabled={sendingMessage || isWindowExpired}
        />
        <Button
          size="icon" className="h-10 w-10 shrink-0 bg-amber-500 hover:bg-amber-600 text-white"
          onClick={onSendMessage}
          disabled={!agentInput.trim() || sendingMessage || isWindowExpired}
        >
          {sendingMessage
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  )
}
