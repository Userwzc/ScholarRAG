import { ChevronRight, FileText, Image, Table } from "lucide-react"
import { cn } from "../../lib/utils"
import type { TOCItem } from "../../lib/api"

interface TocSidebarProps {
  items: TOCItem[]
  currentPage: number
  onItemClick: (pageIdx: number) => void
  collapsed?: boolean
}

export function TocSidebar({ items, currentPage, onItemClick, collapsed = false }: TocSidebarProps) {
  if (collapsed) return null

  const sections = items.filter((item) => item.chunk_type === "section")
  const visuals = items.filter((item) => item.chunk_type !== "section")

  return (
    <div className="w-64 border-r border-border/40 bg-secondary/20 backdrop-blur-sm flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border/40 bg-background/50 backdrop-blur-sm">
        <h2 className="font-semibold text-sm tracking-tight">Table of Contents</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4 scrollbar-thin scrollbar-thumb-muted">
        {sections.length > 0 && (
          <div>
            <div className="flex items-center gap-2 px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium">
              <FileText className="h-3 w-3" />
              Sections
            </div>
            {sections.map((item) => (
              <button
                key={item.id}
                onClick={() => onItemClick(item.page_idx)}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm rounded-xl transition-all duration-200 flex items-center gap-2",
                  "hover:bg-secondary/60",
                  item.level === 1 && "font-medium",
                  item.level === 2 && "pl-6",
                  item.level === 3 && "pl-9",
                  item.level >= 4 && "pl-12 text-xs",
                  currentPage === item.page_idx && "bg-primary/10 text-primary hover:bg-primary/15"
                )}
              >
                <ChevronRight className={cn(
                  "h-3 w-3 shrink-0 transition-transform duration-200",
                  currentPage === item.page_idx && "rotate-90"
                )} />
                <span className="truncate leading-tight">{item.text}</span>
              </button>
            ))}
          </div>
        )}

        {visuals.length > 0 && (
          <div>
            <div className="flex items-center gap-2 px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium">
              <Image className="h-3 w-3" />
              Figures & Tables
            </div>
            {visuals.map((item) => (
              <button
                key={item.id}
                onClick={() => onItemClick(item.page_idx)}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm rounded-xl transition-all duration-200 flex items-center gap-2.5",
                  "hover:bg-secondary/60",
                  currentPage === item.page_idx && "bg-primary/10 text-primary hover:bg-primary/15"
                )}
              >
                {item.chunk_type === "table" ? (
                  <Table className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                ) : (
                  <Image className="h-3.5 w-3.5 shrink-0 text-purple-500" />
                )}
                <span className="truncate leading-tight">{item.text}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
