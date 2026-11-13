"""Utility Tracker Germany integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

PLATFORMS = ["sensor"]
SERVICE_GET_CONTRACT_DATA = "get_contract_data"
SERVICE_SCHEMA = vol.Schema({vol.Optional("entity_id"): vol.Any(str, [str])})


async def _get_contract_data(call: ServiceCall) -> dict:
    from .data import build_contract_data

    hass = call.hass
    ids = call.data.get("entity_id")
    if isinstance(ids, str):
        ids = [ids]
    entries = hass.config_entries.async_entries(DOMAIN)
    if ids:
        reg = er.async_get(hass)
        wanted = set()
        for eid in ids:
            ent = reg.async_get(eid)
            if ent is not None and ent.config_entry_id:
                wanted.add(ent.config_entry_id)
        entries = [e for e in entries if e.entry_id in wanted]
    return {
        "contracts": [
            build_contract_data(hass, e) for e in entries if e.state.value == "loaded"
        ]
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.services.has_service(DOMAIN, SERVICE_GET_CONTRACT_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_CONTRACT_DATA,
            _get_contract_data,
            schema=SERVICE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    remaining = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    if ok and not remaining:
        hass.services.async_remove(DOMAIN, SERVICE_GET_CONTRACT_DATA)
    return ok
