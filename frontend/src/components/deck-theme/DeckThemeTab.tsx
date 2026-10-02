import { useCallback, useEffect, useRef, useState } from "react"
import { Check, Copy, Download, ImagePlus, Layers, Loader2, Palette, Search, Sparkles, Square, WandSparkles, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { usePywebview } from "@/hooks/usePywebview"
import type { ThemeCard, ThemeJob, ThemeStatus } from "@/types/deck-theme"
import { CardComparison } from "./CardComparison"
import { ModelSetup } from "./ModelSetup"

type CardPrinting = {
  name: string
  set_code: string
  collector_number: string
  image_url_small: string
  raw_json: Record<string, unknown>
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : ""
}

function parsePrintings(values: unknown[]): CardPrinting[] {
  return values.map(value => {
    const item = record(value)
    return {
      name: stringValue(item.name),
      set_code: stringValue(item.set_code),
      collector_number: stringValue(item.collector_number),
      image_url_small: stringValue(item.image_url_small),
      raw_json: record(item.raw_json),
    }
  }).filter(item => item.name && Object.keys(item.raw_json).length)
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message
  const message = record(error).message
  return stringValue(message) || stringValue(error) || "Something went wrong. Please try again."
}

const selectClass = "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"

export function DeckThemeTab({ onUseInPrint }: { onUseInPrint: (folder: string) => void }) {
  const { api } = usePywebview()
  const [status, setStatus] = useState<ThemeStatus | null>(null)
  const [setupOpen, setSetupOpen] = useState(false)
  const [job, setJob] = useState<ThemeJob | null>(null)
  const [card, setCard] = useState<ThemeCard | null>(null)
  const [selectedPrinting, setSelectedPrinting] = useState<CardPrinting | null>(null)
  const [faceIndex, setFaceIndex] = useState(0)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<CardPrinting[]>([])
  const [searched, setSearched] = useState(false)
  const [theme, setTheme] = useState("")
  const [prompt, setPrompt] = useState("")
  const [promptTheme, setPromptTheme] = useState("")
  const [resolution, setResolution] = useState("preview")
  const [steps, setSteps] = useState("25")
  const [seed, setSeed] = useState("42")
  const [device, setDevice] = useState<"auto" | "cpu">("auto")
  const [result, setResult] = useState<ThemeJob | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [cancelling, setCancelling] = useState(false)
  const currentCard = useRef<ThemeCard | null>(null)
  const completedJob = useRef("")
  const currentTheme = useRef("")

  const running = job?.state === "running"
  const busy = pending !== null || running
  const inputsLocked = pending !== null || (running && job.kind !== "download")
  const numericSteps = Number(steps)
  const numericSeed = Number(seed)
  const promptNeedsUpdate = prompt.trim().length > 0 && promptTheme !== theme.trim()
  const validSettings = steps.trim() !== "" && seed.trim() !== "" && Number.isInteger(numericSteps) && numericSteps >= 1 && numericSteps <= 50 && Number.isInteger(numericSeed) && numericSeed >= 0 && numericSeed <= 2147483647
  const faces = Array.isArray(selectedPrinting?.raw_json.card_faces)
    ? selectedPrinting.raw_json.card_faces.map((value, index) => {
      const face = record(value)
      return { index, name: stringValue(face.name), hasImage: Object.keys(record(face.image_uris)).length > 0 }
    }).filter(face => face.hasImage)
    : []

  const acceptJob = useCallback((next: ThemeJob | null) => {
    setJob(next)
    if (!next || next.state === "running") return
    setCancelling(false)
    if (completedJob.current === next.id) return
    completedJob.current = next.id
    if (next.state === "failed") setError(next.error || next.message || "The operation failed. Please try again.")
    if (next.state === "cancelled") setNotice("Operation cancelled. You can try again when ready.")
    if (next.state === "complete") {
      const matchingCard = !currentCard.current || next.result?.card_id === currentCard.current.id
      if (next.kind === "enhance" && next.result?.prompt && matchingCard) {
        setPrompt(next.result.prompt)
        setPromptTheme(currentTheme.current)
        setNotice("AI prompt ready. Review it before generating your card.")
      }
      if (next.kind === "edit" && next.result?.image && matchingCard) {
        setResult(next)
        setNotice("Edit complete. Check card text and symbols before printing.")
      }
      if (next.kind === "download") setNotice("Download complete. Your local models are ready to use.")
    }
    if (api) void api.deck_theme_status().then(setStatus).catch(err => setError(errorMessage(err)))
  }, [api])

  useEffect(() => {
    if (!api) return
    let disposed = false
    void api.deck_theme_status().then(value => {
      if (disposed) return
      setStatus(value)
      acceptJob(value.job)
    }).catch(err => { if (!disposed) setError(errorMessage(err)) })
    return () => { disposed = true }
  }, [api, acceptJob])

  useEffect(() => {
    if (!api || !running) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const next = await api.deck_theme_job()
        if (disposed) return
        acceptJob(next)
        if (next?.state !== "running") return
      } catch (err) {
        if (disposed) return
        setError(`Unable to refresh progress: ${errorMessage(err)}`)
      }
      if (!disposed) timer = setTimeout(poll, 1500)
    }
    timer = setTimeout(poll, 750)
    return () => { disposed = true; clearTimeout(timer) }
  }, [api, acceptJob, running, job?.id])

  async function execute(name: string, action: () => Promise<void>) {
    setPending(name)
    setError("")
    setNotice("")
    try { await action() } catch (err) { setError(errorMessage(err)) } finally { setPending(null) }
  }

  function adoptCard(next: ThemeCard) {
    currentCard.current = next
    setCard(next)
    setPrompt("")
    setPromptTheme("")
    setResult(null)
    setResults([])
    setSearched(false)
  }

  async function searchCards() {
    if (!api || !query.trim() || inputsLocked) return
    await execute("search", async () => {
      setResults([])
      setSearched(false)
      setResults(parsePrintings(await api.search_card(query.trim())))
      setSearched(true)
    })
  }

  async function choosePrinting(printing: CardPrinting, face = 0) {
    if (!api) return
    await execute("card", async () => {
      const prepared = await api.deck_theme_prepare_card(printing.raw_json, face)
      adoptCard(prepared)
      setSelectedPrinting(printing)
      setFaceIndex(face)
    })
  }

  async function importImage() {
    if (!api) return
    await execute("import", async () => {
      const imported = await api.deck_theme_import_image()
      if (!imported) return
      adoptCard(imported)
      setSelectedPrinting(null)
      setFaceIndex(0)
    })
  }

  async function buildPrompt() {
    if (!api || !card || !theme.trim()) return
    await execute("prompt", async () => {
      setPrompt(await api.deck_theme_build_prompt(card.id, theme.trim()))
      setPromptTheme(theme.trim())
    })
  }

  async function startDownload(group: "editor" | "enhancer") {
    if (!api) return
    await execute(`download-${group}`, async () => { acceptJob(await api.deck_theme_start_download(group)) })
  }

  async function enhancePrompt() {
    if (!api || !card) return
    await execute("enhance", async () => {
      const basePrompt = !prompt.trim() || promptTheme !== theme.trim()
        ? await api.deck_theme_build_prompt(card.id, theme.trim())
        : prompt.trim()
      setPrompt(basePrompt)
      setPromptTheme(theme.trim())
      acceptJob(await api.deck_theme_start_enhance(card.id, theme.trim(), basePrompt, device))
    })
  }

  async function generateEdit() {
    if (!api || !card || !validSettings || promptNeedsUpdate) return
    await execute("edit", async () => {
      const next = await api.deck_theme_start_edit({
        card_id: card.id,
        theme: theme.trim(),
        prompt: prompt.trim(),
        width: resolution === "preview" ? 512 : 768,
        height: resolution === "preview" ? 704 : 1088,
        steps: numericSteps,
        seed: numericSeed,
        device,
      })
      setResult(null)
      acceptJob(next)
    })
  }

  async function cancelJob() {
    if (!api || cancelling) return
    setCancelling(true)
    try { await api.deck_theme_cancel() } catch (err) { setError(errorMessage(err)); setCancelling(false) }
  }

  async function saveResult() {
    if (!api || !result) return
    await execute("save", async () => {
      const destination = await api.deck_theme_save_result(result.id)
      if (destination) setNotice(`Saved to ${destination}`)
    })
  }

  async function copyOutputPath() {
    const path = result?.result?.output_path
    if (!path) return
    await execute("copy", async () => {
      await navigator.clipboard.writeText(path)
      setNotice("Output path copied to clipboard.")
    })
  }

  const progress = job && job.total > 0 ? Math.min(100, Math.max(0, job.current / job.total * 100)) : 0

  return (
    <div className="mx-auto max-w-[1440px] space-y-5 p-1 pb-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><Palette className="size-5 text-emerald-400" /> DeckTheme</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Give your cards a new world. Start with one card, refine the prompt, and compare the result.</p>
        </div>
        <span className="rounded-full border px-2.5 py-1 text-[11px] text-muted-foreground">Local image editing</span>
      </div>

      <Tabs defaultValue="single" className="gap-4">
        <TabsList className="w-full max-w-sm">
          <TabsTrigger value="single" className="gap-2"><ImagePlus className="size-4" /> Single Card</TabsTrigger>
          <TabsTrigger value="deck" className="gap-2"><Layers className="size-4" /> Deck <span className="ml-1 text-[10px] text-muted-foreground">Soon</span></TabsTrigger>
        </TabsList>

        <TabsContent value="single" forceMount className="m-0 space-y-4 data-[state=inactive]:hidden">
          <ModelSetup status={status} open={setupOpen} disabled={busy || !api} onToggle={() => setSetupOpen(!setupOpen)} onDownload={startDownload} onRefresh={() => {
            if (api) void execute("status", async () => { const value = await api.deck_theme_status(); setStatus(value); acceptJob(value.job) })
          }} />

          {!api && <p role="status" className="rounded-lg border px-3 py-2.5 text-xs text-muted-foreground">Open ProxyToolBox’s desktop app to search cards, download models, and generate edits.</p>}

          {error && <div role="alert" className="flex items-start gap-3 rounded-lg border border-red-400/25 bg-red-400/5 px-3 py-2.5 text-xs leading-relaxed text-red-300"><span className="min-w-0 flex-1 break-words">{error}</span><button type="button" onClick={() => setError("")} aria-label="Dismiss error"><X className="size-4" /></button></div>}
          {notice && <div role="status" className="flex items-start gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-3 py-2.5 text-xs leading-relaxed text-emerald-300"><Check className="mt-0.5 size-3.5 shrink-0" /><span className="break-all">{notice}</span></div>}

          {running && job && (
            <div className="space-y-2 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3" role="status" aria-live="polite">
              <div className="flex items-center gap-2">
                <Loader2 className="size-4 shrink-0 animate-spin text-emerald-400" />
                <p className="min-w-0 flex-1 break-words text-xs">{job.message || (job.kind === "download" ? "Downloading models…" : job.kind === "enhance" ? "Enhancing your prompt…" : "Generating your card…")}</p>
                {job.total > 0 && <span className="text-xs tabular-nums text-muted-foreground">{Math.floor(progress)}%</span>}
                <Button variant="ghost" size="sm" disabled={cancelling} onClick={cancelJob}><Square className="size-3" /> {cancelling ? "Cancelling…" : "Cancel"}</Button>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={job.kind === "download" ? "Download progress" : "Generation progress"} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.total > 0 ? Math.floor(progress) : undefined}>
                <div className={`h-full rounded-full bg-emerald-400 transition-[width] ${job.total <= 0 ? "w-1/3 animate-pulse" : ""}`} style={job.total > 0 ? { width: `${progress}%` } : undefined} />
              </div>
            </div>
          )}

          <div className="grid items-start gap-5 md:grid-cols-[minmax(300px,1fr)_minmax(300px,1.05fr)]">
            <div className="space-y-5">
              <section className="space-y-3 rounded-xl border p-4" aria-labelledby="theme-source-title">
                <h3 id="theme-source-title" className="flex items-center gap-2 text-sm font-medium"><span className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">1</span> Choose a card</h3>
                <form className="flex gap-2" onSubmit={event => { event.preventDefault(); void searchCards() }}>
                  <Input aria-label="Card name" placeholder="Search a card, e.g. Sol Ring" value={query} onChange={event => setQuery(event.target.value)} disabled={inputsLocked || !api} />
                  <Button type="submit" variant="secondary" disabled={inputsLocked || !api || !query.trim()}>{pending === "search" ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />} Search</Button>
                </form>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-muted-foreground">Find a printing on Scryfall, or use your own image.</p>
                  <Button variant="outline" size="sm" disabled={inputsLocked || !api} onClick={importImage}>{pending === "import" ? <Loader2 className="size-3.5 animate-spin" /> : <ImagePlus className="size-3.5" />} Import image</Button>
                </div>

                {searched && results.length === 0 && <p className="rounded-lg bg-muted/30 p-3 text-xs text-muted-foreground">No printings found. Try the card’s full name and check your internet connection.</p>}
                {results.length > 0 && (
                  <div className="space-y-2 border-t pt-3">
                    <div className="flex items-center justify-between"><p className="text-xs text-muted-foreground">{results.length} printings · Select the original artwork</p><Button variant="ghost" size="icon-xs" aria-label="Close search results" onClick={() => { setResults([]); setSearched(false) }}><X /></Button></div>
                    <div className="grid max-h-72 grid-cols-4 gap-2 overflow-y-auto p-1 sm:grid-cols-5 xl:grid-cols-4">
                      {results.map((printing, index) => (
                        <button type="button" key={`${printing.set_code}-${printing.collector_number}-${index}`} disabled={inputsLocked} onClick={() => { void choosePrinting(printing) }} className="group overflow-hidden rounded-lg border bg-background/40 text-left transition-colors hover:border-emerald-400/60 focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-40" aria-label={`Select ${printing.name}, ${printing.set_code} number ${printing.collector_number}`}>
                          {printing.image_url_small ? <img src={printing.image_url_small} alt={printing.name} loading="lazy" className="aspect-[5/7] w-full object-contain" /> : <div className="flex aspect-[5/7] items-center justify-center p-2 text-center text-xs text-muted-foreground">{printing.name}</div>}
                          <p className="truncate px-1.5 py-1.5 text-[10px] text-muted-foreground">{printing.set_code.toUpperCase()} · #{printing.collector_number}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {pending === "card" && <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Loading original image…</p>}
                {card && (
                  <div className="space-y-2 rounded-lg bg-muted/30 p-3">
                    <div className="flex items-start justify-between gap-2"><div><p className="text-sm font-medium">{card.face_name || card.name}</p><p className="mt-0.5 text-[11px] text-muted-foreground">{card.set_code ? `${card.set_code.toUpperCase()} · #${card.collector_number}` : "Imported image"}{card.type_line ? ` · ${card.type_line}` : ""}</p></div><Check className="mt-0.5 size-4 shrink-0 text-emerald-400" /></div>
                    {faces.length > 1 && <div className="space-y-1"><Label htmlFor="theme-face" className="text-xs">Card face</Label><select id="theme-face" value={faceIndex} className={selectClass} disabled={inputsLocked} onChange={event => { if (selectedPrinting) void choosePrinting(selectedPrinting, Number(event.target.value)) }}>{faces.map(face => <option key={face.index} value={face.index}>{stringValue(face.name) || `Face ${face.index + 1}`}</option>)}</select></div>}
                    {card.oracle_text && <p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">{card.oracle_text}</p>}
                  </div>
                )}
              </section>

              <section className="space-y-3 rounded-xl border p-4" aria-labelledby="theme-prompt-title">
                <h3 id="theme-prompt-title" className="flex items-center gap-2 text-sm font-medium"><span className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">2</span> Create the theme</h3>
                <div className="space-y-1.5"><Label htmlFor="theme-description">Theme</Label><Input id="theme-description" placeholder="e.g. Rick and Morty, portal science and green energy" value={theme} disabled={inputsLocked} onChange={event => { setTheme(event.target.value); currentTheme.current = event.target.value.trim() }} /></div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" disabled={!api || !card || !theme.trim() || inputsLocked} onClick={buildPrompt}>{pending === "prompt" ? <Loader2 className="size-3.5 animate-spin" /> : <WandSparkles className="size-3.5" />} Build prompt</Button>
                  <Button variant="outline" disabled={!api || !card || !theme.trim() || busy || !status?.enhancer.ready || !status.platform_supported} onClick={enhancePrompt}><Sparkles className="size-3.5" /> Enhance with AI</Button>
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">Build a prompt from card details without downloading a model. AI enhancement also looks at the original image and follows the Processing setting: Automatic prefers GPU, while CPU keeps inference on the CPU.{!status?.enhancer.ready && <> <button type="button" onClick={() => setSetupOpen(true)} className="underline underline-offset-2 hover:text-foreground">Download the optional enhancer</button>.</>}</p>
                <div className="space-y-1.5"><Label htmlFor="theme-edit-prompt">Editing prompt</Label><Textarea id="theme-edit-prompt" value={prompt} onChange={event => { setPrompt(event.target.value); setPromptTheme(theme.trim()) }} disabled={inputsLocked} placeholder="Choose a card and describe a theme, then build a prompt. You can also write your own instructions here." className="min-h-40 resize-y text-xs leading-relaxed" /></div>
                {promptNeedsUpdate && <p className="text-[11px] text-amber-300">The theme changed. Rebuild or update the prompt before generating.</p>}
              </section>
            </div>

            <section className="space-y-4 rounded-xl border bg-muted/10 p-4" aria-labelledby="theme-generate-title">
              <div className="flex items-center justify-between gap-2"><h3 id="theme-generate-title" className="flex items-center gap-2 text-sm font-medium"><span className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">3</span> Generate & compare</h3><span className="text-[10px] text-muted-foreground">Qwen Image 2.1</span></div>
              <CardComparison card={card} result={result} editing={running && job.kind === "edit"} />
              <p className="text-[11px] leading-relaxed text-muted-foreground">Edits use the full card as a reference. Generated text and mana symbols can change; inspect the result before printing.</p>

              <div className="grid grid-cols-2 gap-3 border-t pt-4">
                <div className="space-y-1.5"><Label htmlFor="theme-resolution" className="text-xs">Output size</Label><select id="theme-resolution" value={resolution} onChange={event => setResolution(event.target.value)} disabled={inputsLocked} className={selectClass}><option value="preview">Preview · 512 × 704</option><option value="standard">Standard · 768 × 1088</option></select></div>
                <div className="space-y-1.5"><Label htmlFor="theme-device" className="text-xs">Processing</Label><select id="theme-device" value={device} onChange={event => setDevice(event.target.value === "cpu" ? "cpu" : "auto")} disabled={inputsLocked} className={selectClass}><option value="auto">Automatic · Prefer GPU</option><option value="cpu">CPU · Slow fallback</option></select></div>
                <div className="space-y-1.5"><Label htmlFor="theme-steps" className="text-xs">Steps</Label><Input id="theme-steps" type="number" min={1} max={50} step={1} value={steps} onChange={event => setSteps(event.target.value)} disabled={inputsLocked} /></div>
                <div className="space-y-1.5"><Label htmlFor="theme-seed" className="text-xs">Seed</Label><Input id="theme-seed" type="number" min={0} max={2147483647} step={1} value={seed} onChange={event => setSeed(event.target.value)} disabled={inputsLocked} /></div>
              </div>
              {!validSettings && <p className="text-xs text-amber-300">Use 1–50 steps and a whole-number seed from 0 to 2147483647.</p>}
              <p className="text-[11px] leading-relaxed text-muted-foreground">Automatic adjusts model placement to available GPU memory for both enhancement and editing. Preview uses less memory. Start with one card to measure speed on your hardware.</p>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex-1 text-[11px] leading-relaxed text-muted-foreground">The editor stays loaded for faster repeats and unloads after five idle minutes.</p>
                <Button variant="ghost" size="sm" disabled={!api || busy} onClick={() => {
                  if (api) void execute("release-memory", async () => {
                    await api.deck_theme_release_memory()
                    setNotice("Loaded editor models released. The next generation will load them again.")
                  })
                }}>Release model memory</Button>
              </div>
              <Button className="h-10 w-full bg-emerald-400 text-zinc-950 hover:bg-emerald-300" disabled={!api || !card || !prompt.trim() || !theme.trim() || promptNeedsUpdate || busy || !status?.editor.ready || !status.platform_supported || !validSettings} onClick={generateEdit}>{pending === "edit" || (running && job.kind === "edit") ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Generate edit</Button>
              {!status?.editor.ready && <p className="text-center text-[11px] text-muted-foreground"><button type="button" onClick={() => setSetupOpen(true)} className="underline underline-offset-2 hover:text-foreground">Set up the image editor</button> to enable generation.</p>}

              {result?.result?.image && (
                <div className="space-y-2 border-t pt-3">
                  {typeof result.result.elapsed_seconds === "number" && <p className="text-xs text-emerald-300">Generated in {result.result.elapsed_seconds >= 60 ? `${Math.floor(result.result.elapsed_seconds / 60)}m ${Math.round(result.result.elapsed_seconds % 60)}s` : `${result.result.elapsed_seconds.toFixed(1)}s`}</p>}
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="sm" onClick={saveResult} disabled={busy}><Download className="size-3.5" /> Save image</Button>
                    <Button variant="outline" size="sm" onClick={copyOutputPath} disabled={busy || !result.result.output_path}><Copy className="size-3.5" /> Copy path</Button>
                    <Button variant="outline" size="sm" disabled={busy || !result.result.output_folder} onClick={() => { if (result.result?.output_folder) onUseInPrint(result.result.output_folder) }}>Use in Print Setup</Button>
                  </div>
                  <p className="text-[11px] text-muted-foreground">The generated image is already saved locally. Save image makes an additional copy.</p>
                </div>
              )}
            </section>
          </div>
        </TabsContent>

        <TabsContent value="deck" className="m-0">
          <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed bg-muted/10 p-8 text-center">
            <span className="mb-4 rounded-2xl border bg-muted/30 p-4"><Layers className="size-7 text-muted-foreground" /></span>
            <h3 className="text-base font-medium">A whole deck. One theme.</h3>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">Deck generation is planned. Use Single Card to test the image editor and find a theme you like first.</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
