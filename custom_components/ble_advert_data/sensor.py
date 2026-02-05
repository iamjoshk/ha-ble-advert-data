"""Sensors for BLE advertisement data."""

from __future__ import annotations

from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_ADDRESS, SIGNAL_STRENGTH_DECIBELS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BleAdvertDataConfigEntry
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BleAdvertDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE advert data sensors."""
    async_add_entities([BleAdvertDataSensor(entry)], True)


class BleAdvertDataSensor(SensorEntity):
    """Representation of a BLE advertisement sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "advertisement"

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the BLE advertisement sensor."""
        self._address = entry.data[CONF_ADDRESS]
        formatted_address = format_mac(self._address)
        self._attr_unique_id = f"{formatted_address}_advertisement"
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, formatted_address)},
            name=entry.title,
        )
        self._attr_extra_state_attributes = self._build_attributes(None)

    async def async_added_to_hass(self) -> None:
        """Register for Bluetooth updates."""
        for info in bluetooth.async_discovered_service_info(self.hass):
            if info.address == self._address:
                self._update_from_service_info(info)
                break

        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_handle_bluetooth,
                BluetoothCallbackMatcher(address=self._address),
                BluetoothScanningMode.ACTIVE,
            )
        )

    @callback
    def _async_handle_bluetooth(
        self, service_info: BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        """Handle Bluetooth updates."""
        self._update_from_service_info(service_info)
        self.async_write_ha_state()

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor attributes from service info."""
        self._attr_native_value = service_info.rssi
        self._attr_extra_state_attributes = self._build_attributes(service_info)
        self._attr_available = True

    def _build_attributes(
        self, service_info: BluetoothServiceInfoBleak | None
    ) -> dict[str, Any]:
        """Build the extra state attributes."""
        if service_info is None:
            return {
                "name": None,
                "address": self._address,
                "rssi": None,
                "manufacturer_data": {},
                "service_data": {},
                "service_uuids": [],
                "source": None,
                "connectable": None,
                "time": None,
                "tx_power": None,
                "raw": None,
            }

        manufacturer_data = {
            str(key): value.hex()
            for key, value in (service_info.manufacturer_data or {}).items()
        }
        service_data = {
            key: value.hex() for key, value in (service_info.service_data or {}).items()
        }
        service_uuids = list(service_info.service_uuids or [])

        raw_hex: str | None = None
        advertisement = getattr(service_info, "advertisement", None)
        if advertisement is not None:
            raw_data = getattr(advertisement, "data", None) or getattr(
                advertisement, "raw_data", None
            )
            if isinstance(raw_data, (bytes, bytearray)):
                raw_hex = bytes(raw_data).hex()

        return {
            "name": service_info.name,
            "address": service_info.address,
            "rssi": service_info.rssi,
            "manufacturer_data": manufacturer_data,
            "service_data": service_data,
            "service_uuids": service_uuids,
            "source": service_info.source,
            "connectable": service_info.connectable,
            "time": service_info.time,
            "tx_power": service_info.tx_power,
            "raw": raw_hex,
        }
