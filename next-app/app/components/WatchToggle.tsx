"use client";

import { Eye, EyeOff } from "lucide-react";

interface WatchToggleProps {
  active: boolean;
  lastChecked: string | null;
  onToggle: () => void;
  disabled: boolean;
}

export default function WatchToggle({
  active,
  lastChecked,
  onToggle,
  disabled,
}: WatchToggleProps) {
  return (
    <footer className="flex items-center justify-between px-6 py-2.5 border-t border-border bg-surface/80 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggle}
          disabled={disabled}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            active
              ? "bg-accent/20 text-accent border border-accent/30"
              : "bg-surface-2 text-muted border border-border hover:text-foreground"
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {active ? (
            <Eye className="h-3.5 w-3.5" />
          ) : (
            <EyeOff className="h-3.5 w-3.5" />
          )}
          {active ? "Autonomous Watch: ON" : "Autonomous Watch: OFF"}
        </button>
        {active && (
          <span className="text-xs text-muted font-mono">
            Checking every 5 min
          </span>
        )}
      </div>
      <div className="text-xs text-muted font-mono">
        {lastChecked ? `Last checked: ${lastChecked}` : ""}
      </div>
    </footer>
  );
}
