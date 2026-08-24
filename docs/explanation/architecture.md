# Architecture Overview

ProxyToolBox is a desktop utility application structured with a decoupled frontend/backend architecture, connected via a local bridge.

## High-Level Architecture

```mermaid
graph LR
    A[React/Vite Frontend] <-->|pywebview window object| B[Python Backend]
```

### 1. The Frontend
Developed in React with Vite, styled with `shadcn/ui` and TailwindCSS. The frontend is entirely responsible for state management related to the UI, data presentation, and gathering user input.
It interacts with the system using `window.pywebview.api`.

### 2. The Bridge
The application runs inside a local chromium-based window orchestrated by `pywebview`.
The `Api` backend class (found in `src.api.py`) encapsulates all native system commands and background thread logic. Wait times and I/O processes are pushed to background threads so the UI does not freeze. Events are communicated back to the frontend using the `_push_log`, `_push_progress`, and `_push_task_complete` utility callbacks which invoke globally mounted JS functions.

### 3. The Backend
Written in Python >3.11, the actual work is split into modular domains.

- **Models (`src.models`)**: Pydantic models serve as the strict typings for all data going in and out of the API.
- **Card Lookup (`src.card_lookup`)**: Uses `httpx` to ping Scryfall. Supports fuzzy searching, exact searches (Set Code + Collector Number), and autocomplete features.
- **Downloader (`src.downloader`)**: Parses Moxfield list text files, batches identification requests for Scryfall Collections API limits securely, checks for token existence, manages image downloading asynchronously via asyncio, and organizes images in numbered sequences inside the set directory.
- **Print Setup (`src.print_setup`)**: Renders images using reportlab or the Pillow library. Responsible for gridding cards out on sheet configurations, adding margins and bleeds, and keeping track of standard and double-sided "transformer" layouts.
