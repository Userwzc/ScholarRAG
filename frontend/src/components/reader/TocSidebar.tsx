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
    <div className="w-60 border-r bg-muted/30 flex flex-col h-full overflow-hidden">
      <div className="p-3 border-b bg-background">
        <h2 className="font-semibold text-sm">Table of Contents</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {sections.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground uppercase tracking-wider">
              <FileText className="h-3 w-3" />
              Sections
            </div>
            {sections.map((item) => (
              <button
                key={item.id}
                onClick={() => onItemClick(item.page_idx)}
                className={cn(
                  "w-full text-left px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors flex items-center gap-1",
                  item.level === 1 && "font-medium",
                  item.level === 2 && "pl-4",
                  item.level === 3 && "pl-6",
                  item.level >= 4 && "pl-8 text-xs",
                  currentPage === item.page_idx && "bg-primary/10 text-primary"
                )}
              >
                <ChevronRight className="h-3 w-3 shrink-0" />
                <span className="truncate">{item.text}</span>
              </button>
            ))}
          </div>
        )}

        {visuals.length > 0 && (
          <div>
            <div className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground uppercase tracking-wider">
              <Image className="h-3 w-3" />
              Figures & Tables
            </div>
            {visuals.map((item) => (
              <button
                key={item.id}
                onClick={() => onItemClick(item.page_idx)}
                className={cn(
                  "w-full text-left px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors flex items-center gap-2",
                  currentPage === item.page_idx && "bg-primary/10 text-primary"
                )}
              >
                {item.chunk_type === "table" ? (
                  <Table className="h-3 w-3 shrink-0 text-muted-foreground" />
                ) : (
                  <Image className="h-3 w-3 shrink-0 text-muted-foreground" />
                )}
                <span className="truncate">{item.text}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
