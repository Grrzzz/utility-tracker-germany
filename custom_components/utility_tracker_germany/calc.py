"""Pure calculation helpers (no Home Assistant imports)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from dateutil.relativedelta import relativedelta

UNIT_FACTORS = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}


def unit_factor(unit: str | None) -> float:
    """Factor to convert a source reading into kWh/m3 (Wh -> kWh, MWh -> kWh)."""
    return UNIT_FACTORS.get(unit or "", 1.0)


@dataclass(frozen=True)
class Period:
    """A tariff period starting at `start` (inclusive)."""

    start: date
    advance: float
    price: float
    base_year: float
    reading: float  # meter reading (kWh/m3) at the start of the period
    sewage_price: float = 0.0  # added to `price` per unit (water only)


def build_periods(
    start: date,
    start_reading: float,
    price: float,
    base_year: float,
    advance: float,
    changes: Iterable[dict[str, Any]] | None,
    sewage_price: float = 0.0,
) -> list[Period]:
    """Build tariff periods from the base tariff and mid-year changes.

    Unspecified values in a change are carried over from the previous period.
    Changes on or before the billing start are ignored; the last change wins
    when several share a date.
    """
    by_date: dict[date, dict[str, Any]] = {}
    for ch in changes or []:
        try:
            d = date.fromisoformat(str(ch["date"]))
        except (KeyError, ValueError):
            continue
        if d > start:
            by_date[d] = ch
    periods = [
        Period(start, advance, price, base_year, start_reading, sewage_price)
    ]
    for d in sorted(by_date):
        ch, prev = by_date[d], periods[-1]
        periods.append(
            Period(
                d,
                float(ch["monthly_advance"]) if ch.get("monthly_advance") is not None else prev.advance,
                float(ch["unit_price"]) if ch.get("unit_price") is not None else prev.price,
                float(ch["base_price_year"]) if ch.get("base_price_year") is not None else prev.base_year,
                float(ch["meter_reading"]) if ch.get("meter_reading") is not None else prev.reading,
                float(ch["sewage_price"]) if ch.get("sewage_price") is not None else prev.sewage_price,
            )
        )
    return periods


def _active(periods: list[Period], today: date) -> list[Period]:
    return [p for p in periods if p.start <= today] or periods[:1]


def contract_end(start: date, term_months: int = 12) -> date:
    """First day after the contract term."""
    return start + relativedelta(months=term_months)


def elapsed_months(start: date, d: date, term_months: int = 12) -> float:
    """Months elapsed since contract start (full months + pro-rata), capped at the term."""
    if d <= start:
        return 0.0
    if d >= contract_end(start, term_months):
        return float(term_months)
    rd = relativedelta(d, start)
    months = rd.years * 12 + rd.months
    anchor = start + relativedelta(months=months)
    next_anchor = start + relativedelta(months=months + 1)
    return months + (d - anchor).days / (next_anchor - anchor).days


def calc_soll(
    start: date,
    today: date,
    periods: list[Period],
    correction: float = 0.0,
    term_months: int = 12,
) -> float:
    """Advance payments accrued so far, honouring advance changes."""
    act = _active(periods, today)
    total = 0.0
    for i, p in enumerate(act):
        end = act[i + 1].start if i + 1 < len(act) else today
        total += p.advance * (
            elapsed_months(start, end, term_months)
            - elapsed_months(start, p.start, term_months)
        )
    return round(total + correction, 2)


def calc_base_cost(
    start: date, today: date, periods: list[Period], term_months: int = 12
) -> float:
    """Pro-rata base price since billing start, honouring base price changes."""
    year_days = (start + relativedelta(years=1) - start).days
    year_end = contract_end(start, term_months)
    act = _active(periods, today)
    total = 0.0
    for i, p in enumerate(act):
        end = min(act[i + 1].start if i + 1 < len(act) else today, year_end)
        days = max(0, (end - p.start).days)
        total += p.base_year * days / year_days
    return total


def calc_ist_parts(
    start: date,
    today: date,
    reading: float,
    unit: str | None,
    periods: list[Period],
    term_months: int = 12,
    end_reading: float | None = None,
) -> tuple[float, float]:
    """Actual cost so far split into (supply incl. base price, sewage), without corrections.

    Each unit consumed is billed with both `price` and `sewage_price`.
    After the contract end the result is frozen: consumption counts up to
    `end_reading` (kWh/m3) if given, else up to the reading at the end date
    is unknown and the live reading is used."""
    current = reading * unit_factor(unit)
    end = contract_end(start, term_months)
    if today >= end:
        if end_reading is not None:
            current = end_reading
        today = end
    act = _active(periods, today)
    supply = sewage = 0.0
    for i, p in enumerate(act):
        end_reading = act[i + 1].reading if i + 1 < len(act) else current
        used = max(0.0, end_reading - p.reading)
        supply += used * p.price
        sewage += used * p.sewage_price
    supply += calc_base_cost(start, today, periods, term_months)
    return round(supply, 2), round(sewage, 2)


def calc_ist(
    start: date,
    today: date,
    reading: float,
    unit: str | None,
    periods: list[Period],
    correction: float = 0.0,
    term_months: int = 12,
    end_reading: float | None = None,
) -> float:
    """Actual cost so far (supply + sewage + correction)."""
    supply, sewage = calc_ist_parts(
        start, today, reading, unit, periods, term_months, end_reading
    )
    return round(supply + sewage + correction, 2)

def calc_forecast(
    start: date,
    today: date,
    reading: float,
    unit: str | None,
    periods: list[Period],
    ist_correction: float = 0.0,
    soll_correction: float = 0.0,
    term_months: int = 12,
    end_reading: float | None = None,
    min_days: int = 14,
) -> dict[str, float] | None:
    """Project Ist to the contract end by extrapolating the average daily consumption.

    Planned tariff changes are priced in. Returns None while there is too little
    data (fewer than `min_days` since the start) to extrapolate.
    """
    end = contract_end(start, term_months)
    plan_total = calc_soll(start, end, periods, soll_correction, term_months)
    if today >= end:
        ist_total = calc_ist(
            start, today, reading, unit, periods, ist_correction, term_months, end_reading
        )
        used = remaining = 0.0
        rate = 0.0
    else:
        elapsed = (today - start).days
        if elapsed < min_days:
            return None
        current = reading * unit_factor(unit)
        used = max(0.0, current - periods[0].reading)
        rate = used / elapsed
        ist_now = calc_ist(
            start, today, reading, unit, periods, ist_correction, term_months
        )
        extra = 0.0
        bounds = [today] + [p.start for p in periods if today < p.start < end] + [end]
        for a, b in zip(bounds, bounds[1:]):
            p = _active(periods, a)[-1]
            extra += rate * (b - a).days * (p.price + p.sewage_price)
        extra += calc_base_cost(start, end, periods, term_months) - calc_base_cost(
            start, today, periods, term_months
        )
        ist_total = round(ist_now + extra, 2)
        remaining = (end - today).days
    accuracy = round(ist_total / plan_total * 100, 1) if plan_total else None
    return {
        "accuracy": accuracy,
        "ist_forecast": ist_total,
        "plan_total": plan_total,
        "balance_forecast": round(plan_total - ist_total, 2),
        "daily_consumption": round(rate, 4),
        "remaining_days": remaining,
    }
