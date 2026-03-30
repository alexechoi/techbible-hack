"use client";

import { Activity } from "lucide-react";

interface HeaderProps {
  isActive: boolean;
}

export default function Header({ isActive }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface/80 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-accent" />
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            ArbitrageAgent
          </h1>
        </div>
        <span className="text-xs text-muted font-mono">
          Cross-Border Amazon Price Intelligence
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            isActive
              ? "bg-accent animate-pulse-glow"
              : "bg-muted"
          }`}
        />
        <span className="text-xs text-muted font-mono">
          {isActive ? "SCANNING" : "IDLE"}
        </span>
      </div>
    </header>
  );
}
