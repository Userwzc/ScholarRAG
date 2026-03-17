import { useState, useRef, useEffect, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import "katex/dist/katex.min.css"
import { Search, Loader2, FileText, Table, Sparkles, User, Bot, Send, Trash2, ArrowDownCircle } from "lucide-react"
import { Button } from "../components/ui/button"
import { Card, CardContent } from "../components/ui/card"
import { createQueryStream, type SSEEvent } from "../lib/api"
import { ThoughtProcess, type AgentStep } from "../components/query/ThoughtProcess"
import { cn } from "../lib/utils"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  steps?: AgentStep[]
  sources?: Array<{
    pdf_name: string
    page: number
    type: string
  }>
}

export default function QueryPage() {
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const [currentSteps, setCurrentSteps] = useState<AgentStep[]>([])
  const [currentSources, setCurrentSources] = useState<Array<{ pdf_name: string; page: number; type: string }>>([])
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const [showScrollButton, setShowScrollButton] = useState(false)

  const scrollToBottom = useCallback((force = false) => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = scrollHeight - scrollTop <= clientHeight + 100
    
    if (force || isAtBottom) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: force ? "auto" : "smooth"
      })
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, currentAnswer, currentSteps, scrollToBottom])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    setShowScrollButton(scrollHeight - scrollTop > clientHeight + 300)
  }

  const clearChat = () => {
    setMessages([])
    setCurrentAnswer("")
    setCurrentSteps([])
    setCurrentSources([])
  }

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || isLoading) return

    const userQuestion = input.trim()
    const messageId = Date.now().toString()
    
    setInput("")
    setMessages(prev => [...prev, { id: messageId, role: "user", content: userQuestion }])
    setIsLoading(true)
    setCurrentAnswer("")
    setCurrentSteps([])
    setCurrentSources([])

    let answerBuffer = ""
    const collectedSources: Array<{ pdf_name: string; page: number; type: string }> = []

    const cleanup = createQueryStream(
      userQuestion,
      (event: SSEEvent) => {
        const eventType = event.type as string
        
        if (eventType === "status") {
          const statusText = event.text as string
          setCurrentSteps(prev => [...prev, { type: "thinking", text: statusText }])
        } else if (eventType === "tool_call") {
          const tool = event.tool as string
          const args = event.args as Record<string, unknown>
          const query = args.query as string | undefined
          setCurrentSteps(prev => [...prev, { 
            type: "tool_call", 
            tool,
            text: query ? `Searching papers for: "${query}"` : `Executing ${tool}...`
          }])
        } else if (eventType === "tool_result") {
          const count = event.count as number
          const pages = event.pages as string[]
          const kind = event.kind as string
          setCurrentSteps(prev => [...prev, { 
            type: "tool_result", 
            count, 
            pages,
            text: `Found ${count} result(s)`
          }])
          pages?.forEach((page) => {
            const [pdf_name, pageStr] = page.split(":")
            const pageNum = parseInt(pageStr, 10)
            if (!isNaN(pageNum)) {
              if (!collectedSources.some(s => s.pdf_name === pdf_name && s.page === pageNum)) {
                collectedSources.push({ pdf_name, page: pageNum, type: kind })
                setCurrentSources([...collectedSources])
              }
            }
          })
        } else if (eventType === "agent_observation") {
          setCurrentSteps(prev => [...prev, { type: "observation", text: event.text as string }])
        } else if (eventType === "agent_visual_context") {
          setCurrentSteps(prev => [...prev, { 
            type: "agent_visual_context", 
            text: `Attached ${event.count} visual evidence(s) from ${event.pages?.[0] || 'the paper'}`
          }])
        } else if (eventType === "answer_token") {
          answerBuffer += (event.text as string)
          setCurrentAnswer(answerBuffer)
        } else if (eventType === "answer_started") {
          setCurrentSteps(prev => [...prev, { type: "answer", text: "Synthesizing research answer..." }])
        } else if (eventType === "answer_done") {
          setIsLoading(false)
          setMessages(prev => [
            ...prev,
            { 
              id: (Date.now() + 1).toString(),
              role: "assistant", 
              content: answerBuffer, 
              steps: [...currentSteps],
              sources: [...collectedSources] 
            }
          ])
          setCurrentAnswer("")
          setCurrentSteps([])
          setCurrentSources([])
        }
      },
      (error) => {
        console.error("Query error:", error)
        setIsLoading(false)
        setCurrentSteps(prev => [...prev, { type: "observation", text: "Error: Failed to get response." }])
      }
    )

    return cleanup
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-background">
      {/* Header / Actions */}
      <div className="flex items-center justify-between px-6 py-3 border-b bg-background/50 backdrop-blur-md z-10">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary animate-pulse" />
          <h1 className="font-semibold text-sm tracking-tight">AI Research Assistant</h1>
        </div>
        <Button variant="ghost" size="sm" onClick={clearChat} className="text-muted-foreground hover:text-destructive">
          <Trash2 className="h-4 w-4 mr-2" />
          Clear Thread
        </Button>
      </div>

      {/* Messages Area */}
      <div 
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-8 space-y-8 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent"
      >
        <div className="max-w-3xl mx-auto space-y-8">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full pt-20 text-center space-y-4 opacity-50">
              <div className="p-4 rounded-full bg-muted">
                <Bot className="h-10 w-10" />
              </div>
              <div className="space-y-1">
                <h3 className="font-medium text-lg">Welcome to ScholarRAG</h3>
                <p className="text-sm max-w-sm">
                  Ask me complex questions about your uploaded papers. I can search through text and analyze figures.
                </p>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={cn("flex flex-col", msg.role === "user" ? "items-end" : "items-start")}>
              <div className={cn("flex gap-4 max-w-[90%]", msg.role === "user" && "flex-row-reverse")}>
                <div className={cn(
                  "flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center mt-1",
                  msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted border shadow-sm"
                )}>
                  {msg.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                
                <div className="flex-1 space-y-2">
                  <div className={cn(
                    "p-4 rounded-2xl leading-relaxed",
                    msg.role === "user" ? "bg-primary/10 text-foreground" : "bg-card border shadow-sm"
                  )}>
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {msg.steps && msg.steps.length > 0 && (
                    <ThoughtProcess steps={msg.steps} isLive={false} />
                  )}

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="flex flex-wrap gap-2 px-1">
                      {msg.sources.map((source, sidx) => (
                        <div key={sidx} className="flex items-center gap-1.5 text-[10px] bg-muted px-2 py-1 rounded-full text-muted-foreground border border-transparent hover:border-primary/30 transition-colors">
                          {source.type === "visual_search" ? <Table className="h-2.5 w-2.5" /> : <FileText className="h-2.5 w-2.5" />}
                          {source.pdf_name}.pdf p.{source.page}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Current Live Processing */}
          {isLoading && (
            <div className="flex flex-col items-start">
              <div className="flex gap-4 max-w-[95%]">
                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-muted border shadow-sm flex items-center justify-center mt-1">
                  <Bot className="h-4 w-4" />
                </div>
                <div className="flex-1 space-y-3">
                  <ThoughtProcess steps={currentSteps} isLive={true} />
                  
                  {currentAnswer && (
                    <div className="p-4 rounded-2xl bg-card border shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-500">
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {currentAnswer}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Floating Scroll Down Button */}
      {showScrollButton && (
        <button 
          onClick={() => scrollToBottom(true)}
          className="fixed bottom-32 right-8 p-2 bg-background border rounded-full shadow-lg text-muted-foreground hover:text-foreground hover:scale-110 transition-all z-20"
        >
          <ArrowDownCircle className="h-5 w-5" />
        </button>
      )}

      {/* Fixed Bottom Input Area */}
      <div className="p-6 bg-gradient-to-t from-background via-background to-transparent">
        <form 
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto relative group"
        >
          <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full opacity-0 group-focus-within:opacity-100 transition-opacity pointer-events-none" />
          <div className="relative flex items-center bg-card border shadow-2xl rounded-2xl overflow-hidden focus-within:ring-2 ring-primary/30 transition-all">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSubmit()
                }
              }}
              placeholder="Deep dive into your papers..."
              className="flex-1 bg-transparent border-none focus:ring-0 px-6 py-4 resize-none h-[56px] min-h-[56px] max-h-32 scrollbar-none"
              disabled={isLoading}
              rows={1}
            />
            <div className="pr-4 flex items-center gap-2">
              <Button 
                type="submit" 
                size="icon"
                disabled={isLoading || !input.trim()}
                className={cn(
                  "h-9 w-9 rounded-xl transition-all",
                  input.trim() ? "scale-100 opacity-100" : "scale-90 opacity-50"
                )}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <p className="mt-2 text-[10px] text-center text-muted-foreground italic">
            Pro tip: I can see tables and figures. Try asking "Analyze the results in Figure 3".
          </p>
        </form>
      </div>
    </div>
  )
}
