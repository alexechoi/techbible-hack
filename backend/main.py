from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from pathlib import Path

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env")
load_dotenv()  # also pick up cwd .env if present

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from backend.agent import run_arbitrage_agent
from backend.models import ArbitrageRequest, WatcherState

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

watcher_state = WatcherState()
_watcher_task: asyncio.Task | None = None


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


@app.post("/api/arbitrage")
async def arbitrage(request: ArbitrageRequest):
    async def event_generator():
        async for sse_event in run_arbitrage_agent(request.url):
            yield sse_event

    return EventSourceResponse(event_generator())


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
