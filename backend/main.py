from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import sys
from pathlib import Path

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend_dir))
load_dotenv(_backend_dir / ".env")
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from agent import run_arbitrage_agent
from models import AgentEvent, ArbitrageRequest, EventType, WatcherState, WishlistItem
from scraper import extract_asin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

watcher_state = WatcherState()
_watcher_task: asyncio.Task | None = None
_wishlist: dict[str, WishlistItem] = {}


def _sse(evt: AgentEvent) -> ServerSentEvent:
    return ServerSentEvent(data=evt.model_dump_json(), event=evt.type.value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ArbitrageAgent backend starting (LangGraph mode)")
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


# --- Single product analysis ---

@app.post("/api/arbitrage")
async def arbitrage(request: ArbitrageRequest):
    async def event_generator():
        async for sse_event in run_arbitrage_agent(request.url):
            yield sse_event

    return EventSourceResponse(event_generator())


# --- Wishlist ---

@app.get("/api/wishlist")
async def wishlist_list():
    return list(_wishlist.values())


@app.post("/api/wishlist")
async def wishlist_add(request: ArbitrageRequest):
    asin = extract_asin(request.url)
    if not asin:
        return {"error": "Could not extract ASIN from URL"}
    if asin in _wishlist:
        return _wishlist[asin].model_dump()
    item = WishlistItem(asin=asin, url=request.url)
    _wishlist[asin] = item
    return item.model_dump()


@app.delete("/api/wishlist/{asin}")
async def wishlist_remove(asin: str):
    _wishlist.pop(asin.upper(), None)
    return {"status": "removed"}


@app.post("/api/wishlist/scan-all")
async def wishlist_scan_all():
    """Process every wishlist item sequentially, streaming events for each."""

    async def event_generator():
        items = list(_wishlist.values())
        if not items:
            yield _sse(AgentEvent(
                type=EventType.ERROR,
                message="Wishlist is empty — add some products first.",
            ))
            return

        yield _sse(AgentEvent(
            type=EventType.THINKING,
            message=f"Starting autonomous scan of {len(items)} wishlist products...",
        ))

        for idx, item in enumerate(items, 1):
            item.status = "scanning"
            yield _sse(AgentEvent(
                type=EventType.THINKING,
                message=f"[{idx}/{len(items)}] Scanning {item.asin}...",
                data={"asin": item.asin, "index": idx, "total": len(items)},
            ))

            async for sse_event in run_arbitrage_agent(item.url):
                yield sse_event

                if hasattr(sse_event, "data") and sse_event.data:
                    try:
                        parsed = __import__("json").loads(sse_event.data)
                        if parsed.get("type") == "complete" and parsed.get("data"):
                            result = parsed["data"]
                            d = result.get("decision", {})
                            item.status = "done"
                            item.verdict = d.get("verdict")
                            item.savings_pct = d.get("savings_pct")
                            item.savings_gbp = d.get("savings_gbp")
                            item.best_country = d.get("best_country")
                            item.uk_price = d.get("uk_price")
                            item.best_landed_cost = d.get("best_landed_cost")
                            item.title = result.get("product_title", "")
                    except Exception:
                        pass

        yield _sse(AgentEvent(
            type=EventType.THINKING,
            message=f"All {len(items)} products scanned. Wishlist updated.",
        ))

    return EventSourceResponse(event_generator())


# --- Watcher ---

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
            async for _ in run_arbitrage_agent(watcher_state.url):
                pass
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
