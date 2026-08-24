# Add a New Tab

This guide explains how to extend ProxyToolBox by adding a new tab to the frontend and connecting it to a new backend module, following the existing architectural patterns. We will use the **Downloader** tab as our reference example.

The process involves three main steps:
1. Creating the Frontend Component
2. Registering the Tab in the App Layout
3. Exposing the Python Backend API

---

## 1. Create the Frontend Component

The UI is built using React, Vite, and shadcn/ui. Tab components live in specific feature directories under `frontend/src/components/`.

Create a new file for your tab (e.g., `frontend/src/components/my-feature/MyFeatureTab.tsx`).

### Following the Pattern
Like the `DownloaderTab`, your component should:
- Access the `api` object via the `usePywebview` hook.
- Maintain its own local state using standard `useState`.
- Disable interactivity during async operations.
- Intercept the `window.__onTaskComplete` event to reset loading states when background python processes finish.

```tsx
// frontend/src/components/downloader/DownloaderTab.tsx (Example Snippet)
import { useState, useEffect } from "react"
import { Download, Loader2 } from "lucide-react"
import { usePywebview } from "@/hooks/usePywebview"
import { Button } from "@/components/ui/button"

export function DownloaderTab() {
  const { api } = usePywebview();
  const [deckList, setDeckList] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    // Intercept Python task completion signal
    const originalOnTaskComplete = window.__onTaskComplete;
    
    window.__onTaskComplete = (result) => {
      if (isDownloading) {
         setIsDownloading(false);
      }
      if (originalOnTaskComplete) originalOnTaskComplete(result);
    };

    return () => {
      window.__onTaskComplete = originalOnTaskComplete;
    }
  }, [isDownloading]);

  const handleStartDownload = () => {
    if (!api || !deckList.trim()) return;

    setIsDownloading(true);
    
    // Call the Python backend method matching src/api.py
    api.start_download("Order_Name", deckList, false, false).catch((err) => {
      console.error(err);
      setIsDownloading(false);
    });
  }

  return (
    <div className="flex flex-col gap-6 p-1 h-full">
      {/* Inputs... */}
      <Button onClick={handleStartDownload} disabled={isDownloading}>
        {isDownloading ? <Loader2 className="animate-spin" /> : <Download />}
        Start
      </Button>
    </div>
  )
}
```

---

## 2. Register the Tab in the App Layout

Once the component is built, integrate it into the main layout located at `frontend/src/App.tsx`.

1. Import your new component.
2. Add a new `TabsTrigger` definition. Remember to update the `grid-cols-*` class on the `TabsList` to ensure equal spacing (e.g., change `grid-cols-3` to `grid-cols-4`).
3. Add the corresponding `TabsContent` wrapper.

```tsx
// frontend/src/App.tsx

// 1. Import
import { DownloaderTab } from "@/components/downloader/DownloaderTab"
import { MyFeatureTab } from "@/components/my-feature/MyFeatureTab" // <-- New
import { Sparkles } from "lucide-react" // Icon

function App() {
  // ...
  return (
    // ...
    <TabsList className="grid w-full grid-cols-4 mb-6"> {/* Update cols to 4 */}
      <TabsTrigger value="downloader"><DownloadCloud /> Download Cards</TabsTrigger>
      {/* ... other triggers ... */}
      <TabsTrigger value="my_feature"><Sparkles /> My Feature</TabsTrigger> {/* <-- New */}
    </TabsList>
    
    <div className="flex-1 overflow-hidden border rounded-lg bg-card text-card-foreground shadow-sm">
      <TabsContent value="downloader" className="m-0 h-full p-4 overflow-y-auto w-full">
        <DownloaderTab />
      </TabsContent>
      {/* ... other content ... */}
      <TabsContent value="my_feature" className="m-0 h-full p-4 overflow-y-auto w-full">
        <MyFeatureTab /> {/* <-- New */}
      </TabsContent>
    </div>
    // ...
  )
}
```

---

## 3. Exposing the Python Backend API

For the frontend button to do anything, there must be a corresponding method exposed to the `pywebview` window. All bridge methods are defined in `src/api.py` and must not freeze the application loop.

### The Backend Pattern
When implementing methods (like `start_download`) in the `Api` class:
1. Wrap long-running tasks in an inner `_run()` function.
2. Spawn a background `threading.Thread` so the Python UI doesn't block.
3. If calling `asyncio` code, create a new event loop for that background thread.
4. Pass standard internal callbacks (`on_progress`, `on_log`) which the `Api` maps to frontend interface updates (`_push_progress`, `_push_log`).
5. Safely conclude the thread with `_push_task_complete`.

```python
# src/api.py

import threading
import asyncio

class Api:
    # ... previous initialization ...

    # The exact signature called from standard TS
    def start_download(self, order_name: str, card_list_text: str, include_tokens: bool = False, dual_face_token: bool = False) -> None:
        """Example implementation from the Downloader."""
        
        # 1. Define the isolated task
        def _run() -> None:
            try:
                # 2. Push log updates to the console UI
                self._push_log("INFO", "Starting download...")

                # 3. Create Event Loop for async tasks (e.g., httpx Scryfall client)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    download_card_images(
                        # ...
                        on_progress=self._push_progress, # Feeds the progress bar automatically
                        on_log=self._push_log,
                    )
                )
                loop.close()

                # 4. Success — triggers frontend un-disable
                self._push_task_complete({"success": True, **result})
                
            except Exception as e:
                self._push_log("ERROR", f"Critical error: {e}")
                
                # 5. Failure — triggers frontend un-disable
                self._push_task_complete({"success": False, "error": str(e)})

        # 6. Execute task as a Daemon Thread without awaiting
        threading.Thread(target=_run, daemon=True).start()
```

By adhering to this pattern, your new modules will transparently hook right into the UI's existing loader bars, console logging system, and responsive state.
