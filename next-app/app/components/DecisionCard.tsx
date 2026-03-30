"use client";

import { TrendingDown, ShieldCheck } from "lucide-react";

interface Decision {
  verdict: "BUY" | "PASS";
  best_country: string | null;
  best_landed_cost: number | null;
  uk_price: number | null;
  savings_pct: number | null;
  savings_gbp: number | null;
  confidence: number;
  reasoning: string;
}

interface DecisionCardProps {
  decision: Decision;
}

export default function DecisionCard({ decision }: DecisionCardProps) {
  const isBuy = decision.verdict === "BUY";

  return (
    <div
      className={`rounded-xl border-2 p-5 transition-all ${
        isBuy
          ? "border-accent bg-accent/5 animate-slide-down"
          : "border-border bg-surface"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          {isBuy ? (
            <TrendingDown className="h-6 w-6 text-accent" />
          ) : (
            <ShieldCheck className="h-6 w-6 text-muted" />
          )}
          <span
            className={`text-2xl font-bold tracking-tight ${
              isBuy ? "text-accent" : "text-muted"
            }`}
          >
            {decision.verdict}
          </span>
        </div>

        {isBuy && decision.savings_gbp !== null && (
          <div className="text-right">
            <div className="text-3xl font-bold text-accent">
              Save £{decision.savings_gbp.toFixed(2)}
            </div>
            <div className="text-sm text-accent/70 font-mono">
              {decision.savings_pct?.toFixed(1)}% cheaper
            </div>
          </div>
        )}
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-muted mb-1">
          <span>Confidence</span>
          <span className="font-mono">
            {(decision.confidence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${
              decision.confidence > 0.8
                ? "bg-accent"
                : decision.confidence > 0.5
                  ? "bg-warning"
                  : "bg-danger"
            }`}
            style={{ width: `${decision.confidence * 100}%` }}
          />
        </div>
      </div>

      <p className="text-sm text-zinc-400 leading-relaxed">
        {decision.reasoning}
      </p>
    </div>
  );
}
