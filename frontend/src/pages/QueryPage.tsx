import { useState, useRef, useEffect, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import { Search, Loader2, FileText, Table, Sparkles } from "lucide-react"
import { Button } from "../components/ui/button"
import { Input } from "../components/ui/input"
import { Card, CardContent } from "../components/ui/card"
import { createQueryStream, type SSEEvent } from "../lib/api"

interface Message {
  role: "user" | "assistant"
  content: string
  sources?: Array<{
    pdf_name: string
    page: number
    type: string
  }>
}

interface AgentStep {
  type: "thinking" | "tool_call" | "tool_result" | "observation" | "answer"
  tool?: string
  text?: string
  count?: number
  pages?: string[]
}

export default function QueryPage() {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const [sources, setSources] = useState<Array<{ pdf_name: string; page: number; type: string }>>([])
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const isStreamComplete = useRef(false)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, currentAnswer, agentSteps])

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim() || isLoading) return

    const userQuestion = question.trim()
    setQuestion("")
    setMessages((prev) => [...prev, { role: "user", content: userQuestion }])
    setCurrentAnswer("")
    setSources([])
    setAgentSteps([])
    setIsLoading(true)
    isStreamComplete.current = false

    let answerBuffer = ""
    const collectedSources: Array<{ pdf_name: string; page: number; type: string }> = []

    const cleanup = createQueryStream(
      userQuestion,
      (event: SSEEvent) => {
        const eventType = event.type as string
        
        if (eventType === "agent_status") {
          const phase = event.phase as string
          const statusText = event.text as string
          const step = event.step as number
          if (phase === "thinking") {
            setAgentSteps(prev => [...prev, { type: "thinking", text: `Step ${step}: ${statusText}` }])
          }
        } else if (eventType === "tool_call") {
          const tool = event.tool as string
          const args = event.args as Record<string, unknown>
          const query = args.query as string | undefined
          setAgentSteps(prev => [...prev, { 
            type: "tool_call", 
            tool,
            text: query ? `Searching for: "${query}"` : `Using tool: ${tool}`
          }])
        } else if (eventType === "tool_result") {
          const count = event.count as number
          const pages = event.pages as string[]
          const kind = event.kind as string
          setAgentSteps(prev => [...prev, { 
            type: "tool_result", 
            count, 
            pages,
            text: `Found ${count} result(s)`
          }])
          pages?.forEach((page) => {
            const [pdf_name, pageStr] = page.split(":")
            const pageNum = parseInt(pageStr, 10)
            if (!isNaN(pageNum)) {
              collectedSources.push({ pdf_name, page: pageNum, type: kind })
            }
          })
          setSources([...collectedSources])
        } else if (eventType === "agent_observation") {
          const text = event.text as string
          setAgentSteps(prev => [...prev, { type: "observation", text }])
        } else if (eventType === "answer_token") {
          const text = event.text as string
          answerBuffer += text
          setCurrentAnswer(answerBuffer)
        } else if (eventType === "answer_started") {
          setAgentSteps(prev => [...prev, { type: "answer", text: "Generating answer..." }])
        } else if (eventType === "answer_done") {
          isStreamComplete.current = true
          setIsLoading(false)
          if (answerBuffer) {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: answerBuffer, sources: [...collectedSources] },
            ])
          }
          setCurrentAnswer("")
          setAgentSteps([])
        }
      },
      (error) => {
        console.error("Query error:", error)
        setIsLoading(false)
      }
    )

    return cleanup
  }, [question, isLoading])

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold mb-2">Query Your Papers</h1>
        <p className="text-muted-foreground">
          Ask questions about your academic papers
        </p>
      </div>

      <form onSubmit={handleSubmit} className="mb-8 flex gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your papers..."
          className="flex-1"
          disabled={isLoading}
        />
        <Button type="submit" disabled={isLoading || !question.trim()}>
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        </Button>
      </form>

      <div className="space-y-6">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <Card className={`max-w-[80%] ${msg.role === "user" ? "bg-primary text-primary-foreground" : ""}`}>
              <CardContent className="p-4">
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-opacity-20">
                    <p className="text-xs font-medium mb-2 opacity-80">Sources:</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((source, sidx) => (
                        <span
                          key={sidx}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-opacity-10 bg-white"
                        >
                          {source.type === "visual_search" ? <Table className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                          {source.pdf_name}.pdf p.{source.page}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        ))}

        {currentAnswer && (
          <div className="flex justify-start">
            <Card className="max-w-[80%]">
              <CardContent className="p-4">
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{currentAnswer}</ReactMarkdown>
                </div>
                {sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-xs font-medium mb-2 text-muted-foreground">Sources:</p>
                    <div className="flex flex-wrap gap-2">
                      {sources.map((source, sidx) => (
                        <span
                          key={sidx}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-secondary"
                        >
                          {source.type === "visual_search" ? <Table className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                          {source.pdf_name}.pdf p.{source.page}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {isLoading && !currentAnswer && agentSteps.length === 0 && (
          <div className="flex justify-start">
            <Card className="max-w-[80%]">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Thinking...</span>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {agentSteps.length > 0 && (
          <div className="flex justify-start">
            <Card className="max-w-[90%]">
              <CardContent className="p-4 space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Sparkles className="h-4 w-4" />
                  <span>Agent Progress</span>
                </div>
                <div className="space-y-1 text-sm text-muted-foreground">
                  {agentSteps.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      {step.type === "thinking" && <Loader2 className="h-3 w-3 animate-spin mt-1" />}
                      {step.type === "tool_call" && <Search className="h-3 w-3 mt-1 text-blue-500" />}
                      {step.type === "tool_result" && <FileText className="h-3 w-3 mt-1 text-green-500" />}
                      {step.type === "observation" && <Sparkles className="h-3 w-3 mt-1 text-purple-500" />}
                      {step.type === "answer" && <Sparkles className="h-3 w-3 mt-1 text-yellow-500" />}
                      <span>{step.text}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
