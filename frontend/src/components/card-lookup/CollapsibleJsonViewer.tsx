import { useState } from "react"
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react"

import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

interface CollapsibleJsonViewerProps {
  data: any
  title?: string
  defaultOpen?: boolean
}

export function CollapsibleJsonViewer({ data, title = "Raw JSON Data", defaultOpen = false }: CollapsibleJsonViewerProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const [copied, setCopied] = useState(false)

  const jsonString = JSON.stringify(data, null, 2)

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border rounded-lg overflow-hidden bg-zinc-950 flex flex-col transition-all duration-200">
      <div 
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-zinc-900 select-none"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          {isOpen ? <ChevronDown className="h-4 w-4 text-zinc-400" /> : <ChevronRight className="h-4 w-4 text-zinc-400" />}
          <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">{title}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-zinc-400 hover:text-white hover:bg-zinc-800"
          onClick={(e) => {
            e.stopPropagation()
            handleCopy()
          }}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>

      <div className={cn(
        "grid overflow-hidden transition-all duration-300 ease-in-out",
        isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      )}>
        <ScrollArea className="min-h-0 h-[300px] border-t border-zinc-900">
          <pre className="p-4 text-[11px] leading-relaxed text-emerald-400/90 font-mono select-text cursor-text tab-size-2">
            {jsonString}
          </pre>
        </ScrollArea>
      </div>
    </div>
  )
}
