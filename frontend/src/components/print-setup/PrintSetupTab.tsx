import { useState, useEffect } from "react"
import { FileOutput, FolderOpen, Loader2 } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card, CardContent } from "@/components/ui/card"

interface PrintSetupTabProps {
  folderPath: string
  onFolderPathChange: (folderPath: string) => void
}

export function PrintSetupTab({ folderPath, onFolderPathChange }: PrintSetupTabProps) {
  const { api } = usePywebview();
  const [cardWidth, setCardWidth] = useState("63.0")
  const [cardHeight, setCardHeight] = useState("88.0")
  const [cornerRadius, setCornerRadius] = useState("2.5")
  const [padding, setPadding] = useState("2.0")
  const [outputFormat, setOutputFormat] = useState("pdf")
  const [isTransformer, setIsTransformer] = useState(false)
  
  const [isProcessing, setIsProcessing] = useState(false)

  // Load defaults from Python on mount
  useEffect(() => {
    if (api) {
      api.get_default_settings().then((defaults) => {
        if (defaults) {
          setCardWidth(defaults.card_width_mm.toString());
          setCardHeight(defaults.card_height_mm.toString());
          setCornerRadius(defaults.corner_radius_mm.toString());
          setPadding(defaults.padding_mm.toString());
        }
      }).catch(console.error);
    }
  }, [api]);

  useEffect(() => {
    const originalOnTaskComplete = window.__onTaskComplete;
    window.__onTaskComplete = (result: any) => {
      if (isProcessing) setIsProcessing(false);
      if (originalOnTaskComplete) originalOnTaskComplete(result);
    };
    return () => {
      window.__onTaskComplete = originalOnTaskComplete;
    }
  }, [isProcessing]);

  const handleBrowse = async () => {
    if (!api) return;
    try {
      const selectedFolder = await api.browse_folder();
      if (selectedFolder) onFolderPathChange(selectedFolder);
    } catch (e) {
      console.error(e);
    }
  }

  const handleCreate = () => {
    if (!api || !folderPath) return;
    setIsProcessing(true);
    
    api.create_output(
      folderPath,
      parseFloat(cardWidth),
      parseFloat(cardHeight),
      parseFloat(cornerRadius),
      parseFloat(padding),
      outputFormat,
      isTransformer
    ).catch((err) => {
      console.error(err);
      setIsProcessing(false);
    });
  }

  return (
    <div className="flex flex-col gap-6 p-1">
      {/* Folder Selection */}
      <div className="space-y-3">
        <Label>Image Folder</Label>
        <div className="flex gap-2">
          <Input 
            value={folderPath} 
            onChange={(e) => onFolderPathChange(e.target.value)} 
            placeholder="Select a folder containing card images..."
            disabled={isProcessing}
          />
          <Button variant="secondary" onClick={handleBrowse} disabled={isProcessing || !api}>
            <FolderOpen className="mr-2 h-4 w-4" />
            Browse
          </Button>
        </div>
      </div>

      {/* Dimensions Grid */}
      <Card className="bg-zinc-50/50 dark:bg-zinc-900/50 border-zinc-200 dark:border-zinc-800 shadow-none">
        <CardContent className="p-4 grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="width" className="text-xs">Width (mm)</Label>
            <Input id="width" type="number" step="0.1" value={cardWidth} onChange={(e) => setCardWidth(e.target.value)} disabled={isProcessing} className="h-8" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="height" className="text-xs">Height (mm)</Label>
            <Input id="height" type="number" step="0.1" value={cardHeight} onChange={(e) => setCardHeight(e.target.value)} disabled={isProcessing} className="h-8" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="corner" className="text-xs">Corner Radius (mm)</Label>
            <Input id="corner" type="number" step="0.1" value={cornerRadius} onChange={(e) => setCornerRadius(e.target.value)} disabled={isProcessing} className="h-8" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="padding" className="text-xs">Padding (mm)</Label>
            <Input id="padding" type="number" step="0.1" value={padding} onChange={(e) => setPadding(e.target.value)} disabled={isProcessing} className="h-8" />
          </div>
        </CardContent>
      </Card>

      {/* Output Settings */}
      <div className="flex items-center gap-6">
        <div className="space-y-3 flex-1">
          <Label>Output Format</Label>
          <Select value={outputFormat} onValueChange={setOutputFormat} disabled={isProcessing}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pdf">PDF Document (*.pdf)</SelectItem>
              <SelectItem value="png">PNG Image Sheets (*.png)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <div className="space-y-3 flex-1 pt-1">
          <div className="flex items-center space-x-2 border rounded-md px-3 py-2 bg-background shadow-sm">
            <Switch 
              id="transformer-mode" 
              checked={isTransformer}
              onCheckedChange={setIsTransformer}
              disabled={isProcessing}
            />
            <Label htmlFor="transformer-mode" className="cursor-pointer text-sm font-normal">
              Two-Sided (Transformers)
            </Label>
          </div>
          {isTransformer && (
            <p className="text-[10px] text-muted-foreground px-1 -mt-1 leading-tight">
              Requires a <code>/transformers</code> subfolder
            </p>
          )}
        </div>
      </div>

      <div className="mt-2">
        <Button 
          onClick={handleCreate} 
          disabled={isProcessing || !folderPath || !api}
          className="w-full"
        >
          {isProcessing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Processing...
            </>
          ) : (
            <>
              <FileOutput className="mr-2 h-4 w-4" />
              Create Document
            </>
          )}
        </Button>
      </div>
    </div>
  )
}
