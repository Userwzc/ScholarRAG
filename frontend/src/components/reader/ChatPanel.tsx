import { useState, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import { Send, Loader2, Bot, X, MessageSquare, Sparkles, Minimize2 } from "lucide-react"
import { Button } from "../ui/button"
import { createQueryStream, type SSEEvent } from "../../lib/api"
import { cn } from "../../lib/utils"
import "katex/dist/katex.min.css"

interface ChatPanelProps {
  pdfName: string
  input: string
  onInputChange: (value: string) => void
}

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
}

export function ChatPanel({ pdfName, input, onInputChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
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

  const toggleChat = () => {
    if (!isOpen) {
      setIsOpen(true)
      setIsMinimized(false)
    } else if (isMinimized) {
      setIsMinimized(false)
    } else {
      setIsMinimized(true)
    }
  }

  const closeChat = () => {
    setIsOpen(false)
    setIsMinimized(false)
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {!isOpen ? (
        <button
          onClick={toggleChat}
          className="group relative flex h-14 w-14 items-center justify-center rounded-2xl gradient-primary shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300"
        >
          <div className="absolute inset-0 rounded-2xl bg-primary/50 animate-ping opacity-30" />
          <MessageSquare className="h-6 w-6 text-primary-foreground relative z-10" />
          <span className="absolute -top-1 -right-1 flex h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex rounded-full h-4 w-4 bg-primary text-[10px] font-bold text-primary-foreground items-center justify-center">
              AI
            </span>
          </span>
        </button>
      ) : isMinimized ? (
        <button
          onClick={() => setIsMinimized(false)}
          className="group flex h-14 w-14 items-center justify-center rounded-2xl gradient-primary shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300"
        >
          <MessageSquare className="h-6 w-6 text-primary-foreground" />
          {messages.length > 0 && (
            <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-xs font-bold text-destructive-foreground">
              {messages.length}
            </span>
          )}
        </button>
      ) : (
        <div className="flex flex-col w-96 h-[500px] rounded-2xl shadow-2xl border border-border/50 bg-card/95 backdrop-blur-xl overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-300">
          <div className="flex items-center justify-between p-4 border-b border-border/40 bg-gradient-to-r from-primary/10 to-transparent">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-primary shadow-md">
                <Bot className="h-5 w-5 text-primary-foreground" />
              </div>
              <div>
                <h3 className="font-semibold text-sm">AI Assistant</h3>
                <p className="text-[10px] text-muted-foreground">Ask about this paper</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-lg hover:bg-secondary"
                onClick={() => setIsMinimized(true)}
              >
                <Minimize2 className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-lg hover:bg-destructive/10 hover:text-destructive"
                onClick={closeChat}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-muted">
            {messages.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center py-8">
                <div className="relative mb-4">
                  <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150" />
                  <div className="relative p-4 rounded-2xl bg-secondary/50 border border-border/40">
                    <Sparkles className="h-8 w-8 text-primary" />
                  </div>
                </div>
                <p className="font-medium text-sm mb-1">Hello! I'm your paper assistant</p>
                <p className="text-xs text-muted-foreground max-w-[200px]">
                  Ask me anything about this paper - summaries, explanations, methods, and more
                </p>
                <div className="flex flex-col gap-2 mt-4 w-full">
                  {["Summarize the main findings", "Explain the methodology", "What are the key contributions?"].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => onInputChange(suggestion)}
                      className="text-xs px-3 py-2 rounded-xl bg-secondary/50 border border-border/40 hover:bg-secondary hover:border-primary/30 transition-all text-left"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-2 animate-fade-in",
                  msg.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                {msg.role === "assistant" && (
                  <div className="flex-shrink-0 h-7 w-7 rounded-lg gradient-primary flex items-center justify-center">
                    <Bot className="h-3.5 w-3.5 text-primary-foreground" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[80%] rounded-2xl px-3 py-2 text-sm",
                    msg.role === "user"
                      ? "gradient-primary text-primary-foreground rounded-br-md"
                      : "bg-secondary/70 border border-border/30 rounded-bl-md"
                  )}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <span>{msg.content}</span>
                  )}
                </div>
              </div>
            ))}

            {isLoading && currentAnswer && (
              <div className="flex gap-2 justify-start animate-fade-in">
                <div className="flex-shrink-0 h-7 w-7 rounded-lg gradient-primary flex items-center justify-center">
                  <Bot className="h-3.5 w-3.5 text-primary-foreground" />
                </div>
                <div className="max-w-[80%] rounded-2xl rounded-bl-md px-3 py-2 text-sm bg-secondary/70 border border-border/30">
                  <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1">
                    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {currentAnswer}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}

            {isLoading && !currentAnswer && (
              <div className="flex gap-2 justify-start">
                <div className="flex-shrink-0 h-7 w-7 rounded-lg gradient-primary flex items-center justify-center">
                  <Bot className="h-3.5 w-3.5 text-primary-foreground" />
                </div>
                <div className="flex items-center gap-1.5 px-4 py-3 rounded-2xl bg-secondary/70 border border-border/30">
                  <div className="h-2 w-2 bg-primary/60 rounded-full animate-bounce" />
                  <div className="h-2 w-2 bg-primary/60 rounded-full animate-bounce [animation-delay:0.15s]" />
                  <div className="h-2 w-2 bg-primary/60 rounded-full animate-bounce [animation-delay:0.3s]" />
                </div>
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="p-3 border-t border-border/40 bg-secondary/20">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => onInputChange(e.target.value)}
                placeholder="Ask about this paper..."
                className="flex-1 rounded-xl border-2 border-border/50 bg-background/80 px-4 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-all placeholder:text-muted-foreground/50"
                disabled={isLoading}
              />
              <Button
                type="submit"
                size="icon"
                disabled={isLoading || !input.trim()}
                className="rounded-xl h-10 w-10 flex-shrink-0"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
