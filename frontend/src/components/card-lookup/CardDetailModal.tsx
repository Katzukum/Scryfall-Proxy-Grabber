import { useState } from "react"
import { Download, FolderOpen, Loader2 } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { CollapsibleJsonViewer } from "./CollapsibleJsonViewer"

interface CardDetailModalProps {
  card: any | null
  isOpen: boolean
  onClose: () => void
}

export function CardDetailModal({ card, isOpen, onClose }: CardDetailModalProps) {
  const { api } = usePywebview()
  const [downloadCount, setDownloadCount] = useState(1)
  const [targetFolder, setTargetFolder] = useState("")
  const [isDownloading, setIsDownloading] = useState(false)

  if (!card) return null

  const handleBrowseFolder = async () => {
    if (!api) return
    const folder = await api.browse_folder()
    if (folder) setTargetFolder(folder)
  }

  const handleDownload = async () => {
    if (!api || !targetFolder || !card) return
    
    setIsDownloading(true)
    try {
      await api.download_single_card(card.raw_json, downloadCount, targetFolder)
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[95vw] lg:max-w-6xl max-h-[95vh] overflow-hidden flex flex-col p-0 bg-zinc-950 border-zinc-800">
        <DialogHeader className="p-4 border-b border-zinc-800 shrink-0">
          <DialogTitle className="text-zinc-100 flex items-center justify-between">
            <span>{card.name}</span>
            {card.set_code && (
              <span className="text-sm font-normal text-zinc-500 mr-6">
                {card.set_code.toUpperCase()} #{card.collector_number}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>
        
        <div className="flex-1 p-4">
          <div className="flex flex-col md:flex-row gap-6">
            {/* Large Image */}
            <div className="w-full md:w-[350px] shrink-0">
              <div className="aspect-[2.5/3.5] relative rounded-xl overflow-hidden shadow-2xl bg-zinc-900 border border-zinc-800">
                {card.image_url ? (
                  <img 
                    src={card.image_url} 
                    alt={card.name}
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-zinc-600 text-sm">
                    No Preview Available
                  </div>
                )}
              </div>
            </div>

            {/* Details and Actions */}
            <div className="flex-1 flex flex-col min-h-0 min-w-0 space-y-4">
              {/* Download Section - NOW ON TOP */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                  <Download className="h-4 w-4" />
                  Download Large Image
                </h3>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="download-count" className="text-zinc-400 text-xs">Copies to save</Label>
                    <Input 
                      id="download-count"
                      type="number"
                      min={1}
                      max={100}
                      value={downloadCount}
                      onChange={(e) => setDownloadCount(parseInt(e.target.value) || 1)}
                      className="bg-zinc-900 border-zinc-800 text-zinc-100 h-9"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label className="text-zinc-400 text-xs">Target Folder</Label>
                    <div className="flex gap-2">
                      <Input 
                        readOnly 
                        placeholder="No folder selected" 
                        value={targetFolder}
                        className="bg-zinc-900 border-zinc-800 text-zinc-300 text-[10px] h-9 truncate"
                      />
                      <Button 
                        size="icon" 
                        variant="secondary"
                        className="shrink-0 h-9 w-9"
                        onClick={handleBrowseFolder}
                      >
                        <FolderOpen className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>

                <Button 
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                  disabled={isDownloading || !targetFolder}
                  onClick={handleDownload}
                >
                  {isDownloading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Download className="h-4 w-4 mr-2" />
                  )}
                  {isDownloading ? "Downloading..." : "Download Large Images"}
                </Button>
                {!targetFolder && (
                  <p className="text-[10px] text-zinc-500 italic text-center">
                    Please select a target folder to enable download
                  </p>
                )}
              </div>

              <Separator className="bg-zinc-800 my-2" />

              <div className="space-y-1">
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Scryfall Links</h3>
                <a 
                  href={card.scryfall_uri} 
                  target="_blank" 
                  rel="noreferrer"
                  className="text-emerald-400 hover:underline text-sm inline-block"
                >
                  View on Scryfall
                </a>
              </div>

              {/* JSON Viewer - INTERNAL WORKING SCROLL */}
              <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar pr-1">
                <CollapsibleJsonViewer data={card.raw_json} />
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
