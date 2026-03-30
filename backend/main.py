from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from backend.arbitrage import calculate_landed_cost, make_decision
from backend.models import (
    AgentEvent,
    ArbitrageRequest,
    ArbitrageResult,
    EventType,
    WatcherState,
)
from backend.scraper import AMAZON_DOMAINS, extract_asin, scrape_country

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

watcher_state = WatcherState()
_watcher_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ArbitrageAgent backend starting")
    yield
    global _watcher_task
    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
        logger.info("Watcher task cancelled on shutdown")


app = FastAPI(title="ArbitrageAgent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _run_arbitrage(url: str) -> AsyncGenerator[str, None]:
    """Core arbitrage pipeline that yields SSE events as the agent works."""

    # Step 1: Extract ASIN
    asin = extract_asin(url)
    if not asin:
        evt = AgentEvent(type=EventType.ERROR, message=f"Could not extract ASIN from URL: {url}")
        yield evt.to_sse()
        return

    yield AgentEvent(
        type=EventType.THINKING,
        message=f"Analysing URL... extracted ASIN {asin}",
        data={"asin": asin, "url": url},
    ).to_sse()

    yield AgentEvent(
        type=EventType.THINKING,
        message=f"Preparing to scan 5 Amazon stores: UK, DE, FR, ES, IT",
    ).to_sse()

    # Step 2: Scrape UK first
    yield AgentEvent(
        type=EventType.SCRAPING,
        message="Scraping baseline price from amazon.co.uk...",
    ).to_sse()

    _, uk_data, uk_events = await scrape_country(asin, "UK")
    for evt in uk_events:
        yield evt.to_sse()

    uk_data, uk_calc_events = calculate_landed_cost(uk_data, shipping_gbp=0.0)
    for evt in uk_calc_events:
        yield evt.to_sse()

    uk_price = uk_data.landed_cost_gbp

    if uk_price:
        yield AgentEvent(
            type=EventType.THINKING,
            message=f"UK baseline established: £{uk_price:.2f}. Now scanning EU stores for arbitrage...",
        ).to_sse()
    else:
        yield AgentEvent(
            type=EventType.THINKING,
            message="UK price could not be determined. Will still scan EU stores for data...",
        ).to_sse()

    # Step 3: Scrape EU countries in parallel
    eu_countries = [c for c in AMAZON_DOMAINS if c != "UK"]

    async def _scrape_and_emit(country: str):
        return await scrape_country(asin, country)

    tasks = [_scrape_and_emit(c) for c in eu_countries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_prices = [uk_data]
    for res in results:
        if isinstance(res, Exception):
            logger.error("Scrape task exception: %s", res)
            yield AgentEvent(type=EventType.ERROR, message=f"Scraper error: {res}").to_sse()
            continue

        country, price_data, events = res
        for evt in events:
            yield evt.to_sse()

        price_data, calc_events = calculate_landed_cost(price_data)
        for evt in calc_events:
            yield evt.to_sse()

        all_prices.append(price_data)

    # Step 4: Decision
    yield AgentEvent(
        type=EventType.THINKING,
        message="All markets scanned. Analysing results and making recommendation...",
    ).to_sse()

    decision, decision_events = make_decision(uk_price, all_prices)
    for evt in decision_events:
        yield evt.to_sse()

    # Step 5: Complete
    result = ArbitrageResult(
        asin=asin,
        product_title=uk_data.product_title or next(
            (p.product_title for p in all_prices if p.product_title), ""
        ),
        uk_price=uk_price,
        prices=all_prices,
        decision=decision,
    )

    yield AgentEvent(
        type=EventType.COMPLETE,
        message="Analysis complete.",
        data=result.model_dump(),
    ).to_sse()


@app.post("/api/arbitrage")
async def arbitrage(request: ArbitrageRequest):
    """Run the arbitrage agent and stream events via SSE."""

    async def event_generator():
        async for event_str in _run_arbitrage(request.url):
            yield event_str

    return EventSourceResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/watch/start")
async def watch_start(request: ArbitrageRequest):
    global _watcher_task, watcher_state

    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()

    watcher_state.active = True
    watcher_state.url = request.url

    async def _watch_loop():
        while watcher_state.active:
            logger.info("Watcher: running arbitrage check for %s", watcher_state.url)
            watcher_state.last_checked = datetime.now().strftime("%H:%M:%S")
            events = []
            async for evt in _run_arbitrage(watcher_state.url):
                events.append(evt)
            # Store last result from the complete event
            watcher_state.last_result = None
            await asyncio.sleep(watcher_state.interval_seconds)

    _watcher_task = asyncio.create_task(_watch_loop())
    return {"status": "started", "url": request.url, "interval": watcher_state.interval_seconds}


@app.post("/api/watch/stop")
async def watch_stop():
    global _watcher_task, watcher_state
    watcher_state.active = False
    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
    return {"status": "stopped"}


@app.get("/api/watch/status")
async def watch_status():
    return watcher_state.model_dump()


@app.get("/health")
def health():
    return {"status": "ok"}
