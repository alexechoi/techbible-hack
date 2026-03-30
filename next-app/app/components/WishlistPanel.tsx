"use client";

import { useState } from "react";
import {
  Plus,
  Trash2,
  Play,
  Loader2,
  TrendingDown,
  ShieldCheck,
} from "lucide-react";

interface WishlistItem {
  asin: string;
  url: string;
  title: string;
  status: string;
  verdict: string | null;
  savings_pct: number | null;
  savings_gbp: number | null;
  best_country: string | null;
  uk_price: number | null;
  best_landed_cost: number | null;
}

interface WishlistPanelProps {
  items: WishlistItem[];
  onAdd: (url: string) => void;
  onRemove: (asin: string) => void;
  onScanAll: () => void;
  isScanning: boolean;
}

export default function WishlistPanel({
  items,
  onAdd,
  onRemove,
  onScanAll,
  isScanning,
}: WishlistPanelProps) {
  const [url, setUrl] = useState("");

  const handleAdd = () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setUrl("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-border bg-surface-2 flex items-center justify-between">
        <span className="text-xs text-muted font-mono">
          WISHLIST ({items.length})
        </span>
        <button
          onClick={onScanAll}
          disabled={isScanning || items.length === 0}
          className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-accent text-black text-xs font-semibold hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isScanning ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Play className="h-3 w-3" />
          )}
          {isScanning ? "Scanning..." : "Scan All"}
        </button>
      </div>

      {/* Add URL input */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-surface">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="Paste Amazon UK URL to add..."
          className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted/50 outline-none font-mono"
        />
        <button
          onClick={handleAdd}
          disabled={!url.trim()}
          className="p-1 rounded hover:bg-zinc-800 text-muted hover:text-accent disabled:opacity-30 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Items */}
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 && (
          <p className="text-xs text-muted/40 italic p-4 text-center">
            Add products to your wishlist...
          </p>
        )}
        {items.map((item) => (
          <div
            key={item.asin}
            className={`flex items-center gap-3 px-4 py-2.5 border-b border-border/50 text-xs transition-colors ${
              item.verdict === "BUY"
                ? "bg-accent/5"
                : ""
            }`}
          >
            {/* Status indicator */}
            <div className="shrink-0">
              {item.status === "scanning" && (
                <Loader2 className="h-3.5 w-3.5 text-accent animate-spin" />
              )}
              {item.status === "done" && item.verdict === "BUY" && (
                <TrendingDown className="h-3.5 w-3.5 text-accent" />
              )}
              {item.status === "done" && item.verdict === "PASS" && (
                <ShieldCheck className="h-3.5 w-3.5 text-muted" />
              )}
              {item.status === "pending" && (
                <div className="h-3.5 w-3.5 rounded-full border border-zinc-600" />
              )}
            </div>

            {/* Product info */}
            <div className="flex-1 min-w-0">
              <p className="font-mono text-zinc-300 truncate">
                {item.title || item.asin}
              </p>
              {item.status === "done" && item.uk_price !== null && (
                <p className="text-muted mt-0.5">
                  UK: £{item.uk_price?.toFixed(2)}
                  {item.best_landed_cost !== null && item.best_country && (
                    <span>
                      {" → "}
                      {item.best_country}: £{item.best_landed_cost?.toFixed(2)}
                    </span>
                  )}
                </p>
              )}
            </div>

            {/* Verdict badge */}
            {item.status === "done" && item.verdict && (
              <span
                className={`shrink-0 px-2 py-0.5 rounded font-bold font-mono ${
                  item.verdict === "BUY"
                    ? "bg-accent/20 text-accent"
                    : "bg-zinc-800 text-muted"
                }`}
              >
                {item.verdict}
                {item.savings_pct !== null && item.savings_pct > 0 && (
                  <span className="ml-1 font-normal">
                    -{item.savings_pct.toFixed(0)}%
                  </span>
                )}
              </span>
            )}

            {/* Remove button */}
            <button
              onClick={() => onRemove(item.asin)}
              className="shrink-0 p-1 rounded hover:bg-zinc-800 text-muted/40 hover:text-red-400 transition-colors"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
