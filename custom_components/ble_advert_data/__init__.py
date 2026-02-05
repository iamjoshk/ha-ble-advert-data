"""Integration for BLE advertisement data."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass(slots=True)
class BleAdvertDataRuntime:
    """Runtime data for the BLE advert data integration."""

    address: str


type BleAdvertDataConfigEntry = ConfigEntry[BleAdvertDataRuntime]


async def async_setup_entry(
    hass: HomeAssistant, entry: BleAdvertDataConfigEntry
) -> bool:
    """Set up BLE advert data from a config entry."""
    entry.runtime_data = BleAdvertDataRuntime(address=entry.data[CONF_ADDRESS])
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BleAdvertDataConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
