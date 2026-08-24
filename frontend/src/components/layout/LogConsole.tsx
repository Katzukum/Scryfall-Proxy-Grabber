import { useState, useEffect, useRef } from "react"
import { Terminal, Trash2, ChevronUp, ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"

export interface LogEntry {
  id: number;
  level: string;
  message: string;
  time: string;
}

export function LogConsole({ isCollapsed, onToggleCollapse }: { isCollapsed: boolean, onToggleCollapse: () => void }) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const logIdCounter = useRef(0)

  useEffect(() => {
    // Register the global callback for pywebview to call
    window.__pushLog = (level: string, message: string) => {
      const now = new Date();
      const timeString = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
      
      const newLog = {
        id: logIdCounter.current++,
        level,
        message,
        time: timeString
      };

      setLogs((prev) => [...prev, newLog]);
    };

    return () => {
        window.__pushLog = undefined;
    }
  }, []);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const getLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR': return 'text-red-400';
      case 'WARN': return 'text-amber-400';
      case 'INFO': return 'text-slate-300';
      default: return 'text-slate-400';
    }
  };

  return (
    <div className={`flex flex-col border rounded-md bg-zinc-950 overflow-hidden shadow-inner ${isCollapsed ? '' : 'h-full'}`}>
      <div 
        className="flex items-center justify-between px-3 py-1.5 bg-zinc-900 border-b border-zinc-800 cursor-pointer hover:bg-zinc-800/80 transition-colors"
        onClick={onToggleCollapse}
      >
        <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
          <Terminal className="w-3.5 h-3.5" />
          <span>Console Output</span>
          {isCollapsed ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
        </div>
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-6 w-6 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            onClick={(e) => {
              e.stopPropagation();
              setLogs([]);
            }}
            title="Clear Console"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
      
      {!isCollapsed && (
        <div 
          ref={scrollRef}
          className="flex-1 p-3 overflow-y-auto font-mono text-xs leading-relaxed min-h-[100px]"
        >
          {logs.length === 0 ? (
            <div className="text-zinc-600 italic">Waiting for output...</div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="mb-1 flex gap-2 break-all">
                <span className="text-zinc-600 shrink-0">[{log.time}]</span>
                <span className={`font-semibold shrink-0 ${getLevelColor(log.level)}`}>
                  {log.level}
                </span>
                <span className="text-zinc-300">{log.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
