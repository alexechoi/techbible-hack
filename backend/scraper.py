from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator

from backend.mcp_client import scrape_url
from backend.models import AgentEvent, EventType, PriceData

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
    """Extract the first plausible product price from scraped markdown."""
    escaped = re.escape(currency_symbol)

    # "€89,99" or "€89.99" or "£109.99"
    patterns = [
        rf"{escaped}\s*(\d{{1,5}}[.,]\d{{2}})",
        rf"(\d{{1,5}}[.,]\d{{2}})\s*{escaped}",
        rf"{escaped}\s*(\d{{1,5}})",
    ]
    for pat in patterns:
        matches = re.findall(pat, markdown)
        for raw in matches:
            try:
                cleaned = raw.replace(",", ".")
                price = float(cleaned)
                if 0.50 < price < 10_000:
                    return price
            except ValueError:
                continue
    return None


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
