"use client";

import { useCallback, useRef, useState } from "react";
import Header from "./components/Header";
import UrlInput from "./components/UrlInput";
import AgentLog, { type LogEntry } from "./components/AgentLog";
import CountryCard from "./components/CountryCard";
import DecisionCard from "./components/DecisionCard";
import BuyAlert from "./components/BuyAlert";
import WatchToggle from "./components/WatchToggle";

interface PriceData {
  country: string;
  country_code: string;
  domain: string;
  currency: string;
  original_price: number | null;
  price_gbp: number | null;
  vat_rate: number;
  ex_vat_gbp: number | null;
  with_uk_vat_gbp: number | null;
  shipping_gbp: number;
  landed_cost_gbp: number | null;
  savings_vs_uk_pct: number | null;
  product_title: string;
  error: string | null;
}

interface Decision {
  verdict: "BUY" | "PASS";
  best_country: string | null;
  best_country_code: string | null;
  best_landed_cost: number | null;
  uk_price: number | null;
  savings_pct: number | null;
  savings_gbp: number | null;
  confidence: number;
  reasoning: string;
}

const COUNTRY_ORDER = ["GB", "DE", "FR", "ES", "IT"];

export default function Home() {
  const [isRunning, setIsRunning] = useState(false);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [liveCountries, setLiveCountries] = useState<Record<string, PriceData>>({});
  const [decision, setDecision] = useState<Decision | null>(null);
  const [alert, setAlert] = useState<{
    savingsGbp: number;
    savingsPct: number;
    country: string;
  } | null>(null);
  const [scrapingSet, setScrapingSet] = useState<Set<string>>(new Set());
  const [watchActive, setWatchActive] = useState(false);
  const [lastChecked, setLastChecked] = useState<string | null>(null);
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const runArbitrage = useCallback(async (url: string) => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsRunning(true);
    setLogEntries([]);
    setLiveCountries({});
    setDecision(null);
    setAlert(null);
    setScrapingSet(new Set());
    setCurrentUrl(url);

    try {
      const response = await fetch("/api/arbitrage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        setLogEntries((prev) => [
          ...prev,
          {
            type: "error",
            message: `Request failed: ${response.status} ${response.statusText}`,
            timestamp: new Date().toLocaleTimeString("en-GB", { hour12: false }),
          },
        ]);
        setIsRunning(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            try {
              const parsed = JSON.parse(dataStr);
              const entry: LogEntry = {
                type: parsed.type || currentEvent,
                message: parsed.message || "",
                timestamp:
                  parsed.timestamp ||
                  new Date().toLocaleTimeString("en-GB", { hour12: false }),
              };
              setLogEntries((prev) => [...prev, entry]);

              if (parsed.type === "scraping" && parsed.message) {
                const domainMatch = parsed.message.match(
                  /amazon\.(co\.uk|de|fr|es|it)/,
                );
                if (domainMatch) {
                  setScrapingSet((prev) => new Set(prev).add(domainMatch[0]));
                }
              }

              if (parsed.type === "price_found" && parsed.data) {
                const d = parsed.data;
                setLiveCountries((prev) => ({
                  ...prev,
                  [d.country_code]: {
                    country: d.country,
                    country_code: d.country_code,
                    domain: d.domain || "",
                    currency: d.currency,
                    original_price: d.price,
                    price_gbp: d.currency === "GBP" ? d.price : null,
                    vat_rate: 0,
                    ex_vat_gbp: null,
                    with_uk_vat_gbp: null,
                    shipping_gbp: d.country_code === "GB" ? 0 : 10,
                    landed_cost_gbp: null,
                    savings_vs_uk_pct: null,
                    product_title: d.title || "",
                    error: null,
                  },
                }));
              }

              if (parsed.type === "complete" && parsed.data) {
                const result = parsed.data;
                const updated: Record<string, PriceData> = {};
                for (const p of result.prices) {
                  updated[p.country_code] = p;
                }
                setLiveCountries(updated);
                if (result.decision) {
                  setDecision(result.decision);
                }
              }

              if (parsed.type === "decision" && parsed.data) {
                setDecision(parsed.data as Decision);
              }

              if (parsed.type === "alert" && parsed.data) {
                setAlert({
                  savingsGbp: parsed.data.savings_gbp,
                  savingsPct: parsed.data.savings_pct,
                  country: parsed.data.country,
                });
              }
            } catch {
              // non-JSON SSE data
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      setLogEntries((prev) => [
        ...prev,
        {
          type: "error",
          message: `Connection error: ${err instanceof Error ? err.message : String(err)}`,
          timestamp: new Date().toLocaleTimeString("en-GB", { hour12: false }),
        },
      ]);
    } finally {
      setIsRunning(false);
      setLastChecked(
        new Date().toLocaleTimeString("en-GB", { hour12: false }),
      );
    }
  }, []);

  const toggleWatch = useCallback(async () => {
    if (watchActive) {
      await fetch("/api/watch/stop", { method: "POST" });
      setWatchActive(false);
    } else if (currentUrl) {
      await fetch("/api/watch/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: currentUrl }),
      });
      setWatchActive(true);
    }
  }, [watchActive, currentUrl]);

  const sortedPrices = COUNTRY_ORDER
    .filter((cc) => liveCountries[cc])
    .map((cc) => liveCountries[cc]);

  const hasAnyData =
    sortedPrices.length > 0 || decision !== null || scrapingSet.size > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header isActive={isRunning} />

      {alert && (
        <BuyAlert
          savingsGbp={alert.savingsGbp}
          savingsPct={alert.savingsPct}
          country={alert.country}
          onDismiss={() => setAlert(null)}
        />
      )}

      <UrlInput onSubmit={runArbitrage} disabled={isRunning} />

      <div className="flex flex-1 min-h-0">
        {/* Left panel: Agent Log */}
        <div className="w-[40%] border-r border-border flex flex-col">
          <AgentLog entries={logEntries} />
        </div>

        {/* Right panel: Results (progressive) */}
        <div className="w-[60%] overflow-y-auto p-6 space-y-6">
          {!hasAnyData && !isRunning && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-2">
                <p className="text-muted text-sm">
                  No analysis yet. Paste an Amazon UK URL to get started.
                </p>
                <p className="text-muted/50 text-xs font-mono">
                  The agent will scan UK, DE, FR, ES, and IT
                </p>
              </div>
            </div>
          )}

          {/* Scanning indicator before any prices arrive */}
          {isRunning && sortedPrices.length === 0 && scrapingSet.size > 0 && (
            <div className="rounded-lg border border-border bg-surface p-4 animate-fade-in">
              <p className="text-sm text-muted mb-3 font-mono">
                Scanning {scrapingSet.size} Amazon stores...
              </p>
              <div className="flex gap-2 flex-wrap">
                {Array.from(scrapingSet).map((domain) => (
                  <span
                    key={domain}
                    className="text-xs px-2 py-1 rounded-md bg-accent/10 text-accent font-mono animate-pulse"
                  >
                    {domain}
                  </span>
                ))}
              </div>
            </div>
          )}

          {decision && <DecisionCard decision={decision} />}

          {sortedPrices.length > 0 && (
            <>
              {sortedPrices[0]?.product_title && (
                <p
                  className="text-sm text-muted truncate"
                  title={sortedPrices[0].product_title}
                >
                  {sortedPrices[0].product_title}
                </p>
              )}
              <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
                {sortedPrices.map((p) => (
                  <div key={p.country_code} className="animate-fade-in">
                    <CountryCard
                      data={p}
                      isBest={p.country === decision?.best_country}
                      isUk={p.country === "UK"}
                    />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <WatchToggle
        active={watchActive}
        lastChecked={lastChecked}
        onToggle={toggleWatch}
        disabled={!currentUrl}
      />
    </div>
  );
}
