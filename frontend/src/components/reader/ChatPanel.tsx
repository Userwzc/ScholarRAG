import { useState, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import { Send, Loader2, Bot, X, MessageSquare } from "lucide-react"
import { Button } from "../ui/button"
import { createQueryStream, type SSEEvent } from "../../lib/api"
import { cn } from "../../lib/utils"
import "katex/dist/katex.min.css"

interface ChatPanelProps {
  pdfName: string
  collapsed?: boolean
  onToggle?: () => void
  input: string
  onInputChange: (value: string) => void
}

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
}

export function ChatPanel({ pdfName, collapsed = false, onToggle, input, onInputChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, currentAnswer])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || isLoading) return

    const question = input.trim()
    const messageId = Date.now().toString()

    setMessages((prev) => [...prev, { id: messageId, role: "user", content: question }])
    onInputChange("")
    setIsLoading(true)
    setCurrentAnswer("")

    const enrichedQuestion = `关于论文《${pdfName}》：${question}`
    let answerBuffer = ""

    createQueryStream(
      enrichedQuestion,
      (event: SSEEvent) => {
        const eventType = event.type as string
        if (eventType === "answer_token") {
          answerBuffer += event.text as string
          setCurrentAnswer(answerBuffer)
        } else if (eventType === "answer_done") {
          setIsLoading(false)
          if (answerBuffer) {
            setMessages((prev) => [
              ...prev,
              { id: (Date.now() + 1).toString(), role: "assistant", content: answerBuffer },
            ])
          }
          setCurrentAnswer("")
        }
      },
      (error) => {
        console.error("Chat error:", error)
        setIsLoading(false)
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: "assistant", content: "Error: Failed to get response." },
        ])
      }
    )
  }

  if (collapsed) {
    return (
      <button
        onClick={onToggle}
        className="w-12 border-l bg-muted/30 flex items-center justify-center hover:bg-muted transition-colors"
      >
        <MessageSquare className="h-5 w-5 text-muted-foreground" />
      </button>
    )
  }

  return (
    <div className="w-80 border-l bg-background flex flex-col h-full">
      <div className="p-3 border-b flex items-center justify-between">
        <h2 className="font-semibold text-sm">AI Assistant</h2>
        {onToggle && (
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onToggle}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-4">
        {messages.length === 0 && !isLoading && (
          <div className="text-center text-muted-foreground text-sm py-8">
            <Bot className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p>Ask me about this paper...</p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={cn("flex gap-2", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
              )}
            >
              {msg.role === "assistant" ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}

        {isLoading && currentAnswer && (
          <div className="flex gap-2 justify-start">
            <div className="max-w-[85%] rounded-lg px-3 py-2 text-sm bg-muted">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {currentAnswer}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-3 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="Ask about this paper..."
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            disabled={isLoading}
          />
          <Button type="submit" size="icon" disabled={isLoading || !input.trim()}>
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </form>
    </div>
  )
}
