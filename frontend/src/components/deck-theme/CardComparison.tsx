import { ArrowRight, ImagePlus, Loader2, Sparkles } from "lucide-react"

import type { ThemeCard, ThemeJob } from "@/types/deck-theme"

export function CardComparison({ card, result, editing }: {
  card: ThemeCard | null
  result: ThemeJob | null
  editing: boolean
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <figure className="min-w-0">
        <figcaption className="mb-2 flex items-center justify-between text-xs font-medium text-muted-foreground">Original <span className="text-[10px] font-normal uppercase tracking-wider">Reference</span></figcaption>
        <div className="relative flex aspect-[5/7] items-center justify-center overflow-hidden rounded-xl border border-dashed bg-zinc-950/30">
          {card ? <img src={card.image} alt={`Original ${card.face_name || card.name}`} className="h-full w-full object-contain" /> : (
            <div className="flex flex-col items-center gap-3 p-4 text-center text-muted-foreground">
              <ImagePlus className="size-7 opacity-50" />
              <p className="text-xs leading-relaxed">Choose a card<br />or import an image</p>
            </div>
          )}
        </div>
      </figure>
      <figure className="min-w-0">
        <figcaption className="mb-2 flex items-center gap-1.5 text-xs font-medium text-emerald-400"><ArrowRight className="size-3" /> Themed edit</figcaption>
        <div className={`relative flex aspect-[5/7] items-center justify-center overflow-hidden rounded-xl border bg-zinc-950/30 ${result?.result?.image ? "border-emerald-400/25" : "border-dashed"}`}>
          {result?.result?.image ? <img src={result.result.image} alt={`Themed edit of ${card?.face_name || card?.name || "card"}`} className="h-full w-full object-contain" /> : (
            <div className="flex flex-col items-center gap-3 p-4 text-center text-muted-foreground">
              {editing ? <Loader2 className="size-7 animate-spin text-emerald-400" /> : <Sparkles className="size-7 text-emerald-400/50" />}
              <p className="text-xs leading-relaxed">{editing ? "Creating your themed card…" : "Your generated edit appears here"}</p>
            </div>
          )}
        </div>
      </figure>
    </div>
  )
}
