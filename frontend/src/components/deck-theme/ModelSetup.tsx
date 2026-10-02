import { Check, ChevronDown, Download, HardDrive, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { ThemeModelStatus, ThemeStatus } from "@/types/deck-theme"

function diskSize(bytes: number) {
  return `${(bytes / 1_000_000_000).toFixed(1)} GB`
}

function ModelRow({ model, title, description, disabled, onDownload }: {
  model: ThemeModelStatus
  title: string
  description: string
  disabled: boolean
  onDownload: () => void
}) {
  const remaining = Math.max(0, model.total_bytes - model.installed_bytes)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background/30 p-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm font-medium">
          {title}
          {model.ready && <span className="inline-flex items-center gap-1 text-xs font-normal text-emerald-400"><Check className="size-3" /> Ready</span>}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {model.total_bytes > 0 ? `${diskSize(model.total_bytes)} on disk` : "Download size unavailable"}
          {model.installed_bytes > 0 && !model.ready ? ` · ${diskSize(model.installed_bytes)} already downloaded` : ""}
        </p>
      </div>
      {!model.ready && (
        <Button variant="outline" size="sm" disabled={disabled} onClick={onDownload}>
          <Download className="size-3.5" /> Download{remaining > 0 ? ` ${diskSize(remaining)}` : ""}
        </Button>
      )}
    </div>
  )
}

export function ModelSetup({ status, open, disabled, onToggle, onDownload, onRefresh }: {
  status: ThemeStatus | null
  open: boolean
  disabled: boolean
  onToggle: () => void
  onDownload: (group: "editor" | "enhancer") => void
  onRefresh: () => void
}) {
  return (
    <section className="overflow-hidden rounded-xl border bg-muted/15" aria-label="Local model setup">
      <button type="button" className="flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-muted/30" onClick={onToggle} aria-expanded={open} aria-controls="theme-model-setup">
        <span className="rounded-lg border bg-background/40 p-2"><HardDrive className="size-4 text-muted-foreground" /></span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">Local models</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            {!status ? "Check availability and download models in the app" : !status.platform_supported ? "This platform is not supported yet" : status.editor.ready ? "Image editor ready · Optional AI prompt enhancement" : "Download the image editor to start generating"}
          </span>
        </span>
        <span className={`hidden rounded-full px-2 py-0.5 text-[11px] sm:inline-block ${status?.editor.ready ? "bg-emerald-400/10 text-emerald-400" : "bg-muted text-muted-foreground"}`}>{status?.editor.ready ? "Ready" : "Setup"}</span>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div id="theme-model-setup" className="space-y-3 border-t p-3">
          <p className="text-xs leading-relaxed text-muted-foreground">Models and their engines are managed by ProxyToolBox. Downloads need internet; editing runs locally. Download sizes below are disk space, not VRAM requirements.</p>
          <p className="text-[11px] leading-relaxed text-muted-foreground">Compatible NVIDIA GPUs use an additional CUDA accelerator, prepared automatically on first generation (about 900 MB to download). Other GPUs use Vulkan.</p>
          <p className="text-[11px] text-muted-foreground"><a href="https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE" target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-foreground">Qwen Research License</a> · Noncommercial research and evaluation.</p>
          {status ? (
            <>
              {status.message && <p className="rounded-md bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">{status.message}</p>}
              <div className="grid gap-3 lg:grid-cols-2">
                <ModelRow model={status.editor} title="Qwen Image 2.1 · INT8" description="Required · Includes the 7.26 GB image model, text/vision encoder, and VAE." disabled={disabled || !status.platform_supported} onDownload={() => onDownload("editor")} />
                <ModelRow model={status.enhancer} title="AI prompt enhancer" description="Optional · Looks at the card and writes a richer editing prompt." disabled={disabled || !status.platform_supported} onDownload={() => onDownload("enhancer")} />
              </div>
            </>
          ) : <Button variant="outline" size="sm" disabled={disabled} onClick={onRefresh}>{disabled && <Loader2 className="size-3.5 animate-spin" />} Check model status</Button>}
        </div>
      )}
    </section>
  )
}
