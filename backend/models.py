from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    THINKING = "thinking"
    SCRAPING = "scraping"
    PRICE_FOUND = "price_found"
    CALCULATING = "calculating"
    DECISION = "decision"
    ALERT = "alert"
    ERROR = "error"
    COMPLETE = "complete"


class AgentEvent(BaseModel):
    type: EventType
    message: str = ""
    data: dict | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def to_sse_dict(self) -> dict:
        return {"event": self.type.value, "data": self.model_dump_json()}


class PriceData(BaseModel):
    country: str
    country_code: str
    domain: str
    currency: str
    original_price: float | None = None
    price_gbp: float | None = None
    vat_rate: float = 0.0
    ex_vat_gbp: float | None = None
    with_uk_vat_gbp: float | None = None
    shipping_gbp: float = 10.0
    landed_cost_gbp: float | None = None
    savings_vs_uk_pct: float | None = None
    product_title: str = ""
    error: str | None = None


class Verdict(str, Enum):
    BUY = "BUY"
    PASS = "PASS"


class Decision(BaseModel):
    verdict: Verdict
    best_country: str | None = None
    best_country_code: str | None = None
    best_landed_cost: float | None = None
    uk_price: float | None = None
    savings_pct: float | None = None
    savings_gbp: float | None = None
    confidence: float = 0.0
    reasoning: str = ""


class ArbitrageResult(BaseModel):
    asin: str
    product_title: str = ""
    uk_price: float | None = None
    prices: list[PriceData] = []
    decision: Decision | None = None


class ArbitrageRequest(BaseModel):
    url: str


class WatcherState(BaseModel):
    active: bool = False
    url: str | None = None
    interval_seconds: int = 300
    last_checked: str | None = None
    last_result: ArbitrageResult | None = None
