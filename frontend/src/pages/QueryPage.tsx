import { useState, useRef, useEffect, useCallback, useMemo } from "react"
import { Link } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkMath from "remark-math"
import rehypeKatex from "rehype-katex"
import "katex/dist/katex.min.css"
import { 
  Loader2, FileText, Table, Sparkles, User, Bot, Send, 
  ArrowDownCircle, PanelLeftClose, PanelLeft, MessageSquarePlus
} from "lucide-react"
import { Button } from "../components/ui/button"
import { createQueryStream, type SSEEvent, type MessageHistory, type Source } from "../lib/api"
import { ThoughtProcess, type AgentStep } from "../components/query/ThoughtProcess"
import { ConversationSidebar } from "../components/query/ConversationSidebar"
import { useConversationStore, type Message } from "../stores/conversation-store"
import { cn } from "../lib/utils"

const MAX_HISTORY_MESSAGES = 10

export default function QueryPage() {
  const {
    conversations,
    activeConversationId,
    sidebarOpen,
    createConversation,
    deleteConversation,
    setActiveConversation,
    loadConversationMessages,
    addMessage,
    toggleSidebar,
    syncWithBackend,
  } = useConversationStore()

  // 启动时同步后端数据
  useEffect(() => {
    syncWithBackend()
  }, [syncWithBackend])

  // 切换对话时加载消息
  useEffect(() => {
    if (activeConversationId) {
      loadConversationMessages(activeConversationId)
    }
  }, [activeConversationId, loadConversationMessages])

  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const [currentSteps, setCurrentSteps] = useState<AgentStep[]>([])
  const [currentSources, setCurrentSources] = useState<Source[]>([])
  
  const scrollRef = useRef<HTMLDivElement>(null)
  const [showScrollButton, setShowScrollButton] = useState(false)

  const activeConversation = conversations.find((c) => c.id === activeConversationId)
  const messages = useMemo(() => activeConversation?.messages || [], [activeConversation?.messages])

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
  }, [messages, currentAnswer, currentSteps, currentSources, scrollToBottom])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    setShowScrollButton(scrollHeight - scrollTop > clientHeight + 300)
  }

  const handleNewChat = async () => {
    await createConversation()
    setCurrentAnswer("")
    setCurrentSteps([])
    setCurrentSources([])
  }

  const handleSelectConversation = (id: string) => {
    setActiveConversation(id)
    setCurrentAnswer("")
    setCurrentSteps([])
    setCurrentSources([])
  }

  // 构建历史消息（最近 10 条）
  const buildHistory = useCallback((): MessageHistory[] => {
    if (!activeConversation || messages.length === 0) return []
    
    const recentMessages = messages.slice(-MAX_HISTORY_MESSAGES)
    return recentMessages.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }))
  }, [activeConversation, messages])

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!input.trim() || isLoading) return

    let conversationId = activeConversationId

    if (!conversationId) {
      conversationId = await createConversation()
    }

    const userQuestion = input.trim()
    const messageId = Date.now().toString()
    
    setInput("")
    
    const userMessage: Message = {
      id: messageId,
      role: "user",
      content: userQuestion,
      createdAt: Date.now(),
    }
    // 用户消息不需要 await，先更新 UI
    addMessage(conversationId, userMessage)
    
    setIsLoading(true)
    setCurrentAnswer("")
    setCurrentSteps([])
    setCurrentSources([])

    let answerBuffer = ""

    const history = buildHistory()

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
          setCurrentSteps(prev => [...prev, { 
            type: "tool_result", 
            count, 
            text: `Found ${count} result(s)`
          }])
        } else if (eventType === "agent_observation") {
          setCurrentSteps(prev => [...prev, { type: "observation", text: event.text as string }])
        } else if (eventType === "agent_visual_context") {
          const pages = event.pages as string[] | undefined
          setCurrentSteps(prev => [...prev, { 
            type: "agent_visual_context", 
            text: `Attached ${event.count as number} visual evidence(s) from ${pages?.[0] || 'the paper'}`
          }])
        } else if (eventType === "answer_token") {
          answerBuffer += (event.text as string)
          setCurrentAnswer(answerBuffer)
        } else if (eventType === "answer_started") {
          setCurrentSteps(prev => [...prev, { type: "answer", text: "Synthesizing research answer..." }])
        } else if (eventType === "answer_done") {
          setIsLoading(false)
          
          const finalSources: Source[] = (event.sources as Source[] | undefined) || []
          
          const assistantMessage: Message = {
            id: (Date.now() + 1).toString(),
            role: "assistant",
            content: answerBuffer,
            steps: [...currentSteps],
            sources: finalSources,
            createdAt: Date.now(),
          }
          addMessage(conversationId, assistantMessage)
          
          setCurrentAnswer("")
          setCurrentSteps([])
          setCurrentSources([])
        }
      },
      (error) => {
        console.error("Query error:", error)
        setIsLoading(false)
        setCurrentSteps(prev => [...prev, { type: "observation", text: "Error: Failed to get response." }])
      },
      conversationId,
      history,
    )

    return cleanup
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeConversationId}
        onSelect={handleSelectConversation}
        onCreate={handleNewChat}
        onDelete={deleteConversation}
        isOpen={sidebarOpen}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between px-6 py-3 border-b border-border/40 glass">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="rounded-xl h-8 w-8"
            >
              {sidebarOpen ? (
                <PanelLeftClose className="h-4 w-4" />
              ) : (
                <PanelLeft className="h-4 w-4" />
              )}
            </Button>
            <div className="flex h-8 w-8 items-center justify-center rounded-xl gradient-primary">
              <Sparkles className="h-4 w-4 text-primary-foreground animate-pulse-soft" />
            </div>
            <div>
              <h1 className="font-semibold text-sm tracking-tight">
                {activeConversation?.title || "AI Research Assistant"}
              </h1>
              <p className="text-[10px] text-muted-foreground">Powered by multimodal RAG</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleNewChat}
              className="text-muted-foreground hover:text-primary rounded-xl"
            >
              <MessageSquarePlus className="h-4 w-4 mr-2" />
              New Chat
            </Button>
          </div>
        </div>

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-4 py-6 space-y-6 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent"
        >
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-full pt-16 text-center space-y-6">
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 blur-2xl rounded-full scale-150" />
                  <div className="relative p-6 rounded-2xl bg-card/80 border border-border/50 backdrop-blur-sm">
                    <Bot className="h-12 w-12 text-primary" />
                  </div>
                </div>
                <div className="space-y-2">
                  <h3 className="font-semibold text-xl">Welcome to ScholarRAG</h3>
                  <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
                    Ask questions about your uploaded academic papers. I can search through text content and analyze figures, tables, and equations.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 justify-center mt-4">
                  {["Summarize the methodology", "What are the main findings?", "Explain Figure 3"].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => setInput(suggestion)}
                      className="px-4 py-2 text-xs rounded-xl bg-secondary/50 border border-border/50 hover:bg-secondary hover:border-primary/30 transition-all duration-200"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={cn("flex flex-col animate-fade-in", msg.role === "user" ? "items-end" : "items-start")}>
                <div className={cn("flex gap-3 max-w-[90%]", msg.role === "user" && "flex-row-reverse")}>
                  <div className={cn(
                    "flex-shrink-0 h-9 w-9 rounded-xl flex items-center justify-center shadow-sm",
                    msg.role === "user"
                      ? "gradient-primary"
                      : "bg-card border border-border/50"
                  )}>
                    {msg.role === "user"
                      ? <User className="h-4 w-4 text-primary-foreground" />
                      : <Bot className="h-4 w-4 text-primary" />
                    }
                  </div>

                  <div className="flex-1 space-y-3">
                    <div className={cn(
                      "p-4 rounded-2xl leading-relaxed shadow-sm",
                      msg.role === "user"
                        ? "bg-primary/10 border border-primary/20"
                        : "bg-card/90 border border-border/50 backdrop-blur-sm"
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
                          <Link
                            key={sidx}
                            to={`/papers/${source.pdf_name}/read?page=${source.page}`}
                            className="flex items-center gap-1.5 text-[10px] bg-secondary/60 border border-border/40 px-2.5 py-1.5 rounded-lg text-muted-foreground hover:border-primary/30 hover:bg-secondary transition-all duration-200 cursor-pointer"
                          >
                            {source.type === "visual_search"
                              ? <Table className="h-3 w-3" />
                              : <FileText className="h-3 w-3" />
                            }
                            <span className="font-medium">{source.pdf_name}.pdf</span>
                            <span className="text-muted-foreground/60">p.{source.page}</span>
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex flex-col items-start animate-fade-in">
                <div className="flex gap-3 max-w-[95%]">
                  <div className="flex-shrink-0 h-9 w-9 rounded-xl bg-card border border-border/50 flex items-center justify-center shadow-sm">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 space-y-3">
                    <ThoughtProcess steps={currentSteps} isLive={true} />

                    {currentAnswer && (
                      <div className="p-4 rounded-2xl bg-card/90 border border-border/50 backdrop-blur-sm shadow-sm animate-slide-in-bottom">
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

        {showScrollButton && (
          <button
            onClick={() => scrollToBottom(true)}
            className="fixed bottom-36 right-8 p-2.5 bg-card border border-border/50 rounded-xl shadow-lg text-muted-foreground hover:text-primary hover:border-primary/30 hover:scale-105 transition-all z-20 backdrop-blur-sm"
          >
            <ArrowDownCircle className="h-5 w-5" />
          </button>
        )}

        <div className="p-6 bg-gradient-to-t from-background via-background/95 to-transparent">
          <form
            onSubmit={handleSubmit}
            className="max-w-3xl mx-auto relative group"
          >
            <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-3xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-300 pointer-events-none" />
            <div className="relative flex items-center bg-card/90 border-2 border-border/50 backdrop-blur-md rounded-2xl overflow-hidden shadow-lg transition-all duration-200 focus-within:border-primary/50 focus-within:shadow-xl focus-within:shadow-primary/5">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit()
                  }
                }}
                placeholder={activeConversationId ? "Ask about your papers..." : "Start a new conversation..."}
                className="flex-1 bg-transparent border-none focus:ring-0 px-6 py-4 resize-none h-[56px] min-h-[56px] max-h-32 scrollbar-none text-foreground placeholder:text-muted-foreground/50"
                disabled={isLoading}
                rows={1}
              />
              <div className="pr-4 flex items-center gap-2">
                <Button
                  type="submit"
                  size="sm"
                  disabled={isLoading || !input.trim()}
                  className={cn(
                    "h-9 px-4 rounded-xl transition-all duration-200",
                    input.trim() ? "scale-100 opacity-100" : "scale-90 opacity-50"
                  )}
                >
                  {isLoading
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <Send className="h-4 w-4" />
                  }
                </Button>
              </div>
            </div>
            <p className="mt-2 text-[10px] text-center text-muted-foreground/60">
              I can analyze text, figures, tables, and equations from your papers
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}
