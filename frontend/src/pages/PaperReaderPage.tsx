import { useState, useCallback } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowLeft, Loader2, Menu, PanelRightClose, PanelRightOpen } from "lucide-react"
import { Button } from "../components/ui/button"
import { PDFViewer } from "../components/reader/PDFViewer"
import { TocSidebar } from "../components/reader/TocSidebar"
import { ChatPanel } from "../components/reader/ChatPanel"
import { SelectionToolbar } from "../components/reader/SelectionToolbar"
import { getPdfUrl, fetchToc, fetchPaper } from "../lib/api"

export default function PaperReaderPage() {
  const { pdfName } = useParams<{ pdfName: string }>()
  const navigate = useNavigate()

  const [currentPage, setCurrentPage] = useState(0)
  const [tocCollapsed, setTocCollapsed] = useState(false)
  const [chatCollapsed, setChatCollapsed] = useState(false)
  const [selection, setSelection] = useState<{ text: string; position: { x: number; y: number } } | null>(null)
  const [chatQuestion, setChatQuestion] = useState("")

  const { data: paper, isLoading: paperLoading } = useQuery({
    queryKey: ["paper", pdfName],
    queryFn: () => fetchPaper(pdfName!),
    enabled: !!pdfName,
  })

  const { data: toc } = useQuery({
    queryKey: ["toc", pdfName],
    queryFn: () => fetchToc(pdfName!),
    enabled: !!pdfName,
  })

  const handleTextSelect = useCallback((text: string) => {
    if (text.length > 0 && text.length < 1000) {
      const selectionObj = window.getSelection()
      if (selectionObj && selectionObj.rangeCount > 0) {
        const range = selectionObj.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        setSelection({
          text,
          position: { x: rect.left + rect.width / 2 - 100, y: rect.top + window.scrollY },
        })
      }
    }
  }, [])

  const handleTocItemClick = useCallback((pageIdx: number) => {
    setCurrentPage(pageIdx)
  }, [])

  const handleAskSelection = useCallback(() => {
    if (selection) {
      setChatQuestion(`关于「${selection.text.substring(0, 100)}${selection.text.length > 100 ? "..." : ""}」`)
      setChatCollapsed(false)
      setSelection(null)
    }
  }, [selection])

  if (paperLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-muted-foreground">Paper not found</p>
        <Button onClick={() => navigate("/papers")}>Back to Papers</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <Button variant="ghost" size="sm" onClick={() => navigate("/papers")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <div className="flex-1 min-w-0">
          <h1 className="font-medium text-sm truncate">{paper.title}</h1>
          <p className="text-xs text-muted-foreground truncate">{paper.authors}</p>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => setTocCollapsed(!tocCollapsed)}>
            <Menu className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setChatCollapsed(!chatCollapsed)}>
            {chatCollapsed ? <PanelRightOpen className="h-4 w-4" /> : <PanelRightClose className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        <TocSidebar
          items={toc?.items || []}
          currentPage={currentPage}
          onItemClick={handleTocItemClick}
          collapsed={tocCollapsed}
        />

        <div className="flex-1 overflow-hidden">
          <PDFViewer
            pdfUrl={getPdfUrl(pdfName!)}
            initialPage={currentPage}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
            onTextSelect={handleTextSelect}
          />
        </div>

        <ChatPanel
          pdfName={pdfName!}
          collapsed={chatCollapsed}
          onToggle={() => setChatCollapsed(!chatCollapsed)}
          input={chatQuestion}
          onInputChange={setChatQuestion}
        />
      </div>

      {/* Selection toolbar */}
      {selection && (
        <SelectionToolbar
          selectedText={selection.text}
          position={selection.position}
          onAsk={handleAskSelection}
          onClose={() => setSelection(null)}
        />
      )}
    </div>
  )
}
