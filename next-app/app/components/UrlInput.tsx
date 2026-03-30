"use client";

import { Search, Link as LinkIcon } from "lucide-react";
import { useState, useCallback } from "react";

interface UrlInputProps {
  onSubmit: (url: string) => void;
  disabled: boolean;
}

export default function UrlInput({ onSubmit, disabled }: UrlInputProps) {
  const [url, setUrl] = useState("");

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = url.trim();
      if (!trimmed) return;
      onSubmit(trimmed);
    },
    [url, onSubmit],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLInputElement>) => {
      const pasted = e.clipboardData.getData("text").trim();
      if (pasted && /amazon\.\w+.*\/dp\/[A-Z0-9]{10}/i.test(pasted)) {
        setTimeout(() => onSubmit(pasted), 100);
      }
    },
    [onSubmit],
  );

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-3 px-6 py-3 border-b border-border bg-surface"
    >
      <LinkIcon className="h-4 w-4 text-muted shrink-0" />
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onPaste={handlePaste}
        placeholder="Paste an Amazon UK product URL (e.g. https://www.amazon.co.uk/dp/B08L5TNJHG)"
        disabled={disabled}
        className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted/60 outline-none font-mono"
      />
      <button
        type="submit"
        disabled={disabled || !url.trim()}
        className="flex items-center gap-2 px-4 py-1.5 rounded-md bg-accent text-black text-sm font-medium hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <Search className="h-3.5 w-3.5" />
        Analyse
      </button>
    </form>
  );
}
