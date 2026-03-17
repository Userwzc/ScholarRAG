import React, { useState } from "react"
import { 
  ChevronDown, 
  ChevronRight, 
  Search, 
  Eye, 
  BookOpen, 
  CheckCircle2, 
  Loader2,
  Table,
  FileText
} from "lucide-react"
import { cn } from "../../lib/utils"

export interface AgentStep {
  type: "thinking" | "tool_call" | "tool_result" | "observation" | "answer" | "agent_visual_context"
  tool?: string
  text?: string
  count?: number
  pages?: string[]
  phase?: string
  step?: number
}

interface ThoughtProcessProps {
  steps: AgentStep[]
  isLive?: boolean
}

export function ThoughtProcess({ steps, isLive = false }: ThoughtProcessProps) {
  const [isOpen, setIsOpen] = useState(true)

  if (steps.length === 0) return null

  // Group steps by their logical iteration/step number
  const latestStep = steps[steps.length - 1]
  const isFinished = steps.some(s => s.type === "answer")

  const getStepIcon = (step: AgentStep) => {
    switch (step.type) {
      case "thinking": return <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
      case "tool_call": return <Search className="h-3.5 w-3.5 text-indigo-500" />
      case "tool_result": return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
      case "observation": return <Eye className="h-3.5 w-3.5 text-amber-500" />
      case "agent_visual_context": return <Table className="h-3.5 w-3.5 text-purple-500" />
      default: return <BookOpen className="h-3.5 w-3.5 text-slate-400" />
    }
  }

  return (
    <div className="my-4 w-full max-w-[95%]">
      <div 
        className={cn(
          "flex items-center gap-2 px-4 py-2 cursor-pointer transition-all border rounded-t-xl bg-muted/30",
          !isOpen && "rounded-b-xl border-b"
        )}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex-1 flex items-center gap-2">
          {isLive && !isFinished ? (
            <div className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </div>
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          )}
          <span className="text-sm font-medium text-foreground/80">
            {isFinished ? "Research completed" : "Agent is researching..."}
          </span>
          <span className="text-xs text-muted-foreground ml-2">
            ({steps.length} steps)
          </span>
        </div>
        {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </div>

      {isOpen && (
        <div className="border-x border-b rounded-b-xl p-4 bg-muted/10 space-y-3 animate-in fade-in slide-in-from-top-2 duration-300">
          {steps.map((step, idx) => (
            <div key={idx} className="flex gap-3 items-start group">
              <div className="mt-1 flex-shrink-0">
                {getStepIcon(step)}
              </div>
              <div className="flex-1 space-y-1">
                <div className="text-sm text-foreground/70 leading-relaxed">
                  {step.text || (step.tool === 'search_papers' ? 'Searching papers database...' : step.tool)}
                </div>
                {step.pages && step.pages.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {step.pages.map((p, pidx) => (
                      <span key={pidx} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 bg-secondary/50 rounded text-muted-foreground">
                        <FileText className="h-2.5 w-2.5" />
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {isLive && !isFinished && (
            <div className="flex gap-3 items-center ml-0.5">
              <div className="flex space-x-1">
                <div className="h-1 w-1 bg-blue-500/50 rounded-full animate-bounce"></div>
                <div className="h-1 w-1 bg-blue-500/50 rounded-full animate-bounce [animation-delay:0.2s]"></div>
                <div className="h-1 w-1 bg-blue-500/50 rounded-full animate-bounce [animation-delay:0.4s]"></div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
