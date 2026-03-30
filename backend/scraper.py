from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator

from mcp_client import scrape_url
from models import AgentEvent, EventType, PriceData

logger = logging.getLogger(__name__)

AMAZON_DOMAINS: dict[str, dict] = {
    "UK": {
        "domain": "amazon.co.uk",
        "currency": "GBP",
        "currency_symbol": "£",
        "code": "GB",
    },
    "DE": {
        "domain": "amazon.de",
        "currency": "EUR",
        "currency_symbol": "€",
        "code": "DE",
    },
    "FR": {
        "domain": "amazon.fr",
        "currency": "EUR",
        "currency_symbol": "€",
        "code": "FR",
    },
    "ES": {
        "domain": "amazon.es",
        "currency": "EUR",
        "currency_symbol": "€",
        "code": "ES",
    },
    "IT": {
        "domain": "amazon.it",
        "currency": "EUR",
        "currency_symbol": "€",
        "code": "IT",
    },
}


def extract_asin(url: str) -> str | None:
    """Pull the 10-char ASIN from an Amazon product URL."""
    m = re.search(r"/dp/([A-Z0-9]{10})", url, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"/product/([A-Z0-9]{10})", url, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?:asin|ASIN)[=/]([A-Z0-9]{10})", url, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _parse_price_from_markdown(markdown: str, currency_symbol: str) -> float | None:
    """Extract the headline product price from scraped markdown.

    Strategy: the real product price appears in the top portion of the page
    (price block, buy box) while "related product" prices appear lower down.
    We score prices found in the top 20% of the page 3x higher, then pick
    the highest-scoring price, breaking ties by value (headline > accessory).
    """
    escaped = re.escape(currency_symbol)
    text = markdown.replace("\xa0", " ")

    patterns = [
        rf"{escaped}\s*(\d{{1,5}}[.,]\d{{2}})",
        rf"(\d{{1,5}}[.,]\d{{2}})\s*{escaped}",
        rf"{escaped}\s*(\d{{1,5}})",
        rf"(\d{{1,5}})\s*{escaped}",
    ]

    from collections import Counter
    top_cutoff = len(text) // 5
    top_prices: Counter[float] = Counter()
    all_prices: Counter[float] = Counter()

    for pat in patterns:
        for m in re.finditer(pat, text):
            raw = m.group(1)
            try:
                cleaned = raw.replace(",", ".")
                price = float(cleaned)
                if 1.0 < price < 10_000:
                    all_prices[price] += 1
                    if m.start() < top_cutoff:
                        top_prices[price] += 1
            except ValueError:
                continue

    if not all_prices:
        return None

    scores: Counter[float] = Counter()
    for price, count in all_prices.items():
        scores[price] = count + top_prices.get(price, 0) * 3

    max_score = max(scores.values())
    candidates = [p for p, s in scores.items() if s == max_score]
    return max(candidates)


def _extract_title_from_markdown(markdown: str) -> str:
    """Best-effort title extraction from scraped markdown."""
    for line in markdown.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if len(stripped) > 15 and not stripped.startswith("http"):
            return stripped[:120]
    return ""


def build_product_url(asin: str, domain: str) -> str:
    return f"https://www.{domain}/dp/{asin}"


async def scrape_country(
    asin: str,
    country: str,
) -> tuple[str, PriceData, list[AgentEvent]]:
    """Scrape a single country and return (country, price_data, events)."""
    info = AMAZON_DOMAINS[country]
    events: list[AgentEvent] = []
    url = build_product_url(asin, info["domain"])

    events.append(AgentEvent(
        type=EventType.SCRAPING,
        message=f"Deploying scraper to {info['domain']} via Bright Data MCP...",
    ))

    price_data = PriceData(
        country=country,
        country_code=info["code"],
        domain=info["domain"],
        currency=info["currency"],
    )

    try:
        markdown = await scrape_url(url)
        price = _parse_price_from_markdown(markdown, info["currency_symbol"])
        title = _extract_title_from_markdown(markdown)

        price_data.original_price = price
        price_data.product_title = title

        if price is not None:
            events.append(AgentEvent(
                type=EventType.PRICE_FOUND,
                message=f"Found price on {info['domain']}: {info['currency_symbol']}{price:.2f}",
                data={
                    "country": country,
                    "country_code": info["code"],
                    "price": price,
                    "currency": info["currency"],
                    "title": title,
                    "url": url,
                },
            ))
        else:
            price_data.error = "Price not found in page content"
            events.append(AgentEvent(
                type=EventType.ERROR,
                message=f"Could not extract price from {info['domain']} — page may have different layout",
            ))
    except Exception as exc:
        logger.exception("Scrape failed for %s", info["domain"])
        price_data.error = str(exc)
        events.append(AgentEvent(
            type=EventType.ERROR,
            message=f"Scraper error on {info['domain']}: {exc}",
        ))

    return country, price_data, events
