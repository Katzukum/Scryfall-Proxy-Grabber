import { APP_VERSION } from "../../version"

export function AppHeader() {
  return (
    <div className="flex items-center gap-2 px-6 py-4 border-b border-border/50 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="overflow-hidden rounded-md border border-border/60 shadow-sm">
        <img
          src="/proxytoolbox-logo-option-2a.svg"
          alt="ProxyToolBox logo"
          className="h-8 w-8"
        />
      </div>
      <div>
        <h1 className="font-semibold text-lg leading-tight">ProxyToolBox</h1>
        <p className="text-xs text-muted-foreground font-medium">v{APP_VERSION}</p>
      </div>
    </div>
  )
}
