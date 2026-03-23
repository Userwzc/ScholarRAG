import { MessageSquare, Plus, Trash2, Clock } from "lucide-react"
import { Button } from "../ui/button"
import { cn } from "../../lib/utils"
import type { Conversation } from "../../stores/conversation-store"

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  isOpen: boolean
}

function formatTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return "Just now"
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  
  return new Date(timestamp).toLocaleDateString()
}

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  isOpen,
}: ConversationSidebarProps) {
  if (!isOpen) return null

  return (
    <div className="w-72 border-r border-border/40 bg-secondary/20 backdrop-blur-sm flex flex-col h-full">
      <div className="p-4 border-b border-border/40">
        <Button
          onClick={onCreate}
          className="w-full justify-start gap-2 rounded-xl"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin scrollbar-thumb-muted">
        {conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center px-4">
            <MessageSquare className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <p className="text-sm text-muted-foreground">No conversations yet</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Start a new chat to begin</p>
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group relative flex items-start gap-3 p-3 rounded-xl cursor-pointer transition-all duration-200",
                activeId === conv.id
                  ? "bg-primary/10 border border-primary/20"
                  : "hover:bg-secondary/60 border border-transparent"
              )}
              onClick={() => onSelect(conv.id)}
            >
              <div className={cn(
                "flex-shrink-0 h-8 w-8 rounded-lg flex items-center justify-center",
                activeId === conv.id ? "gradient-primary" : "bg-secondary border border-border/50"
              )}>
                <MessageSquare className={cn(
                  "h-4 w-4",
                  activeId === conv.id ? "text-primary-foreground" : "text-muted-foreground"
                )} />
              </div>
              
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate leading-tight">
                  {conv.title}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <Clock className="h-3 w-3 text-muted-foreground/60" />
                  <span className="text-[10px] text-muted-foreground/60">
                    {formatTime(conv.updatedAt)}
                  </span>
                  <span className="text-[10px] text-muted-foreground/40">
                    {conv.messages.length} messages
                  </span>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(conv.id)
                }}
                className="opacity-0 group-hover:opacity-100 flex-shrink-0 h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>

      {conversations.length > 0 && (
        <div className="p-3 border-t border-border/40">
          <p className="text-[10px] text-muted-foreground/50 text-center">
            {conversations.length} conversation{conversations.length !== 1 ? "s" : ""}
          </p>
        </div>
      )}
    </div>
  )
}
