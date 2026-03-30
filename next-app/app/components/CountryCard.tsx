"use client";

interface PriceData {
  country: string;
  country_code: string;
  currency: string;
  original_price: number | null;
  price_gbp: number | null;
  vat_rate: number;
  ex_vat_gbp: number | null;
  with_uk_vat_gbp: number | null;
  shipping_gbp: number;
  landed_cost_gbp: number | null;
  savings_vs_uk_pct: number | null;
  error: string | null;
}

const FLAGS: Record<string, string> = {
  GB: "\u{1F1EC}\u{1F1E7}",
  DE: "\u{1F1E9}\u{1F1EA}",
  FR: "\u{1F1EB}\u{1F1F7}",
  ES: "\u{1F1EA}\u{1F1F8}",
  IT: "\u{1F1EE}\u{1F1F9}",
};

const CURRENCY_SYMBOLS: Record<string, string> = {
  GBP: "£",
  EUR: "€",
};

interface CountryCardProps {
  data: PriceData;
  isBest: boolean;
  isUk: boolean;
}

export default function CountryCard({ data, isBest, isUk }: CountryCardProps) {
  const flag = FLAGS[data.country_code] || "";
  const sym = CURRENCY_SYMBOLS[data.currency] || data.currency;
  const hasSavings = (data.savings_vs_uk_pct ?? 0) > 0;

  if (data.error && data.original_price === null) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4 opacity-50">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">{flag}</span>
          <span className="font-semibold text-sm">{data.country}</span>
        </div>
        <p className="text-xs text-red-400">Failed to retrieve price</p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg border p-4 transition-all ${
        isBest
          ? "border-accent bg-accent/5 ring-1 ring-accent/30"
          : "border-border bg-surface"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{flag}</span>
          <span className="font-semibold text-sm">{data.country}</span>
          {isUk && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 font-mono">
              BASELINE
            </span>
          )}
          {isBest && !isUk && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent font-mono font-bold">
              BEST DEAL
            </span>
          )}
        </div>
        {hasSavings && !isUk && (
          <span className="text-xs font-bold text-accent animate-pulse-glow px-2 py-0.5 rounded-full bg-accent/10">
            -{data.savings_vs_uk_pct?.toFixed(1)}%
          </span>
        )}
      </div>

      <div className="space-y-1 text-xs font-mono">
        <Row
          label="Original"
          value={
            data.original_price !== null
              ? `${sym}${data.original_price.toFixed(2)}`
              : "—"
          }
        />
        {!isUk && (
          <>
            <Row
              label="In GBP"
              value={
                data.price_gbp !== null ? `£${data.price_gbp.toFixed(2)}` : "—"
              }
            />
            <Row
              label={`-${(data.vat_rate * 100).toFixed(0)}% local VAT`}
              value={
                data.ex_vat_gbp !== null
                  ? `£${data.ex_vat_gbp.toFixed(2)}`
                  : "—"
              }
            />
            <Row
              label="+20% UK VAT"
              value={
                data.with_uk_vat_gbp !== null
                  ? `£${data.with_uk_vat_gbp.toFixed(2)}`
                  : "—"
              }
            />
            <Row
              label="Shipping"
              value={`£${data.shipping_gbp.toFixed(2)}`}
            />
          </>
        )}
        <div className="border-t border-border pt-1 mt-1">
          <Row
            label="Landed cost"
            value={
              data.landed_cost_gbp !== null
                ? `£${data.landed_cost_gbp.toFixed(2)}`
                : "—"
            }
            bold
          />
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  bold,
}: {
  label: string;
  value: string;
  bold?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{label}</span>
      <span className={bold ? "font-bold text-foreground" : "text-zinc-300"}>
        {value}
      </span>
    </div>
  );
}
