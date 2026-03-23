import { useEffect, useState } from "react"
import { Copy, Check, Sparkles } from "lucide-react"
import { Button } from "../ui/button"

interface SelectionToolbarProps {
  selectedText: string
  position: { x: number; y: number }
  onAsk: () => void
  onClose: () => void
}

export function SelectionToolbar({ selectedText, position, onAsk, onClose }: SelectionToolbarProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest(".selection-toolbar")) {
        onClose()
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [onClose])

  const handleCopy = async () => {
    await navigator.clipboard.writeText(selectedText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className="selection-toolbar fixed z-50 flex gap-1.5 bg-card/95 backdrop-blur-xl border border-border/40 shadow-xl rounded-2xl p-1.5 animate-in fade-in zoom-in-95 duration-200"
      style={{ left: position.x, top: position.y - 55 }}
    >
      <Button
        variant="default"
        size="sm"
        onClick={onAsk}
        className="gap-2 rounded-xl h-8 px-3"
      >
        <Sparkles className="h-3.5 w-3.5" />
        Ask AI
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleCopy}
        className="gap-2 rounded-xl h-8 px-3"
      >
        {copied ? (
          <>
            <Check className="h-3.5 w-3.5 text-emerald-600" />
            <span className="text-emerald-600">Copied</span>
          </>
        ) : (
          <>
            <Copy className="h-3.5 w-3.5" />
            Copy
          </>
        )}
      </Button>
    </div>
  )
}
