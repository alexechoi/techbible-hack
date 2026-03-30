from __future__ import annotations

from models import AgentEvent, Decision, EventType, PriceData, Verdict

FX_RATES: dict[str, float] = {
    "GBP": 1.0,
    "EUR": 0.83,
}

VAT_RATES: dict[str, float] = {
    "GB": 0.20,
    "DE": 0.19,
    "FR": 0.20,
    "ES": 0.21,
    "IT": 0.22,
}

DEFAULT_SHIPPING_GBP = 10.0
BUY_THRESHOLD_PCT = 10.0


def to_gbp(amount: float, currency: str) -> float:
    rate = FX_RATES.get(currency, 1.0)
    return round(amount * rate, 2)


def calculate_landed_cost(
    price_data: PriceData,
    shipping_gbp: float = DEFAULT_SHIPPING_GBP,
) -> tuple[PriceData, list[AgentEvent]]:
    """Calculate the full landed cost for one country and return calculation events."""
    events: list[AgentEvent] = []

    if price_data.original_price is None:
        return price_data, events

    price_gbp = to_gbp(price_data.original_price, price_data.currency)
    price_data.price_gbp = price_gbp

    local_vat_rate = VAT_RATES.get(price_data.country_code, 0.20)
    price_data.vat_rate = local_vat_rate

    if price_data.country_code == "GB":
        price_data.ex_vat_gbp = price_gbp
        price_data.with_uk_vat_gbp = price_gbp
        price_data.shipping_gbp = 0.0
        price_data.landed_cost_gbp = price_gbp
    else:
        ex_vat = round(price_gbp / (1 + local_vat_rate), 2)
        price_data.ex_vat_gbp = ex_vat
        with_uk_vat = round(ex_vat * 1.20, 2)
        price_data.with_uk_vat_gbp = with_uk_vat
        price_data.shipping_gbp = shipping_gbp
        landed = round(with_uk_vat + shipping_gbp, 2)
        price_data.landed_cost_gbp = landed

        events.append(AgentEvent(
            type=EventType.CALCULATING,
            message=(
                f"{price_data.country}: "
                f"{price_data.currency} {price_data.original_price:.2f} → "
                f"£{price_gbp:.2f} | "
                f"-{local_vat_rate:.0%} VAT → £{ex_vat:.2f} | "
                f"+20% UK VAT → £{with_uk_vat:.2f} | "
                f"+£{shipping_gbp:.2f} shipping = "
                f"£{landed:.2f} landed"
            ),
        ))

    return price_data, events


def make_decision(
    uk_price: float | None,
    prices: list[PriceData],
) -> tuple[Decision, list[AgentEvent]]:
    """Analyse all prices and emit the agent's buy/pass decision."""
    events: list[AgentEvent] = []
    successful = [p for p in prices if p.landed_cost_gbp is not None and p.country != "UK"]
    total_eu = len([p for p in prices if p.country != "UK"])
    confidence = len(successful) / max(total_eu, 1)

    if uk_price is None:
        decision = Decision(
            verdict=Verdict.PASS,
            confidence=confidence,
            reasoning="Could not determine UK price — unable to compare.",
        )
        return decision, events

    if not successful:
        decision = Decision(
            verdict=Verdict.PASS,
            uk_price=uk_price,
            confidence=0.0,
            reasoning="No EU prices could be retrieved — cannot make a recommendation.",
        )
        return decision, events

    best = min(successful, key=lambda p: p.landed_cost_gbp or float("inf"))
    savings_gbp = round(uk_price - (best.landed_cost_gbp or uk_price), 2)
    savings_pct = round((savings_gbp / uk_price) * 100, 1) if uk_price > 0 else 0.0

    for p in successful:
        p.savings_vs_uk_pct = round(
            ((uk_price - (p.landed_cost_gbp or uk_price)) / uk_price) * 100, 1
        ) if uk_price > 0 else 0.0

    if savings_pct >= BUY_THRESHOLD_PCT:
        verdict = Verdict.BUY
        reasoning = (
            f"Amazon {best.country} offers the best deal at £{best.landed_cost_gbp:.2f} landed "
            f"(vs £{uk_price:.2f} UK). That's £{savings_gbp:.2f} cheaper ({savings_pct}% saving). "
            f"After removing {best.country} VAT ({best.vat_rate:.0%}) and adding UK VAT (20%), "
            f"plus £{best.shipping_gbp:.2f} shipping, this is a genuine arbitrage opportunity."
        )
    else:
        verdict = Verdict.PASS
        if savings_pct > 0:
            reasoning = (
                f"Best EU option is Amazon {best.country} at £{best.landed_cost_gbp:.2f} landed, "
                f"saving only {savings_pct}%. Below the {BUY_THRESHOLD_PCT}% threshold — "
                f"stick with Amazon UK at £{uk_price:.2f}."
            )
        else:
            reasoning = (
                f"Amazon UK at £{uk_price:.2f} is the best price. "
                f"No EU store beats it after VAT adjustment and shipping "
                f"(cheapest EU landed cost: £{best.landed_cost_gbp:.2f} from {best.country})."
            )

    best_c = best.country if verdict == Verdict.BUY else "UK"
    best_cc = best.country_code if verdict == Verdict.BUY else "GB"
    best_lc = best.landed_cost_gbp if verdict == Verdict.BUY else uk_price

    decision = Decision(
        verdict=verdict,
        best_country=best_c,
        best_country_code=best_cc,
        best_landed_cost=best_lc,
        uk_price=uk_price,
        savings_pct=savings_pct,
        savings_gbp=savings_gbp,
        confidence=round(confidence, 2),
        reasoning=reasoning,
    )

    events.append(AgentEvent(
        type=EventType.DECISION,
        message=reasoning,
        data=decision.model_dump(),
    ))

    if verdict == Verdict.BUY:
        events.append(AgentEvent(
            type=EventType.ALERT,
            message=f"BUY ALERT: Save £{savings_gbp:.2f} ({savings_pct}%) buying from Amazon {best.country}!",
            data={"savings_gbp": savings_gbp, "savings_pct": savings_pct, "country": best.country},
        ))

    return decision, events
