"""Structured contract data for the get_contract_data action."""
from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .calc import (
    build_periods,
    calc_forecast,
    calc_ist_parts,
    calc_soll,
    contract_end,
    unit_factor,
)
from .const import (
    CONF_KWH_FACTOR,
    CONF_BASE_PRICE,
    CONF_END_READING,
    CONF_MONTHLY_ADVANCE,
    CONF_SEWAGE_PRICE,
    CONF_SOURCE_SENSOR,
    CONF_START_DATE,
    CONF_START_READING,
    CONF_TERM_MONTHS,
    CONF_TYPE,
    CONF_UNIT_PRICE,
    DEFAULT_TERM_MONTHS,
    TYPE_WATER,
    CONF_CONTRACTS,
)
from .contracts import get_contracts, pick_active, with_end_readings


def _contract_figures(
    hass: HomeAssistant, entry: ConfigEntry, cfg: dict[str, Any], today: date
) -> dict[str, Any]:
    start = date.fromisoformat(str(cfg[CONF_START_DATE]))
    term = int(cfg.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS))
    end = contract_end(start, term)
    water = cfg.get(CONF_TYPE) == TYPE_WATER
    factor = float(cfg.get(CONF_KWH_FACTOR) or 1)
    price = float(cfg[CONF_UNIT_PRICE]) * factor
    sewage = float(cfg.get(CONF_SEWAGE_PRICE) or 0)
    periods = build_periods(
        start,
        float(cfg[CONF_START_READING]),
        price,
        float(cfg[CONF_BASE_PRICE]),
        float(cfg[CONF_MONTHLY_ADVANCE]),
        None,
        sewage,
    )
    end_reading = cfg.get(CONF_END_READING)
    end_reading = float(end_reading) if end_reading is not None else None

    state = hass.states.get(cfg[CONF_SOURCE_SENSOR])
    unit = state.attributes.get("unit_of_measurement") if state else None
    reading = None
    if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
        try:
            reading = float(state.state)
        except ValueError:
            reading = None

    if today < start:
        status = "planned"
    elif today >= end:
        status = "past"
    else:
        status = "active"

    result: dict[str, Any] = {
        "status": status,
        "contract": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "term_months": term,
            "days_total": (end - start).days,
            "days_elapsed": max(0, min((today - start).days, (end - start).days)),
            "days_remaining": max((end - today).days, 0),
            "ended": today >= end,
            "end_reading": end_reading,
        },
        "tariff": {
            "unit_price": round(price + sewage, 5),
            "unit_price_per_kwh": round(price / factor, 5) if factor != 1 else None,
            "kwh_per_m3": factor if factor != 1 else None,
            "base_price_year": float(cfg[CONF_BASE_PRICE]),
            "monthly_advance": float(cfg[CONF_MONTHLY_ADVANCE]),
        },
        "meter": {"start_reading": float(cfg[CONF_START_READING])},
        "costs": {"plan": calc_soll(start, today, periods, 0.0, term)},
        "forecast": None,
    }
    if water:
        result["tariff"]["fresh_water_price"] = price
        result["tariff"]["wastewater_price"] = sewage

    if reading is not None and status != "planned":
        current = reading * unit_factor(unit)
        if today >= end and end_reading is not None:
            current = end_reading
        supply, sewage_cost = calc_ist_parts(
            start, today, reading, unit, periods, term, end_reading
        )
        costs = result["costs"]
        costs["ist"] = round(supply + sewage_cost, 2)
        costs["ist_supply_incl_base"] = supply
        if water:
            costs["ist_sewage"] = sewage_cost
        costs["balance"] = round(costs["plan"] - costs["ist"], 2)
        result["meter"]["current_reading"] = round(current, 3)
        result["meter"]["consumption_total"] = round(
            max(0.0, current - periods[0].reading), 3
        )
        fc = calc_forecast(
            start, today, reading, unit, periods,
            term_months=term, end_reading=end_reading,
        )
        if fc is not None:
            result["forecast"] = {
                "advance_coverage_percent": fc["accuracy"],
                "ist_at_end": fc["ist_forecast"],
                "plan_at_end": fc["plan_total"],
                "balance_at_end": fc["balance_forecast"],
                "daily_consumption": fc["daily_consumption"],
            }
    return result


def build_contract_data(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    today = dt_util.now().date()
    items = with_end_readings(get_contracts(entry))
    active = pick_active(items, today)
    figures = []
    for i, c in enumerate(items):
        fig = _contract_figures(hass, entry, {**entry.data, **c}, today)
        fig["index"] = i + 1
        figures.append(fig)
    water = entry.data.get(CONF_TYPE) == TYPE_WATER
    result: dict[str, Any] = {
        "name": entry.title,
        "entry_id": entry.entry_id,
        "type": entry.data.get(CONF_TYPE),
        "unit": "m3" if water else "kWh",
        "active_contract": active + 1,
    }
    result.update({k: v for k, v in figures[active].items() if k != "index"})
    result["all_contracts"] = figures
    return result