"use client";

import { useEffect, useRef } from "react";
import {
  Brain,
  Globe,
  PoundSterling,
  Calculator,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Bell,
} from "lucide-react";

export interface LogEntry {
  type: string;
  message: string;
  timestamp: string;
}

const TYPE_CONFIG: Record<
  string,
  { icon: React.ElementType; color: string; label: string }
> = {
  thinking: { icon: Brain, color: "text-blue-400", label: "THINK" },
  scraping: { icon: Globe, color: "text-cyan-400", label: "SCRAPE" },
  price_found: { icon: PoundSterling, color: "text-emerald-400", label: "PRICE" },
  calculating: { icon: Calculator, color: "text-amber-400", label: "CALC" },
  decision: { icon: CheckCircle2, color: "text-emerald-400", label: "DECIDE" },
  alert: { icon: Bell, color: "text-emerald-300", label: "ALERT" },
  error: { icon: XCircle, color: "text-red-400", label: "ERROR" },
  complete: { icon: CheckCircle2, color: "text-emerald-400", label: "DONE" },
};

interface AgentLogProps {
  entries: LogEntry[];
}

export default function AgentLog({ entries }: AgentLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-border bg-surface-2 flex items-center gap-2">
        <div className="h-3 w-3 rounded-full bg-red-500/70" />
        <div className="h-3 w-3 rounded-full bg-yellow-500/70" />
        <div className="h-3 w-3 rounded-full bg-green-500/70" />
        <span className="ml-2 text-xs text-muted font-mono">agent.log</span>
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-xs bg-black/40"
      >
        {entries.length === 0 && (
          <p className="text-muted/50 italic">
            Paste an Amazon UK URL above to start the agent...
          </p>
        )}
        {entries.map((entry, i) => {
          const config = TYPE_CONFIG[entry.type] || TYPE_CONFIG.thinking;
          const Icon = config.icon;
          return (
            <div
              key={i}
              className="flex items-start gap-2 animate-fade-in"
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <span className="text-muted/50 shrink-0 w-16 text-right">
                {entry.timestamp}
              </span>
              <span
                className={`shrink-0 w-16 text-right font-semibold ${config.color}`}
              >
                {config.label}
              </span>
              <Icon className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${config.color}`} />
              <span className="text-zinc-300 break-all">{entry.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
