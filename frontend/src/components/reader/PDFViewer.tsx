import { useEffect, useRef, useCallback } from "react"
import { Viewer, Worker } from "@react-pdf-viewer/core"
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout"
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation"
import type { PageChangeEvent } from "@react-pdf-viewer/core"
import "@react-pdf-viewer/core/lib/styles/index.css"
import "@react-pdf-viewer/default-layout/lib/styles/index.css"

interface PDFViewerProps {
  pdfUrl: string
  initialPage?: number
  currentPage?: number
  onPageChange?: (page: number) => void
  onTextSelect?: (text: string) => void
}

export function PDFViewer({ 
  pdfUrl, 
  initialPage = 0, 
  currentPage,
  onPageChange,
  onTextSelect 
}: PDFViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const lastJumpedPage = useRef(initialPage)

  const pageNavigationPluginInstance = pageNavigationPlugin()
  const { jumpToPage } = pageNavigationPluginInstance

  const defaultLayoutPluginInstance = defaultLayoutPlugin({
    sidebarTabs: () => [],
  })

  const handlePageChange = useCallback((e: PageChangeEvent) => {
    onPageChange?.(e.currentPage)
  }, [onPageChange])

  // Handle programmatic page navigation from TOC clicks
  useEffect(() => {
    if (
      currentPage !== undefined &&
      currentPage !== lastJumpedPage.current
    ) {
      lastJumpedPage.current = currentPage
      jumpToPage(currentPage)
    }
  }, [currentPage, jumpToPage])

  useEffect(() => {
    const handleMouseUp = () => {
      const selection = window.getSelection()
      const text = selection?.toString().trim()
      if (text && onTextSelect) {
        onTextSelect(text)
      }
    }

    const container = containerRef.current
    container?.addEventListener("mouseup", handleMouseUp)
    return () => container?.removeEventListener("mouseup", handleMouseUp)
  }, [onTextSelect])

  return (
    <div ref={containerRef} className="h-full">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.js">
        <Viewer
          fileUrl={pdfUrl}
          plugins={[pageNavigationPluginInstance, defaultLayoutPluginInstance]}
          initialPage={initialPage}
          onPageChange={handlePageChange}
        />
      </Worker>
    </div>
  )
}
