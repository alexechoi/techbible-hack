"use client";

import { TrendingDown, X } from "lucide-react";

interface BuyAlertProps {
  savingsGbp: number;
  savingsPct: number;
  country: string;
  onDismiss: () => void;
}

export default function BuyAlert({
  savingsGbp,
  savingsPct,
  country,
  onDismiss,
}: BuyAlertProps) {
  return (
    <div className="animate-slide-down bg-accent/10 border-b-2 border-accent px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <div className="h-10 w-10 rounded-full bg-accent/20 flex items-center justify-center animate-pulse-glow">
          <TrendingDown className="h-5 w-5 text-accent" />
        </div>
        <div>
          <div className="text-lg font-bold text-accent">
            BUY ALERT — Save £{savingsGbp.toFixed(2)} ({savingsPct.toFixed(1)}
            %)
          </div>
          <div className="text-sm text-accent/70">
            Best price found on Amazon {country}
          </div>
        </div>
      </div>
      <button
        onClick={onDismiss}
        className="p-1 rounded hover:bg-zinc-800 text-muted"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
