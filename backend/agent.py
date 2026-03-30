from __future__ import annotations

import json
import logging
import os
import re
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sse_starlette.sse import ServerSentEvent

from backend.arbitrage import (
    DEFAULT_SHIPPING_GBP,
    FX_RATES,
    VAT_RATES,
    calculate_landed_cost,
    make_decision,
    to_gbp,
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
to buy from an EU Amazon store (Germany, France, Spain, Italy) after accounting for \
currency conversion, VAT adjustment, and shipping.

## How to work

1. Extract the ASIN (the 10-character product ID from the /dp/ segment of the URL).
2. Scrape the UK store first to establish the baseline GBP price.
3. Scrape the EU stores (amazon.de, amazon.fr, amazon.es, amazon.it) for the same ASIN. \
   You SHOULD call scrape_amazon_product for all EU stores simultaneously in a single response \
   to save time.
4. For each EU price found, call calculate_eu_landed_cost to get the true cost of importing to the UK.
5. Compare all landed costs against the UK price and give your final recommendation.

## Important notes
- If a store doesn't carry the product, note it and move on.
- Always explain your reasoning at each step — the user can see your thoughts in real-time.
- Be concise but thorough. Think like a trading analyst.
- After all analysis, state clearly: BUY (with which store) or PASS, and why.
"""


def _detect_country_from_url(url: str) -> tuple[str, dict] | None:
    for country, info in AMAZON_DOMAINS.items():
        if info["domain"] in url:
            return country, info
    return None


@tool
async def scrape_amazon_product(url: str) -> str:
    """Scrape an Amazon product page using Bright Data MCP and extract the price.

    Use this tool to get the current price of a product on any Amazon store.
    Build the URL as: https://www.{domain}/dp/{ASIN}

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
            result["error"] = "Price not found on this page — product may not be available in this store."
        return json.dumps(result)
    except Exception as exc:
        logger.exception("scrape_amazon_product failed for %s", url)
        return json.dumps({"country": country, "country_code": info["code"], "error": str(exc)})


@tool
def calculate_eu_landed_cost(
    original_price: float,
    currency: str,
    country_code: str,
) -> str:
    """Calculate the true landed cost of importing a product from an EU Amazon store to the UK.

    This accounts for: currency conversion to GBP, removal of local VAT, addition of UK VAT (20%), and shipping.

    Args:
        original_price: The product price in its original currency (e.g. 162.34)
        currency: The currency code (EUR or GBP)
        country_code: Two-letter country code (DE, FR, ES, IT)
    """
    price_gbp = to_gbp(original_price, currency)
    local_vat = VAT_RATES.get(country_code, 0.20)
    ex_vat = round(price_gbp / (1 + local_vat), 2)
    with_uk_vat = round(ex_vat * 1.20, 2)
    shipping = DEFAULT_SHIPPING_GBP
    landed = round(with_uk_vat + shipping, 2)

    return json.dumps({
        "country_code": country_code,
        "original_price": original_price,
        "currency": currency,
        "price_gbp": price_gbp,
        "local_vat_rate": local_vat,
        "ex_vat_gbp": ex_vat,
        "with_uk_vat_gbp": with_uk_vat,
        "shipping_gbp": shipping,
        "landed_cost_gbp": landed,
        "breakdown": (
            f"{currency} {original_price:.2f} → £{price_gbp:.2f} | "
            f"-{local_vat:.0%} local VAT → £{ex_vat:.2f} | "
            f"+20% UK VAT → £{with_uk_vat:.2f} | "
            f"+£{shipping:.2f} shipping = £{landed:.2f} landed"
        ),
    })


def _build_agent():
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0, streaming=True)
    return create_react_agent(
        model=llm,
        tools=[scrape_amazon_product, calculate_eu_landed_cost],
        prompt=SYSTEM_PROMPT,
    )


def _sse(evt: AgentEvent) -> ServerSentEvent:
    return ServerSentEvent(data=evt.model_dump_json(), event=evt.type.value)


async def run_arbitrage_agent(url: str) -> AsyncGenerator[ServerSentEvent, None]:
    """Run the LangGraph arbitrage agent and yield SSE events as it thinks and acts."""
    agent = _build_agent()

    collected_prices: dict[str, dict] = {}
    asin = extract_asin(url)

    yield _sse(AgentEvent(
        type=EventType.THINKING,
        message=f"Agent initialised. Analysing {url}",
        data={"asin": asin, "url": url},
    ))

    user_message = (
        f"Analyse this Amazon UK product for cross-border arbitrage opportunities:\n"
        f"{url}\n\n"
        f"The ASIN is {asin}. The Amazon stores to check are:\n"
        f"- UK: https://www.amazon.co.uk/dp/{asin}\n"
        f"- DE: https://www.amazon.de/dp/{asin}\n"
        f"- FR: https://www.amazon.fr/dp/{asin}\n"
        f"- ES: https://www.amazon.es/dp/{asin}\n"
        f"- IT: https://www.amazon.it/dp/{asin}\n"
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
                                    name = tc["name"]
                                    args = tc["args"]
                                    if name == "scrape_amazon_product":
                                        domain = args.get("url", "")
                                        yield _sse(AgentEvent(
                                            type=EventType.SCRAPING,
                                            message=f"Deploying Bright Data MCP scraper → {domain}",
                                        ))
                                    elif name == "calculate_eu_landed_cost":
                                        cc = args.get("country_code", "?")
                                        yield _sse(AgentEvent(
                                            type=EventType.CALCULATING,
                                            message=f"Calculating landed cost for {cc}...",
                                        ))

                elif node_name == "tools":
                    for msg in messages:
                        if isinstance(msg, ToolMessage):
                            try:
                                data = json.loads(msg.content)
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if "price" in data and data.get("price") is not None:
                                country = data.get("country", "?")
                                cc = data.get("country_code", "")
                                price = data["price"]
                                currency = data.get("currency", "")
                                sym = "£" if currency == "GBP" else "€"
                                collected_prices[cc] = data
                                yield _sse(AgentEvent(
                                    type=EventType.PRICE_FOUND,
                                    message=f"Found price on {data.get('domain', country)}: {sym}{price:.2f}",
                                    data=data,
                                ))
                            elif "landed_cost_gbp" in data:
                                cc = data.get("country_code", "?")
                                breakdown = data.get("breakdown", "")
                                if cc in collected_prices:
                                    collected_prices[cc].update(data)
                                yield _sse(AgentEvent(
                                    type=EventType.CALCULATING,
                                    message=f"{cc}: {breakdown}",
                                ))
                            elif "error" in data:
                                yield _sse(AgentEvent(
                                    type=EventType.ERROR,
                                    message=f"{data.get('country', '?')}: {data['error']}",
                                ))
    except Exception as exc:
        logger.exception("Agent execution error")
        yield _sse(AgentEvent(type=EventType.ERROR, message=f"Agent error: {exc}"))

    # Build the final ArbitrageResult from collected data
    yield _sse(AgentEvent(
        type=EventType.THINKING,
        message="Compiling final analysis...",
    ))

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

        if data.get("landed_cost_gbp"):
            pd.price_gbp = data.get("price_gbp")
            pd.vat_rate = data.get("local_vat_rate", 0.0)
            pd.ex_vat_gbp = data.get("ex_vat_gbp")
            pd.with_uk_vat_gbp = data.get("with_uk_vat_gbp")
            pd.shipping_gbp = data.get("shipping_gbp", 10.0)
            pd.landed_cost_gbp = data.get("landed_cost_gbp")
        elif cc == "GB" and pd.original_price is not None:
            pd.price_gbp = pd.original_price
            pd.ex_vat_gbp = pd.original_price
            pd.with_uk_vat_gbp = pd.original_price
            pd.shipping_gbp = 0.0
            pd.landed_cost_gbp = pd.original_price
            pd.vat_rate = 0.20

        if cc == "GB" and pd.original_price is not None:
            uk_price = pd.original_price
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


def _split_into_thoughts(text: str) -> list[str]:
    """Split LLM output into individual thought lines for the agent log."""
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line and len(line) > 3:
            line = re.sub(r"^\d+\.\s*", "", line)
            line = re.sub(r"^[-*]\s*", "", line)
            if line:
                lines.append(line)
    return lines if lines else [text.strip()]
