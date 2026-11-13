"""Sensors for Utility Tracker Germany."""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .calc import (
    build_periods,
    calc_forecast,
    calc_ist,
    calc_ist_parts,
    calc_soll,
    contract_end,
)
from .contracts import entry_config
from .const import (
    CONF_KWH_FACTOR,
    CONF_END_READING,
    CONF_TERM_MONTHS,
    DEFAULT_TERM_MONTHS,
    CONF_BASE_PRICE,
    CONF_MONTHLY_ADVANCE,
    CONF_SEWAGE_PRICE,
    CONF_SOURCE_SENSOR,
    CONF_START_DATE,
    CONF_START_READING,
    CONF_TYPE,
    CONF_UNIT_PRICE,
    TYPE_WATER,
    DOMAIN,
    UPDATE_INTERVAL_MINUTES,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors."""
    entities: list[_Base] = [
        UtilityPlanSensor(entry),
        UtilityIstSensor(entry),
        UtilityGuthabenSensor(entry),
    ]
    if entities[0]._has_sewage:
        entities += [
            UtilityIstPartSensor(entry, 0, "ist_bezug", "Ist Bezug"),
            UtilityIstPartSensor(entry, 1, "ist_abwasser", "Ist Abwasser"),
        ]
    entities.append(UtilityForecastSensor(entry))
    entities.append(UtilityTariffSensor(entry))
    entities.append(UtilityDaysLeftSensor(entry))
    async_add_entities(entities)


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2
    _key = ""
    _needs_source = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._load()
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title
        )

    def _load(self) -> None:
        """(Re)load the settings of the currently running contract."""
        d = entry_config(self._entry, dt_util.now().date())
        self._source = d[CONF_SOURCE_SENSOR]
        self._start = date.fromisoformat(str(d[CONF_START_DATE]))
        self._term = int(d.get(CONF_TERM_MONTHS, DEFAULT_TERM_MONTHS))
        self._periods = build_periods(
            self._start,
            float(d[CONF_START_READING]),
            float(d[CONF_UNIT_PRICE]) * float(d.get(CONF_KWH_FACTOR) or 1),
            float(d[CONF_BASE_PRICE]),
            float(d[CONF_MONTHLY_ADVANCE]),
            None,
            float(d.get(CONF_SEWAGE_PRICE) or 0),
        )
        self._factor = float(d.get(CONF_KWH_FACTOR) or 1)
        self._has_sewage = any(p.sewage_price for p in self._periods)
        er = d.get(CONF_END_READING)
        self._end_reading = float(er) if er is not None else None

    async def async_added_to_hass(self) -> None:
        if self._needs_source:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._source], self._handle_update
                )
            )
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._handle_update,
                timedelta(minutes=UPDATE_INTERVAL_MINUTES),
            )
        )
        self._refresh()

    @callback
    def _handle_update(self, *_args) -> None:
        self._load()
        self._refresh()
        self.async_write_ha_state()

    def _today(self) -> date:
        return dt_util.now().date()

    def _ist(self) -> float | None:
        state = self.hass.states.get(self._source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return None
        try:
            reading = float(state.state)
        except ValueError:
            return None
        return calc_ist(
            self._start,
            self._today(),
            reading,
            state.attributes.get("unit_of_measurement"),
            self._periods,
            term_months=self._term,
            end_reading=self._end_reading,
        )

    def _soll(self) -> float:
        return calc_soll(
            self._start, self._today(), self._periods, 0.0, self._term
        )

    @callback
    def _refresh(self) -> None:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self._attr_native_value is not None


class UtilityPlanSensor(_Base):
    _key = "soll"
    _attr_name = "Plan"
    _needs_source = False

    @callback
    def _refresh(self) -> None:
        self._attr_native_value = self._soll()


class UtilityIstSensor(_Base):
    _key = "ist"
    _attr_name = "Ist"

    @callback
    def _refresh(self) -> None:
        self._attr_native_value = self._ist()


class UtilityGuthabenSensor(_Base):
    _key = "differenz"
    _attr_name = "Guthaben"

    @callback
    def _refresh(self) -> None:
        ist = self._ist()
        self._attr_native_value = None if ist is None else round(self._soll() - ist, 2)


class UtilityIstPartSensor(_Base):
    """Actual cost split: supply (Bezug) or sewage (Abwasser), without corrections."""

    def __init__(self, entry: ConfigEntry, index: int, key: str, name: str) -> None:
        self._key = key
        self._attr_name = name
        self._index = index
        super().__init__(entry)

    @callback
    def _refresh(self) -> None:
        state = self.hass.states.get(self._source)
        self._attr_native_value = None
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return
        try:
            reading = float(state.state)
        except ValueError:
            return
        self._attr_native_value = calc_ist_parts(
            self._start,
            self._today(),
            reading,
            state.attributes.get("unit_of_measurement"),
            self._periods,
            term_months=self._term,
            end_reading=self._end_reading,
        )[self._index]


class UtilityForecastSensor(_Base):
    """Projected Ist at contract end relative to the planned advances, in percent."""

    _key = "prognose"
    _attr_name = "Abschlagsdeckung"
    _attr_device_class = None
    _attr_native_unit_of_measurement = "%"
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:chart-line"

    @callback
    def _refresh(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        state = self.hass.states.get(self._source)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return
        try:
            reading = float(state.state)
        except ValueError:
            return
        result = calc_forecast(
            self._start,
            self._today(),
            reading,
            state.attributes.get("unit_of_measurement"),
            self._periods,
            term_months=self._term,
            end_reading=self._end_reading,
        )
        if result is None:
            self._attr_extra_state_attributes = {"reason": "not_enough_data"}
            return
        self._attr_native_value = result.pop("accuracy")
        self._attr_extra_state_attributes = result


class UtilityTariffSensor(_Base):
    """Currently valid tariff; attributes list all periods incl. planned ones."""

    _key = "tarif"
    _attr_name = "Tarif"
    _attr_device_class = None
    _attr_native_unit_of_measurement = None
    _attr_suggested_display_precision = None
    _attr_icon = "mdi:cash-clock"
    _needs_source = False

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self._unit = "m3" if entry.data.get(CONF_TYPE) == TYPE_WATER else "kWh"

    def _describe(self, p) -> dict:
        data = {
            "valid_from": p.start.isoformat(),
            "unit_price": round((p.price + p.sewage_price) / self._factor, 5),
            "base_price_year": p.base_year,
            "monthly_advance": p.advance,
        }
        if p.sewage_price:
            data["fresh_water_price"] = p.price
            data["wastewater_price"] = p.sewage_price
        return data

    @callback
    def _refresh(self) -> None:
        today = self._today()
        periods = []
        current = None
        for p in self._periods:
            item = self._describe(p)
            if p.start <= today:
                item["status"] = "past"
                current = item
            else:
                item["status"] = "planned"
            periods.append(item)
        if current is None:
            current = periods[0]
        current["status"] = "active"
        planned = [i for i in periods if i["status"] == "planned"]
        self._attr_native_value = (
            f"{current['unit_price']} EUR/{self._unit}, "
            f"{current['monthly_advance']} EUR/month"
        )
        self._attr_extra_state_attributes = {
            "current": current,
            "next_change": planned[0]["valid_from"] if planned else None,
            "planned": planned,
            "periods": periods,
            "unit": self._unit,
        }


class UtilityDaysLeftSensor(_Base):
    """Countdown in days until the contract ends."""

    _key = "restlaufzeit"
    _attr_name = "Restlaufzeit"
    _attr_device_class = None
    _attr_native_unit_of_measurement = "d"
    _attr_suggested_display_precision = 0
    _needs_source = False

    @callback
    def _refresh(self) -> None:
        end = contract_end(self._start, self._term)
        self._attr_native_value = max((end - self._today()).days, 0)
        self._attr_extra_state_attributes = {"contract_end": end.isoformat()}