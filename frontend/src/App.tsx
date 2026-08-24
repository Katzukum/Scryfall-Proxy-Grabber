import { useState, useEffect } from "react"
import { DownloadCloud, FileOutput, SearchCheck } from "lucide-react"

import { usePywebview } from "@/hooks/usePywebview"
import { AppHeader } from "@/components/layout/AppHeader"
import { LogConsole } from "@/components/layout/LogConsole"
import { ProgressBar } from "@/components/layout/ProgressBar"
import { DownloaderTab } from "@/components/downloader/DownloaderTab"
import { PrintSetupTab } from "@/components/print-setup/PrintSetupTab"
import { CardLookupTab } from "@/components/card-lookup/CardLookupTab"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"

function App() {
  const { isReady } = usePywebview();
  const [activeTab, setActiveTab] = useState("downloader");
  const [isLogCollapsed, setIsLogCollapsed] = useState(true);
  const [printFolderPath, setPrintFolderPath] = useState("");

  // Setting the dark theme class
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  if (!isReady) {
    return (
      <div className="h-screen w-screen flex flex-col items-center justify-center bg-background text-muted-foreground gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
        <p className="text-sm font-medium animate-pulse">Initializing pywebview bridge...</p>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-background text-foreground overflow-hidden font-sans">
      <AppHeader />
      
      <main className="flex-1 p-6 flex flex-col gap-6 overflow-hidden min-h-0">
        <div className="flex-1 overflow-hidden">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
            <TabsList className="grid w-full grid-cols-3 mb-6 bg-zinc-100/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 shrink-0">
              <TabsTrigger value="downloader" className="flex items-center gap-2">
                <DownloadCloud className="w-4 h-4" /> Download Cards
              </TabsTrigger>
              <TabsTrigger value="print" className="flex items-center gap-2">
                <FileOutput className="w-4 h-4" /> Print Setup
              </TabsTrigger>
              <TabsTrigger value="lookup" className="flex items-center gap-2">
                <SearchCheck className="w-4 h-4" /> Card Lookup
              </TabsTrigger>
            </TabsList>
            
            <div className="flex-1 overflow-hidden border rounded-lg bg-card text-card-foreground shadow-sm">
              <TabsContent value="downloader" className="m-0 h-full p-4 overflow-y-auto w-full">
                <DownloaderTab onDownloadComplete={setPrintFolderPath} />
              </TabsContent>
              <TabsContent value="print" className="m-0 h-full p-4 overflow-y-auto w-full">
                <PrintSetupTab folderPath={printFolderPath} onFolderPathChange={setPrintFolderPath} />
              </TabsContent>
              <TabsContent value="lookup" className="m-0 h-full p-4 overflow-y-auto w-full">
                <CardLookupTab />
              </TabsContent>
            </div>
          </Tabs>
        </div>
        
        {/* Persistent bottom area */}
        <div className={`shrink-0 flex flex-col gap-2 transition-[height] duration-200 ${isLogCollapsed ? 'h-auto' : 'h-[35%] min-h-[150px]'}`}>
          <ProgressBar />
          <div className="flex-1 min-h-0">
            <LogConsole isCollapsed={isLogCollapsed} onToggleCollapse={() => setIsLogCollapsed(!isLogCollapsed)} />
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
