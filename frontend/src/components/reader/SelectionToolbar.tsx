import { useEffect, useState } from "react"
import { MessageSquare, Copy, Check } from "lucide-react"
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
      className="selection-toolbar fixed z-50 flex gap-1 bg-background border shadow-lg rounded-lg p-1 animate-in fade-in zoom-in-95 duration-150"
      style={{ left: position.x, top: position.y - 50 }}
    >
      <Button variant="ghost" size="sm" onClick={onAsk} className="gap-1">
        <MessageSquare className="h-3 w-3" />
        Ask AI
      </Button>
      <Button variant="ghost" size="sm" onClick={handleCopy} className="gap-1">
        {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  )
}
