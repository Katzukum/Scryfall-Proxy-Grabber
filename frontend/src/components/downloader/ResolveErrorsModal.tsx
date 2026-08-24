import { useEffect, useMemo, useState } from "react"
import { AlertCircle, Download, Loader2, Search } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"

interface ResolveErrorsModalProps {
  isOpen: boolean
  onClose: () => void
  orderName: string
}

export function ResolveErrorsModal({ isOpen, onClose, orderName }: ResolveErrorsModalProps) {
  const { api } = usePywebview()
  const [errorCards, setErrorCards] = useState<string[]>([])
  const [selectedErrorCard, setSelectedErrorCard] = useState<string>("")
  const [searchQuery, setSearchQuery] = useState<string>("")
  const [results, setResults] = useState<any[]>([])
  const [downloadCount, setDownloadCount] = useState<number>(1)
  const [isLoadingErrors, setIsLoadingErrors] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)

  useEffect(() => {
    if (!isOpen || !api || !orderName.trim()) {
      return
    }

    let cancelled = false
    const loadErrors = async () => {
      setIsLoadingErrors(true)
      setResults([])
      setSelectedErrorCard("")
      setSearchQuery("")
      try {
        const cards = await api.get_error_cards(orderName)
        if (!cancelled) {
          setErrorCards(cards || [])
        }
      } catch (err) {
        console.error("Failed to load error cards:", err)
        if (!cancelled) {
          setErrorCards([])
        }
      } finally {
        if (!cancelled) {
          setIsLoadingErrors(false)
        }
      }
    }

    loadErrors()
    return () => {
      cancelled = true
    }
  }, [api, isOpen, orderName])

  const canSearch = !!api && !!searchQuery.trim() && !isSearching
  const hasErrorCards = errorCards.length > 0
  const trimmedOrderName = useMemo(() => orderName.trim(), [orderName])

  const runSearch = async (query?: string) => {
    if (!api) return
    const effectiveQuery = (query ?? searchQuery).trim()
    if (!effectiveQuery) return

    setIsSearching(true)
    setResults([])
    try {
      const found = await api.search_card(effectiveQuery)
      setResults(found || [])
    } catch (err) {
      console.error("Card search failed:", err)
    } finally {
      setIsSearching(false)
    }
  }

  const handleSelectErrorCard = async (name: string) => {
    setSelectedErrorCard(name)
    setSearchQuery(name)
    await runSearch(name)
  }

  const handleDownload = async (card: any) => {
    if (!api || !trimmedOrderName || !card?.raw_json) return
    setIsDownloading(true)
    try {
      await api.download_single_card(card.raw_json, Math.max(1, downloadCount), trimmedOrderName)
    } catch (err) {
      console.error("Single card download failed:", err)
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[95vw] lg:max-w-6xl max-h-[92vh] overflow-hidden p-0">
        <DialogHeader className="p-4 border-b border-border/50">
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Resolve Download Errors
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] h-[75vh]">
          <div className="border-r border-border/50 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Label>Errored Cards</Label>
              <Badge variant="secondary">{errorCards.length}</Badge>
            </div>
            <ScrollArea className="h-[calc(75vh-120px)] pr-2">
              <div className="space-y-1">
                {isLoadingErrors && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading error list...
                  </div>
                )}
                {!isLoadingErrors && !hasErrorCards && (
                  <p className="text-sm text-muted-foreground py-2">No unresolved errors found for this order.</p>
                )}
                {!isLoadingErrors && errorCards.map((cardName) => (
                  <Button
                    key={cardName}
                    variant={selectedErrorCard === cardName ? "default" : "ghost"}
                    className="w-full justify-start text-left h-auto py-2 px-3 whitespace-normal"
                    onClick={() => void handleSelectErrorCard(cardName)}
                  >
                    {cardName}
                  </Button>
                ))}
              </div>
            </ScrollArea>
          </div>

          <div className="p-4 flex flex-col min-h-0 gap-3">
            <div className="space-y-2">
              <Label>Search Card By Name</Label>
              <div className="flex gap-2">
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Select from left or type a card name..."
                  onKeyDown={(e) => e.key === "Enter" && canSearch && void runSearch()}
                />
                <Button onClick={() => void runSearch()} disabled={!canSearch} className="w-28">
                  {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
                  {isSearching ? "" : "Search"}
                </Button>
              </div>
            </div>

            <div className="w-40 space-y-1">
              <Label htmlFor="resolve-download-count">Copies</Label>
              <Input
                id="resolve-download-count"
                type="number"
                min={1}
                max={100}
                value={downloadCount}
                onChange={(e) => setDownloadCount(parseInt(e.target.value, 10) || 1)}
              />
            </div>

            <Separator />

            <div className="flex-1 min-h-0">
              <ScrollArea className="h-full pr-2">
                {!results.length ? (
                  <div className="h-[220px] flex items-center justify-center text-muted-foreground text-sm border rounded-md border-dashed">
                    {isSearching ? "Searching..." : "Pick a card on the left to search versions"}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3 p-1">
                    {results.map((card, idx) => (
                      <div
                        key={`${card.set_code}-${card.collector_number}-${idx}`}
                        className="group border rounded-md overflow-hidden bg-card"
                      >
                        <div className="aspect-[2.5/3.5] w-full bg-muted/30">
                          {card.image_url_small ? (
                            <img src={card.image_url_small} alt={card.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-muted-foreground px-2 text-center">
                              No Preview
                            </div>
                          )}
                        </div>
                        <div className="p-2 space-y-1">
                          <p className="text-xs font-medium leading-tight line-clamp-2 min-h-8">{card.name}</p>
                          <p className="text-[10px] text-muted-foreground uppercase">
                            {card.set_code} #{card.collector_number}
                          </p>
                          <Button
                            size="sm"
                            className="w-full"
                            onClick={() => void handleDownload(card)}
                            disabled={isDownloading || !trimmedOrderName}
                          >
                            {isDownloading ? (
                              <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            ) : (
                              <Download className="h-4 w-4 mr-2" />
                            )}
                            Download
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
