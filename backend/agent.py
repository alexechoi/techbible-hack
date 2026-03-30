from __future__ import annotations

import json
import logging
import os
import re
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from sse_starlette.sse import ServerSentEvent

from backend.arbitrage import (
    calculate_landed_cost,
    make_decision,
)
from backend.mcp_client import scrape_url
from backend.models import (
    AgentEvent,
    ArbitrageResult,
    EventType,
    PriceData,
)
from backend.scraper import (
    AMAZON_DOMAINS,
    _extract_title_from_markdown,
    _parse_price_from_markdown,
    build_product_url,
    extract_asin,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are ArbitrageAgent, an autonomous cross-border Amazon price intelligence agent.

Your mission: Given an Amazon UK product URL, determine whether the same product is cheaper \
to buy from an EU Amazon store after accounting for currency conversion, VAT adjustment, and shipping.

## CRITICAL: Be fast
- Scrape ALL 5 stores (UK + 4 EU) simultaneously in your FIRST response. \
  Make 5 parallel scrape_amazon_product tool calls immediately.
- After getting results, give a brief analysis. Landed cost calculations are done automatically — \
  just focus on your recommendation.

## After getting prices
Provide a SHORT analysis (3-4 sentences max). State: BUY (which store, why) or PASS (why).
If a store didn't have the product, just skip it.
"""


def _detect_country_from_url(url: str) -> tuple[str, dict] | None:
    for country, info in AMAZON_DOMAINS.items():
        if info["domain"] in url:
            return country, info
    return None


@tool
async def scrape_amazon_product(url: str) -> str:
    """Scrape an Amazon product page using Bright Data MCP and extract the price.

    Args:
        url: Full Amazon product URL, e.g. https://www.amazon.de/dp/B0CHWZ9TZS
    """
    detected = _detect_country_from_url(url)
    if not detected:
        return json.dumps({"error": f"Could not detect Amazon store from URL: {url}"})

    country, info = detected

    try:
        markdown = await scrape_url(url)
        price = _parse_price_from_markdown(markdown, info["currency_symbol"])
        title = _extract_title_from_markdown(markdown)

        result = {
            "country": country,
            "country_code": info["code"],
            "domain": info["domain"],
            "currency": info["currency"],
            "price": price,
            "title": title,
            "url": url,
        }
        if price is None:
            result["error"] = "Price not found — product may not be available."
        return json.dumps(result)
    except Exception as exc:
        logger.exception("scrape_amazon_product failed for %s", url)
        return json.dumps({"country": country, "country_code": info["code"], "error": str(exc)})


def _build_agent():
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    return create_react_agent(
        model=llm,
        tools=[scrape_amazon_product],
        prompt=SYSTEM_PROMPT,
    )


def _sse(evt: AgentEvent) -> ServerSentEvent:
    return ServerSentEvent(data=evt.model_dump_json(), event=evt.type.value)


async def run_arbitrage_agent(url: str) -> AsyncGenerator[ServerSentEvent, None]:
    """Run the LangGraph arbitrage agent and yield SSE events."""
    agent = _build_agent()

    collected_prices: dict[str, dict] = {}
    asin = extract_asin(url)

    yield _sse(AgentEvent(
        type=EventType.THINKING,
        message=f"Agent initialised. Analysing {url}",
        data={"asin": asin, "url": url},
    ))

    urls = {c: build_product_url(asin, info["domain"]) for c, info in AMAZON_DOMAINS.items()}
    url_list = "\n".join(f"- {c}: {u}" for c, u in urls.items())

    user_message = (
        f"Analyse ASIN {asin} for cross-border arbitrage. "
        f"Scrape ALL 5 stores NOW in parallel:\n{url_list}"
    )

    input_state = {"messages": [HumanMessage(content=user_message)]}

    try:
        async for chunk in agent.astream(input_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                messages = node_output.get("messages", [])

                if node_name == "agent":
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            if msg.content:
                                for sentence in _split_into_thoughts(msg.content):
                                    yield _sse(AgentEvent(
                                        type=EventType.THINKING,
                                        message=sentence,
                                    ))

                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    if tc["name"] == "scrape_amazon_product":
                                        yield _sse(AgentEvent(
                                            type=EventType.SCRAPING,
                                            message=f"Deploying Bright Data MCP scraper → {tc['args'].get('url', '')}",
                                        ))

                elif node_name == "tools":
                    for msg in messages:
                        if isinstance(msg, ToolMessage):
                            try:
                                data = json.loads(msg.content)
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if "price" in data and data.get("price") is not None:
                                cc = data.get("country_code", "")
                                price = data["price"]
                                currency = data.get("currency", "")
                                sym = "£" if currency == "GBP" else "€"
                                collected_prices[cc] = data
                                yield _sse(AgentEvent(
                                    type=EventType.PRICE_FOUND,
                                    message=f"Found price on {data.get('domain', '?')}: {sym}{price:.2f}",
                                    data=data,
                                ))
                            elif "error" in data:
                                yield _sse(AgentEvent(
                                    type=EventType.ERROR,
                                    message=f"{data.get('country', '?')}: {data['error']}",
                                ))
    except Exception as exc:
        logger.exception("Agent execution error")
        yield _sse(AgentEvent(type=EventType.ERROR, message=f"Agent error: {exc}"))

    # Auto-calculate landed costs (no LLM round-trip needed)
    all_prices: list[PriceData] = []
    uk_price: float | None = None
    product_title = ""

    for cc, data in collected_prices.items():
        country = data.get("country", "")
        pd = PriceData(
            country=country,
            country_code=cc,
            domain=data.get("domain", ""),
            currency=data.get("currency", ""),
            original_price=data.get("price"),
            product_title=data.get("title", ""),
            error=data.get("error"),
        )

        if cc == "GB":
            pd, _ = calculate_landed_cost(pd, shipping_gbp=0.0)
            if pd.original_price is not None:
                uk_price = pd.original_price
        else:
            pd, calc_events = calculate_landed_cost(pd)
            for evt in calc_events:
                yield _sse(evt)

        if pd.product_title and not product_title:
            product_title = pd.product_title
        all_prices.append(pd)

    decision, decision_events = make_decision(uk_price, all_prices)
    for evt in decision_events:
        yield _sse(evt)

    result = ArbitrageResult(
        asin=asin or "",
        product_title=product_title,
        uk_price=uk_price,
        prices=all_prices,
        decision=decision,
    )

    yield _sse(AgentEvent(
        type=EventType.COMPLETE,
        message="Analysis complete.",
        data=result.model_dump(),
    ))


def _normalize_content(content) -> str:
    if isinstance(content, list):
        return " ".join(
            c if isinstance(c, str) else c.get("text", str(c))
            for c in content
        )
    return str(content) if content else ""


def _split_into_thoughts(text) -> list[str]:
    text = _normalize_content(text)
    if not text:
        return []
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line and len(line) > 3:
            line = re.sub(r"^\d+\.\s*", "", line)
            line = re.sub(r"^[-*]\s*", "", line)
            if line:
                lines.append(line)
    return lines if lines else [text.strip()]
