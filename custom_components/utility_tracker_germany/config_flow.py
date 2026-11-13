"""Config flow for Utility Tracker Germany."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .calc import unit_factor
from .contracts import (
    check_overlap,
    contract_span,
    get_contracts,
    pick_active,
    with_end_readings,
)
from .const import (
    CONF_KWH_FACTOR,
    TYPE_GAS,
    CONF_CONTRACTS,
    CONF_BASE_PRICE,
    CONF_END_READING,
    CONF_MONTHLY_ADVANCE,
    CONF_NAME,
    CONF_SEWAGE_PRICE,
    CONF_SOURCE_SENSOR,
    CONF_START_DATE,
    CONF_START_READING,
    CONF_TERM_MONTHS,
    CONF_TYPE,
    CONF_UNIT_PRICE,
    DEFAULT_TERM_MONTHS,
    DOMAIN,
    TYPE_ELECTRICITY,
    TYPE_WATER,
    TYPES,
)

EUR = "EUR"
M3 = "m\u00b3"


def _number(unit: str | None = None, minimum: float = 0) -> selector.NumberSelector:
    config: dict[str, Any] = {
        "min": minimum,
        "max": 10000000,
        "step": "any",
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _int_box(minimum: int, maximum: int, unit: str | None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            **({"unit_of_measurement": unit} if unit else {}),
        )
    )


def _step1_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
            vol.Required(
                CONF_TYPE, default=d.get(CONF_TYPE, TYPE_ELECTRICITY)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TYPES,
                    translation_key="type",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_SOURCE_SENSOR, default=d.get(CONF_SOURCE_SENSOR, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_START_DATE, default=d.get(CONF_START_DATE, vol.UNDEFINED)
            ): selector.DateSelector(),
            vol.Required(
                CONF_TERM_MONTHS, default=d.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS)
            ): _int_box(1, 120, None),
            vol.Required(
                CONF_START_READING, default=d.get(CONF_START_READING, 0)
            ): _number(minimum=-10000000),
        }
    )


def _step2_schema(d: dict[str, Any], water: bool, gas: bool = False) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if gas:
        fields[vol.Required(CONF_KWH_FACTOR, default=d.get(CONF_KWH_FACTOR, 10))] = _number()
    fields[vol.Required(CONF_UNIT_PRICE, default=d.get(CONF_UNIT_PRICE, 0))] = _number(EUR)
    if water:
        fields[
            vol.Required(CONF_SEWAGE_PRICE, default=d.get(CONF_SEWAGE_PRICE, 0))
        ] = _number(EUR)
    fields[vol.Required(CONF_BASE_PRICE, default=d.get(CONF_BASE_PRICE, 0))] = _number(
        EUR
    )
    fields[
        vol.Required(CONF_MONTHLY_ADVANCE, default=d.get(CONF_MONTHLY_ADVANCE, 0))
    ] = _number(EUR)
    return vol.Schema(fields)


class UtilityTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow (2 steps)."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return UtilityTrackerOptionsFlow()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Step 1: name, type, source sensor, contract start and term."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_NAME] = user_input[CONF_NAME].strip()
            if not user_input[CONF_NAME]:
                errors[CONF_NAME] = "name_required"
            try:
                date.fromisoformat(str(user_input[CONF_START_DATE]))
            except ValueError:
                errors[CONF_START_DATE] = "invalid_date"
            if self.hass.states.get(user_input[CONF_SOURCE_SENSOR]) is None:
                errors[CONF_SOURCE_SENSOR] = "source_not_found"
            if not errors:
                user_input[CONF_TERM_MONTHS] = int(user_input[CONF_TERM_MONTHS])
                self._data.update(user_input)
                return await self._prices_step()
        d = user_input or self._data
        return self.async_show_form(
            step_id="user", data_schema=_step1_schema(d), errors=errors
        )

    async def _prices_step(self, user_input: dict[str, Any] | None = None):
        """Step 2: prices; the step id depends on the contract type."""
        kind = self._data[CONF_TYPE]
        water = kind == TYPE_WATER
        errors: dict[str, str] = {}
        if user_input is not None:
            if any(v < 0 for v in user_input.values()):
                errors["base"] = "negative_value"
            elif kind == TYPE_GAS and user_input[CONF_KWH_FACTOR] <= 0:
                errors["base"] = "negative_value"
            else:
                if not water:
                    user_input[CONF_SEWAGE_PRICE] = 0
                self._data.update(user_input)
                return await self._finish()
        d = {**self._data, **(user_input or {})}
        return self.async_show_form(
            step_id=f"prices_{kind}",
            data_schema=_step2_schema(d, water, kind == TYPE_GAS),
            errors=errors,
        )

    async def _finish(self):
        await self.async_set_unique_id(
            f"{self._data[CONF_SOURCE_SENSOR]}_{self._data[CONF_NAME]}".lower()
        )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

    async def async_step_prices_electricity(self, user_input=None):
        return await self._prices_step(user_input)

    async def async_step_prices_gas(self, user_input=None):
        return await self._prices_step(user_input)

    async def async_step_prices_water(self, user_input=None):
        return await self._prices_step(user_input)


def _contract_schema(
    c: dict[str, Any], water: bool, suggested_end: float | None = None, gas: bool = False
) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_START_DATE, default=c.get(CONF_START_DATE, vol.UNDEFINED)
        ): selector.DateSelector(),
        vol.Required(
            CONF_TERM_MONTHS, default=c.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS)
        ): _int_box(1, 120, None),
        vol.Required(
            CONF_START_READING, default=c.get(CONF_START_READING, 0)
        ): _number(minimum=-10000000),
        vol.Required(CONF_UNIT_PRICE, default=c.get(CONF_UNIT_PRICE, 0)): _number(EUR),
    }
    if gas:
        fields[
            vol.Required(CONF_KWH_FACTOR, default=c.get(CONF_KWH_FACTOR) or 1)
        ] = _number()
    if water:
        fields[
            vol.Required(CONF_SEWAGE_PRICE, default=c.get(CONF_SEWAGE_PRICE) or 0)
        ] = _number(EUR)
    fields[vol.Required(CONF_BASE_PRICE, default=c.get(CONF_BASE_PRICE, 0))] = _number(
        EUR
    )
    fields[
        vol.Required(CONF_MONTHLY_ADVANCE, default=c.get(CONF_MONTHLY_ADVANCE, 0))
    ] = _number(EUR)
    fields[
        vol.Optional(CONF_END_READING, description={"suggested_value": suggested_end})
    ] = _number(minimum=-10000000)
    return vol.Schema(fields)


class UtilityTrackerOptionsFlow(config_entries.OptionsFlow):
    """Contract overview, add / adjust / delete contracts."""

    def __init__(self) -> None:
        self._index: int | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init", menu_options=["overview", "add", "adjust", "delete"]
        )

    def _contracts(self) -> list[dict[str, Any]]:
        return get_contracts(self.config_entry)

    def _gas(self) -> bool:
        return self.config_entry.data.get(CONF_TYPE) == TYPE_GAS

    def _water(self) -> bool:
        return self.config_entry.data.get(CONF_TYPE) == TYPE_WATER

    def _save(self, items: list[dict[str, Any]]):
        items = sorted(items, key=lambda c: str(c[CONF_START_DATE]))
        return self.async_create_entry(data={CONF_CONTRACTS: items})

    def _label(self, i: int, c: dict[str, Any]) -> str:
        start, end = contract_span(c)
        return f"{i + 1}: {self._fmt_date(start)} \u2013 {self._fmt_date(end)}"

    def _validate(
        self, user_input: dict[str, Any], others: list[dict[str, Any]]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        try:
            date.fromisoformat(str(user_input[CONF_START_DATE]))
        except ValueError:
            errors[CONF_START_DATE] = "invalid_date"
            return errors
        keys = (CONF_UNIT_PRICE, CONF_SEWAGE_PRICE, CONF_BASE_PRICE, CONF_MONTHLY_ADVANCE)
        if user_input.get(CONF_KWH_FACTOR) is not None and user_input[CONF_KWH_FACTOR] <= 0:
            errors["base"] = "negative_value"
        elif any(user_input[k] < 0 for k in keys if user_input.get(k) is not None):
            errors["base"] = "negative_value"
        elif check_overlap([*others, user_input]):
            errors["base"] = "overlap"
        return errors

    @staticmethod
    def _clean(user_input: dict[str, Any], water: bool) -> dict[str, Any]:
        c = {
            CONF_START_DATE: str(user_input[CONF_START_DATE]),
            CONF_TERM_MONTHS: int(user_input[CONF_TERM_MONTHS]),
            CONF_START_READING: user_input[CONF_START_READING],
            CONF_UNIT_PRICE: user_input[CONF_UNIT_PRICE],
            CONF_SEWAGE_PRICE: user_input.get(CONF_SEWAGE_PRICE) or 0 if water else 0,
            CONF_BASE_PRICE: user_input[CONF_BASE_PRICE],
            CONF_MONTHLY_ADVANCE: user_input[CONF_MONTHLY_ADVANCE],
        }
        if user_input.get(CONF_KWH_FACTOR):
            c[CONF_KWH_FACTOR] = user_input[CONF_KWH_FACTOR]
        if user_input.get(CONF_END_READING) is not None:
            c[CONF_END_READING] = user_input[CONF_END_READING]
        return c

    async def async_step_overview(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="overview",
            data_schema=vol.Schema({}),
            description_placeholders={"summary": await self._summary()},
        )

    async def _texts(self) -> dict[str, str]:
        """Overview strings from the translation files of the UI language."""
        from homeassistant.helpers.translation import async_get_translations

        lang = self.hass.config.language
        prefix = f"component.{DOMAIN}.options.step.overview."
        found: dict[str, str] = {}
        for code in ("en", lang):
            tr = await async_get_translations(self.hass, code, "options", [DOMAIN])
            found.update(
                {k[len(prefix):]: v for k, v in tr.items() if k.startswith(prefix)}
            )
        return found

    def _fmt_date(self, d: date) -> str:
        try:
            from babel.dates import format_date

            return format_date(d, format="medium", locale=self.hass.config.language)
        except Exception:  # noqa: BLE001 - babel is optional
            if str(self.hass.config.language).startswith(("de", "fr", "es", "it", "nl", "pl")):
                return d.strftime("%d.%m.%Y")
            return d.isoformat()

    def _fmt_num(self, value: float) -> str:
        try:
            from babel.numbers import format_decimal

            return format_decimal(
                value, format="#,##0.#####", locale=self.hass.config.language
            )
        except Exception:  # noqa: BLE001 - babel is optional
            text = f"{value:.5f}".rstrip("0").rstrip(".")
            if str(self.hass.config.language).startswith("de"):
                text = text.replace(".", ",")
            return text

    async def _summary(self) -> str:
        t = await self._texts()
        items = with_end_readings(self._contracts())
        today = date.today()
        active = pick_active(items, today)
        gas = self._gas()
        meter_unit = "m\u00b3" if (self._water() or gas) else "kWh"
        price_unit = "kWh" if gas else meter_unit
        blocks = [f"**{self.config_entry.title}**"]
        for i, c in enumerate(items):
            start, end = contract_span(c)
            price = float(c[CONF_UNIT_PRICE]) + float(c.get(CONF_SEWAGE_PRICE) or 0)
            if today < start:
                status = t.get("status_planned", "planned")
            elif today >= end:
                status = t.get("status_ended", "ended")
            else:
                status = t.get("status_running", "running")
            left = max((end - today).days, 0)
            er = c.get(CONF_END_READING)
            fmt = self._fmt_num
            lines = [
                t["contract_line"].format(
                    n=i + 1,
                    status=status,
                    mark=" \u2b50" if i == active else "",
                    start=self._fmt_date(start),
                    end=self._fmt_date(end),
                    term=c[CONF_TERM_MONTHS],
                    left=left,
                ),
                t["reading_line"].format(
                    start=fmt(float(c[CONF_START_READING])), unit=meter_unit
                )
                + (
                    t["reading_end"].format(end=fmt(float(er)), unit=meter_unit)
                    if er is not None
                    else ""
                ),
                t["price_line"].format(
                    price=fmt(price),
                    unit=price_unit,
                    base=fmt(float(c[CONF_BASE_PRICE])),
                    advance=fmt(float(c[CONF_MONTHLY_ADVANCE])),
                ),
            ]
            factor = c.get(CONF_KWH_FACTOR)
            if gas and factor:
                lines.append(t["factor_line"].format(factor=fmt(float(factor))))
            blocks.append("\n\n".join(lines))
        return "\n\n---\n\n".join(blocks)

    async def async_step_add(self, user_input: dict[str, Any] | None = None):
        items = self._contracts()
        water = self._water()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input, items)
            if not errors:
                return self._save([*items, self._clean(user_input, water)])
        last = items[-1]
        _, last_end = contract_span(last)
        defaults = dict(user_input or {})
        if user_input is None:
            reading = last.get(CONF_END_READING)
            if reading is None:
                reading = await self._suggest_reading(last_end)
            defaults = {
                CONF_START_DATE: last_end.isoformat(),
                CONF_TERM_MONTHS: last.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS),
                CONF_START_READING: reading if reading is not None else 0,
                CONF_UNIT_PRICE: last.get(CONF_UNIT_PRICE, 0),
                CONF_KWH_FACTOR: last.get(CONF_KWH_FACTOR),
                CONF_SEWAGE_PRICE: last.get(CONF_SEWAGE_PRICE, 0),
                CONF_BASE_PRICE: last.get(CONF_BASE_PRICE, 0),
                CONF_MONTHLY_ADVANCE: last.get(CONF_MONTHLY_ADVANCE, 0),
            }
        return self.async_show_form(
            step_id="add", data_schema=_contract_schema(defaults, water, None, self._gas()), errors=errors
        )

    def _select_schema(self) -> vol.Schema:
        options = [
            selector.SelectOptionDict(value=str(i), label=self._label(i, c))
            for i, c in enumerate(self._contracts())
        ]
        return vol.Schema(
            {
                vol.Required("contract"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options, mode=selector.SelectSelectorMode.LIST
                    )
                )
            }
        )

    async def async_step_adjust(self, user_input: dict[str, Any] | None = None):
        items = self._contracts()
        if len(items) == 1:
            self._index = 0
            return await self.async_step_adjust_form()
        if user_input is not None:
            self._index = int(user_input["contract"])
            return await self.async_step_adjust_form()
        return self.async_show_form(step_id="adjust", data_schema=self._select_schema())

    async def async_step_adjust_form(self, user_input: dict[str, Any] | None = None):
        items = self._contracts()
        idx = self._index or 0
        current = items[idx]
        water = self._water()
        errors: dict[str, str] = {}
        if user_input is not None:
            others = [c for i, c in enumerate(items) if i != idx]
            errors = self._validate(user_input, others)
            if not errors:
                return self._save([*others, self._clean(user_input, water)])
        suggested_end = current.get(CONF_END_READING)
        if suggested_end is None and idx == len(items) - 1:
            _, end_d = contract_span(current)
            if end_d <= date.today():
                suggested_end = await self._suggest_reading(end_d)
        return self.async_show_form(
            step_id="adjust_form",
            data_schema=_contract_schema(user_input or current, water, suggested_end, self._gas()),
            errors=errors,
            description_placeholders={"contract": self._label(idx, current)},
        )

    async def async_step_delete(self, user_input: dict[str, Any] | None = None):
        items = self._contracts()
        if len(items) == 1:
            self._index = 0
            return await self.async_step_delete_confirm()
        if user_input is not None:
            self._index = int(user_input["contract"])
            return await self.async_step_delete_confirm()
        return self.async_show_form(step_id="delete", data_schema=self._select_schema())

    async def async_step_delete_confirm(self, user_input: dict[str, Any] | None = None):
        items = self._contracts()
        idx = self._index or 0
        last_one = len(items) == 1
        if user_input is not None:
            if not user_input.get("confirm"):
                return self.async_abort(reason="not_deleted")
            if last_one:
                self.hass.async_create_task(
                    self.hass.config_entries.async_remove(self.config_entry.entry_id)
                )
                return self.async_abort(reason="deleted")
            return self._save([c for i, c in enumerate(items) if i != idx])
        return self.async_show_form(
            step_id="delete_confirm_last" if last_one else "delete_confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={
                "name": self.config_entry.title,
                "contract": self._label(idx, items[idx]),
            },
        )

    async def async_step_delete_confirm_last(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self.async_step_delete_confirm(user_input)

    async def _suggest_reading(self, d: date) -> float | None:
        """Meter reading at the start of `d` from long-term statistics, in kWh/m3."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
            from homeassistant.util import dt as dt_util

            src = self.config_entry.data[CONF_SOURCE_SENSOR]
            begin = dt_util.start_of_local_day(d)
            result = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                begin,
                begin + timedelta(days=2),
                {src},
                "hour",
                None,
                {"state"},
            )
            rows = result.get(src) or []
            if not rows or rows[0].get("state") is None:
                return None
            state = self.hass.states.get(src)
            unit = state.attributes.get("unit_of_measurement") if state else None
            return round(float(rows[0]["state"]) * unit_factor(unit), 3)
        except Exception:  # noqa: BLE001 - suggestion is optional
            return None
