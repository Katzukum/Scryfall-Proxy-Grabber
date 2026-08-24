import { useState } from "react"
import { Search, Loader2 } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { CardDetailModal } from "./CardDetailModal"

export function CardLookupTab() {
  const { api } = usePywebview();
  
  const [searchMode, setSearchMode] = useState<"name" | "set">("name")
  
  // Name Search
  const [cardName, setCardName] = useState("")
  // Set Search
  const [setCode, setSetCode] = useState("")
  const [collectorNum, setCollectorNum] = useState("")
  
  const [isSearching, setIsSearching] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [selectedCard, setSelectedCard] = useState<any | null>(null)
  
  const handleSearch = async () => {
    if (!api) return;
    
    setIsSearching(true);
    setResults([]);
    
    try {
      let res;
      if (searchMode === "name") {
        res = await api.search_card(cardName);
      } else {
        res = await api.lookup_card(setCode, collectorNum);
      }
      setResults(res || []);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setIsSearching(false);
    }
  }

  const isSearchDisabled = isSearching || !api || 
    (searchMode === "name" ? !cardName.trim() : (!setCode.trim() || !collectorNum.trim()));

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Search Controls */}
      <div className="shrink-0 pb-4 border-b border-border/50 mb-4">
        <Tabs value={searchMode} onValueChange={(val) => setSearchMode(val as any)} className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="name">Search By Name</TabsTrigger>
            <TabsTrigger value="set">Search By Set & Collector #</TabsTrigger>
          </TabsList>
          
          <TabsContent value="name" className="m-0 space-y-3">
            <Label>Card Name</Label>
            <div className="flex gap-2">
              <Input 
                placeholder="e.g. Black Lotus" 
                value={cardName} 
                onChange={(e) => setCardName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !isSearchDisabled && handleSearch()}
              />
              <Button onClick={handleSearch} disabled={isSearchDisabled} className="w-24">
                {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
                {isSearching ? "" : "Search"}
              </Button>
            </div>
          </TabsContent>
          
          <TabsContent value="set" className="m-0 space-y-3">
            <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
              <div className="space-y-1.5">
                <Label>Set Code</Label>
                <Input 
                  placeholder="e.g. mh2" 
                  value={setCode} 
                  onChange={(e) => setSetCode(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !isSearchDisabled && handleSearch()}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Collector #</Label>
                <Input 
                  placeholder="e.g. 1" 
                  value={collectorNum} 
                  onChange={(e) => setCollectorNum(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !isSearchDisabled && handleSearch()}
                />
              </div>
              <Button onClick={handleSearch} disabled={isSearchDisabled} className="w-24">
                {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
                {isSearching ? "" : "Search"}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Results Area */}
      <div className="flex-1 overflow-hidden min-h-[350px] relative">
        <ScrollArea className="h-full">
          {!results.length ? (
            <div className="h-[350px] flex items-center justify-center text-muted-foreground text-sm border rounded-md border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/20">
              {isSearching ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
                  <span>Searching Scryfall...</span>
                </div>
              ) : "Search for a card to see all versions"}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 p-1">
              {results.map((card, idx) => (
                <div 
                  key={`${card.set_code}-${card.collector_number}-${idx}`}
                  className="group relative aspect-[2.5/3.5] rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-900 cursor-pointer transition-all duration-200 hover:scale-[1.03] hover:shadow-xl hover:z-10"
                  onClick={() => setSelectedCard(card)}
                >
                  {card.image_url_small ? (
                    <img 
                      src={card.image_url_small} 
                      alt={card.name}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full p-2 text-center">
                      <span className="text-[10px] font-bold uppercase text-zinc-500">{card.name}</span>
                      <span className="text-[9px] text-zinc-600">{card.set_code} #{card.collector_number}</span>
                    </div>
                  )}
                  {/* Hover Overlay */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-end p-2 opacity-0 group-hover:opacity-100">
                    <div className="w-full bg-black/60 backdrop-blur-sm rounded p-1.5 text-center">
                      <p className="text-[9px] font-medium text-white truncate">{card.name}</p>
                      <p className="text-[8px] text-zinc-300 uppercase">{card.set_code} • {card.collector_number}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      <CardDetailModal 
        card={selectedCard}
        isOpen={!!selectedCard}
        onClose={() => setSelectedCard(null)}
      />
    </div>
  )
}
