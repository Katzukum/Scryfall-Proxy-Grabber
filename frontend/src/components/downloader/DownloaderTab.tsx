import { useState, useEffect } from "react"
import { Download, Loader2 } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { ResolveErrorsModal } from "./ResolveErrorsModal"

interface DownloaderTabProps {
  onDownloadComplete?: (folderPath: string) => void
}

export function DownloaderTab({ onDownloadComplete }: DownloaderTabProps) {
  const { api } = usePywebview();
  const [orderName, setOrderName] = useState("My_Proxy_Order")
  const [deckList, setDeckList] = useState("")
  const [includeTokens, setIncludeTokens] = useState(false)
  const [dualFaceToken, setDualFaceToken] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [isResolveErrorsOpen, setIsResolveErrorsOpen] = useState(false)
  
  // Count lines that look like cards
  const cardCount = deckList.split('\n').filter(line => line.trim().length > 0).length

  useEffect(() => {
    // Register the task completion handler for this tab
    // We only care if we are currently downloading
    const originalOnTaskComplete = window.__onTaskComplete;
    
    window.__onTaskComplete = (result: any) => {
      // If there's an original handler, you might want to call it, but in our case
      // we just want to reset loading state
      if (isDownloading) {
         setIsDownloading(false);
         if (result?.success && orderName.trim()) {
          onDownloadComplete?.(orderName.trim());
         }
         // You could also show a toast notification here
      }
      if (originalOnTaskComplete) {
         originalOnTaskComplete(result);
      }
    };

    return () => {
      window.__onTaskComplete = originalOnTaskComplete;
    }
  }, [isDownloading, onDownloadComplete, orderName]);

  // Handle include tokens toggle side-effects
  const handleIncludeTokensChange = (checked: boolean) => {
    setIncludeTokens(checked);
    if (!checked) {
      setDualFaceToken(false);
    }
  };

  const handleStartDownload = () => {
    if (!api) return;
    if (!orderName.trim() || !deckList.trim()) return;

    setIsDownloading(true);
    // Call the python backend
    api.start_download(orderName, deckList, includeTokens, dualFaceToken).catch((err) => {
      console.error(err);
      setIsDownloading(false);
    });
  }

  return (
    <div className="flex flex-col gap-6 p-1 h-full">
      <div className="space-y-3 shrink-0">
        <Label htmlFor="order-name">Order / Folder Name</Label>
        <Input 
          id="order-name" 
          value={orderName} 
          onChange={(e) => setOrderName(e.target.value)} 
          placeholder="e.g. Modern_Burn"
          disabled={isDownloading}
        />
      </div>
      
      <div className="flex flex-row gap-4 flex-1 min-h-0">
        {/* Left Side: Deck List */}
        <div className="flex flex-col gap-3 flex-1 min-h-0">
          <div className="flex items-center justify-between shrink-0">
            <Label htmlFor="decklist">Paste Deck List</Label>
            <Badge variant="secondary" className="font-normal text-xs px-2 py-0.5">
              {cardCount} {cardCount === 1 ? 'card' : 'cards'}
            </Badge>
          </div>
          <Textarea 
            id="decklist"
            className="flex-1 font-mono text-xs resize-none"
            placeholder={"1 Sol Ring (C14) 55\n2 Lightning Bolt (M10) 146"}
            value={deckList}
            onChange={(e) => setDeckList(e.target.value)}
            disabled={isDownloading}
          />
        </div>

        <Separator orientation="vertical" className="h-full" />

        {/* Right Side: Options that can grow */}
        <div className="flex flex-col gap-6 w-64 shrink-0">
          <div className="space-y-4">
            <h3 className="font-semibold text-sm">Download Options</h3>
            
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="include-tokens" className="text-sm font-medium">Include Tokens</Label>
                <div className="text-[10px] text-muted-foreground leading-tight max-w-[150px]">
                  Fetch token cards related to deck.
                </div>
              </div>
              <Switch
                id="include-tokens"
                checked={includeTokens}
                onCheckedChange={handleIncludeTokensChange}
                disabled={isDownloading}
              />
            </div>

            <div className="flex items-center justify-between opacity-100 transition-opacity" style={{ opacity: includeTokens ? 1 : 0.5 }}>
              <div className="space-y-0.5">
                <Label htmlFor="dual-face-token" className="text-sm font-medium">Dual Face Token</Label>
                <div className="text-[10px] text-muted-foreground leading-tight max-w-[150px]">
                  Pair tokens for 2-sided transformer printing.
                </div>
              </div>
              <Switch
                id="dual-face-token"
                checked={dualFaceToken}
                onCheckedChange={setDualFaceToken}
                disabled={!includeTokens || isDownloading}
              />
            </div>
          </div>

          <Button 
            onClick={handleStartDownload} 
            disabled={isDownloading || !orderName.trim() || !deckList.trim() || !api}
            className="w-full mt-auto"
          >
            {isDownloading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Downloading...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Start Download
              </>
            )}
          </Button>
          <Button
            variant="outline"
            className="w-full"
            disabled={isDownloading || !orderName.trim() || !api}
            onClick={() => setIsResolveErrorsOpen(true)}
          >
            Resolve Errors
          </Button>
        </div>
      </div>
      <ResolveErrorsModal
        isOpen={isResolveErrorsOpen}
        onClose={() => setIsResolveErrorsOpen(false)}
        orderName={orderName}
      />
    </div>
  )
}
