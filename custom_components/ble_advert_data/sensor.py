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
from .const import (
    CONF_ENDIAN,
    CONF_LENGTH,
    CONF_OFFSET,
    CONF_RULE_ID,
    CONF_RULE_NAME,
    CONF_SCALE,
    CONF_SIGNED,
    CONF_SOURCE_KEY,
    CONF_SOURCE_TYPE,
    CONF_UNIT,
    DOMAIN,
    ENDIAN_BIG,
    ENDIAN_LITTLE,
    SOURCE_MANUFACTURER,
    SOURCE_RAW,
    SOURCE_SERVICE,
    CONF_RULES,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BleAdvertDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BLE advert data sensors."""
    rules = [
        rule
        for rule in entry.options.get(CONF_RULES, [])
        if isinstance(rule, dict)
    ]
    entities: list[SensorEntity] = [BleAdvertDataSensor(entry)]
    entities.extend(
        BleAdvertDataByteSensor(entry, rule, index)
        for index, rule in enumerate(rules)
    )
    async_add_entities(entities, True)


class BleAdvertDataBaseSensor(SensorEntity):
    """Base class for BLE advertisement sensors."""

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the BLE advertisement sensor."""
        self._address = entry.data[CONF_ADDRESS]
        formatted_address = format_mac(self._address)
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, formatted_address)},
            name=entry.title,
        )

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
        raise NotImplementedError


class BleAdvertDataSensor(BleAdvertDataBaseSensor):
    """Representation of a BLE advertisement sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "advertisement"

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the BLE advertisement sensor."""
        super().__init__(entry)
        formatted_address = format_mac(self._address)
        self._attr_unique_id = f"{formatted_address}_advertisement"
        self._attr_extra_state_attributes = self._build_attributes(None)

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


class BleAdvertDataByteSensor(BleAdvertDataBaseSensor):
    """Representation of a BLE advertisement byte sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry: BleAdvertDataConfigEntry,
        rule: dict[str, Any],
        index: int,
    ) -> None:
        """Initialize the BLE advertisement byte sensor."""
        super().__init__(entry)
        formatted_address = format_mac(self._address)
        rule_id = rule.get(CONF_RULE_ID) or f"rule_{index}"
        self._rule = rule
        self._attr_unique_id = f"{formatted_address}_rule_{rule_id}"
        self._attr_name = rule.get(CONF_RULE_NAME, f"Rule {index + 1}")
        self._attr_native_unit_of_measurement = rule.get(CONF_UNIT)
        self._attr_extra_state_attributes = self._build_attributes(None, None)

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor attributes from service info."""
        value, raw_hex = _parse_rule_value(service_info, self._rule)
        self._attr_native_value = value
        self._attr_extra_state_attributes = self._build_attributes(service_info, raw_hex)
        self._attr_available = True

    def _build_attributes(
        self,
        service_info: BluetoothServiceInfoBleak | None,
        raw_hex: str | None,
    ) -> dict[str, Any]:
        """Build extra state attributes."""
        return {
            "name": service_info.name if service_info else None,
            "address": self._address,
            "source_type": self._rule.get(CONF_SOURCE_TYPE),
            "source_key": self._rule.get(CONF_SOURCE_KEY),
            "offset": self._rule.get(CONF_OFFSET),
            "length": self._rule.get(CONF_LENGTH),
            "endian": self._rule.get(CONF_ENDIAN),
            "signed": self._rule.get(CONF_SIGNED),
            "scale": self._rule.get(CONF_SCALE),
            "unit": self._rule.get(CONF_UNIT),
            "raw_bytes": raw_hex,
        }


def _parse_rule_value(
    service_info: BluetoothServiceInfoBleak, rule: dict[str, Any]
) -> tuple[float | None, str | None]:
    """Parse a rule value from service info."""
    data = _extract_rule_bytes(service_info, rule)
    if not data:
        return None, None

    offset = int(rule.get(CONF_OFFSET, 0))
    length = int(rule.get(CONF_LENGTH, 0))
    if length <= 0 or offset < 0:
        return None, None

    end = offset + length
    if end > len(data):
        return None, None

    chunk = data[offset:end]
    if not chunk:
        return None, None

    endian = rule.get(CONF_ENDIAN, ENDIAN_BIG)
    signed = bool(rule.get(CONF_SIGNED, False))
    byteorder = "little" if endian == ENDIAN_LITTLE else "big"
    value = int.from_bytes(chunk, byteorder=byteorder, signed=signed)
    scale = float(rule.get(CONF_SCALE, 1.0))
    return value * scale, chunk.hex()


def _extract_rule_bytes(
    service_info: BluetoothServiceInfoBleak, rule: dict[str, Any]
) -> bytes | None:
    """Extract bytes for a rule."""
    source_type = rule.get(CONF_SOURCE_TYPE)
    source_key = rule.get(CONF_SOURCE_KEY)

    if source_type == SOURCE_MANUFACTURER:
        if not source_key:
            return None
        key = _parse_int(source_key)
        if key is None:
            return None
        return (service_info.manufacturer_data or {}).get(key)

    if source_type == SOURCE_SERVICE:
        if not source_key:
            return None
        service_data = service_info.service_data or {}
        if source_key in service_data:
            return service_data.get(source_key)
        return service_data.get(source_key.lower())

    if source_type == SOURCE_RAW:
        return _get_raw_bytes(service_info)

    return None


def _get_raw_bytes(service_info: BluetoothServiceInfoBleak) -> bytes | None:
    """Return the raw advertisement bytes, if available."""
    advertisement = getattr(service_info, "advertisement", None)
    if advertisement is None:
        return None

    raw_data = getattr(advertisement, "data", None) or getattr(
        advertisement, "raw_data", None
    )
    if isinstance(raw_data, (bytes, bytearray)):
        return bytes(raw_data)

    return None


def _parse_int(value: str) -> int | None:
    """Parse a string into an int, supporting hex."""
    try:
        return int(value, 0)
    except ValueError:
        return None
