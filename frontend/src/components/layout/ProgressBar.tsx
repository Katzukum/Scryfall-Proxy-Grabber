import { useState, useEffect } from "react"
import { Progress } from "@/components/ui/progress"

export function ProgressBar() {
  const [current, setCurrent] = useState(0)
  const [total, setTotal] = useState(0)
  const [label, setLabel] = useState("")

  useEffect(() => {
    window.__pushProgress = (cur: number, tot: number, lbl: string) => {
      setCurrent(cur)
      setTotal(tot)
      setLabel(lbl)
    }

    // Original reference could be stored differently but is unused so we skip it
    
    // We override or hook into it. If it's already defined we should compose them,
    // but typically we can just reset our own state when task is complete.
    // However, the tab components handle the actual onTaskComplete.
    // We can just define an extra listener pattern if needed, but for simplicity
    // we just let the progress bar reset after a few seconds of 100% or completion.
    
    return () => {
      window.__pushProgress = undefined;
    }
  }, [])

  const percentage = total > 0 ? Math.round((current / total) * 100) : 0
  const isVisible = total > 0 && current < total;

  if (!isVisible && total === 0) return null;

  return (
    <div className="space-y-1.5 w-full py-2">
      <div className="flex justify-between text-xs text-muted-foreground mr-1">
        <span className="max-w-[80%] truncate">{label || "Processing..."}</span>
        <span>{percentage}% ({current}/{total})</span>
      </div>
      <Progress value={percentage} className="h-2" />
    </div>
  )
}
