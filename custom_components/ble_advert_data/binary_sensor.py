"""Binary sensors for BLE advertisement data."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from . import BleAdvertDataConfigEntry
from .const import DOMAIN

CONNECTIVITY_TIMEOUT = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BleAdvertDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE advert data binary sensors."""
    async_add_entities([BleAdvertConnectivitySensor(entry)], True)


class BleAdvertConnectivitySensor(BinarySensorEntity):
    """Representation of a BLE connectivity sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_translation_key = "connectivity"

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the BLE connectivity sensor."""
        self._address = entry.data[CONF_ADDRESS]
        formatted_address = format_mac(self._address)
        self._attr_unique_id = f"{formatted_address}_connectivity"
        self._attr_is_on = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, formatted_address)},
            name=entry.title,
        )
        self._last_seen: float | None = None
        self._timeout_cancel = None

    async def async_added_to_hass(self) -> None:
        """Register for Bluetooth updates."""
        for info in bluetooth.async_discovered_service_info(self.hass):
            if info.address == self._address:
                self._update_connectivity(info.time)
                break

        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_handle_bluetooth,
                BluetoothCallbackMatcher(address=self._address),
                BluetoothScanningMode.ACTIVE,
            )
        )

        # Start periodic check for timeout
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_check_timeout, timedelta(seconds=5)
            )
        )

    @callback
    def _async_handle_bluetooth(
        self, service_info: BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        """Handle Bluetooth updates."""
        self._update_connectivity(service_info.time)
        self.async_write_ha_state()

    def _update_connectivity(self, timestamp: float) -> None:
        """Update connectivity based on timestamp."""
        self._last_seen = timestamp
        self._attr_is_on = True

    @callback
    def _async_check_timeout(self, _now) -> None:
        """Check if the device has timed out."""
        if self._last_seen is None:
            return

        time_since_last_seen = _now.timestamp() - self._last_seen
        if time_since_last_seen > CONNECTIVITY_TIMEOUT.total_seconds():
            if self._attr_is_on:
                self._attr_is_on = False
                self.async_write_ha_state()
