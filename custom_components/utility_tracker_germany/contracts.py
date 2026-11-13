"""Contract list handling: several contracts in sequence per tracker."""
from __future__ import annotations

from datetime import date
from typing import Any

from .calc import contract_end
from .const import (
    CONF_BASE_PRICE,
    CONF_CONTRACTS,
    CONF_END_READING,
    CONF_KWH_FACTOR,
    CONF_MONTHLY_ADVANCE,
    CONF_SEWAGE_PRICE,
    CONF_START_DATE,
    CONF_START_READING,
    CONF_TERM_MONTHS,
    CONF_UNIT_PRICE,
    DEFAULT_TERM_MONTHS,
)

CONTRACT_KEYS = (
    CONF_START_DATE,
    CONF_TERM_MONTHS,
    CONF_START_READING,
    CONF_UNIT_PRICE,
    CONF_SEWAGE_PRICE,
    CONF_BASE_PRICE,
    CONF_MONTHLY_ADVANCE,
    CONF_END_READING,
    CONF_KWH_FACTOR,
)


def get_contracts(entry) -> list[dict[str, Any]]:
    """Stored contracts sorted by start date.

    Trackers created before multi-contract support keep their single contract
    in entry.data (overlaid with options); it is returned as contract #1.
    """
    stored = entry.options.get(CONF_CONTRACTS)
    if stored:
        items = [dict(c) for c in stored]
    else:
        flat = {**entry.data, **entry.options}
        items = [{k: flat[k] for k in CONTRACT_KEYS if k in flat}]
    for c in items:
        c.setdefault(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS)
    items.sort(key=lambda c: str(c[CONF_START_DATE]))
    return items


def contract_span(c: dict[str, Any]) -> tuple[date, date]:
    start = date.fromisoformat(str(c[CONF_START_DATE]))
    return start, contract_end(start, int(c.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS)))


def with_end_readings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill a missing end reading with the start reading of the next contract."""
    out = [dict(c) for c in items]
    for i, c in enumerate(out[:-1]):
        if c.get(CONF_END_READING) is None:
            c[CONF_END_READING] = out[i + 1].get(CONF_START_READING)
    return out


def pick_active(items: list[dict[str, Any]], today: date) -> int:
    """Index of the running contract, else the last one started, else the first."""
    last_started = None
    for i, c in enumerate(items):
        start, end = contract_span(c)
        if start <= today < end:
            return i
        if start <= today:
            last_started = i
    return last_started if last_started is not None else 0


def entry_config(entry, today: date | None = None) -> dict[str, Any]:
    """Tracker data overlaid with the currently relevant contract (flat)."""
    items = with_end_readings(get_contracts(entry))
    return {**entry.data, **items[pick_active(items, today or date.today())]}


def check_overlap(items: list[dict[str, Any]]) -> bool:
    """True when contracts overlap."""
    spans = sorted(contract_span(c) for c in items)
    return any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1))
