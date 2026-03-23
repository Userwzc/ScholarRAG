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

  const isFinished = steps.some(s => s.type === "answer")

  const getStepIcon = (step: AgentStep) => {
    switch (step.type) {
      case "thinking": 
        return <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />
      case "tool_call": 
        return <Search className="h-3.5 w-3.5 text-primary" />
      case "tool_result": 
        return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
      case "observation": 
        return <Eye className="h-3.5 w-3.5 text-amber-600" />
      case "agent_visual_context": 
        return <Table className="h-3.5 w-3.5 text-primary" />
      default: 
        return <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
    }
  }

  return (
    <div className="my-3 w-full max-w-[95%]">
      <div 
        className={cn(
          "flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-all duration-200 border rounded-xl",
          isOpen ? "rounded-b-none" : "",
          "bg-gradient-to-r from-primary/5 via-primary/3 to-transparent border-primary/20 hover:border-primary/30"
        )}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex-1 flex items-center gap-3">
          {isLive && !isFinished ? (
            <div className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary"></span>
            </div>
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          )}
          <span className="text-sm font-medium text-foreground/80">
            {isFinished ? "Research completed" : "Agent is researching..."}
          </span>
          <span className="text-xs text-muted-foreground bg-secondary/50 px-2 py-0.5 rounded-full">
            {steps.length} steps
          </span>
        </div>
        {isOpen 
          ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> 
          : <ChevronRight className="h-4 w-4 text-muted-foreground" />
        }
      </div>

      {isOpen && (
        <div className="border-x border-b border-primary/10 rounded-b-xl p-4 bg-gradient-to-b from-primary/3 to-transparent space-y-3 animate-slide-in-top">
          {steps.map((step, idx) => (
            <div key={idx} className="flex gap-3 items-start group animate-fade-in" style={{ animationDelay: `${idx * 50}ms` }}>
              <div className="mt-0.5 flex-shrink-0 p-1 rounded-lg bg-secondary/50">
                {getStepIcon(step)}
              </div>
              <div className="flex-1 space-y-1.5">
                <div className="text-sm text-foreground/70 leading-relaxed">
                  {step.text || (step.tool === 'search_papers' ? 'Searching papers database...' : step.tool)}
                </div>
                {step.pages && step.pages.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {step.pages.map((p, pidx) => (
                      <span 
                        key={pidx} 
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 bg-secondary/60 border border-border/40 rounded-lg text-muted-foreground"
                      >
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
            <div className="flex gap-3 items-center ml-0.5 pt-1">
              <div className="flex space-x-1">
                <div className="h-1.5 w-1.5 bg-primary/60 rounded-full animate-bounce"></div>
                <div className="h-1.5 w-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:0.15s]"></div>
                <div className="h-1.5 w-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:0.3s]"></div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
