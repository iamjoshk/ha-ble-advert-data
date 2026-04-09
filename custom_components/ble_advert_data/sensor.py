"""Sensors for BLE advertisement data."""

from __future__ import annotations

from datetime import datetime
from homeassistant.core import Event, HomeAssistant, callback
from typing import Any
import asyncio
import time
import logging

from bleak import BleakClient
from bleak.exc import BleakError

# Optional helper from bleak-retry-connector; import lazily at runtime
try:
    from bleak_retry_connector import establish_connection as _establish_connection  # type: ignore
    _HAS_RETRY_CONNECTOR = True
except Exception:  # pragma: no cover - optional
    _establish_connection = None  # type: ignore
    _HAS_RETRY_CONNECTOR = False

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
from homeassistant.helpers.restore_state import RestoreEntity

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

# GATT Battery Service UUIDs (standard)
GATT_BATTERY_SERVICE_UUID = "180f"
GATT_BATTERY_LEVEL_CHAR_UUID = "2a19"


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
    
    # Add latest MAC sensor if fingerprinting is enabled
    if entry.options.get("service_data_fingerprint"):
        entities.append(BleAdvertDataLatestMacSensor(entry))
    
    # Add GATT battery sensor if GATT fetching is enabled
    if entry.options.get("enable_gatt_fetch"):
        entities.append(BleAdvertDataGattBatterySensor(entry))
    
    entities.extend(
        BleAdvertDataByteSensor(entry, rule, index)
        for index, rule in enumerate(rules)
    )
    async_add_entities(entities, True)


class BleAdvertDataBaseSensor(RestoreEntity, SensorEntity):
    """Base class for BLE advertisement sensors."""

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the BLE advertisement sensor."""
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        formatted_address = format_mac(self._address)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, formatted_address)},
            name=entry.title,
        )
        # Service data fingerprinting for randomized MAC tracking
        self._service_data_fingerprint: dict[str, str] | None = entry.options.get(
            "service_data_fingerprint"
        )
        self._logger = logging.getLogger(__name__)

    def _matches_device(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if service info matches this device by MAC or service data fingerprint."""
        # Primary: match by MAC address
        if service_info.address == self._address:
            return True
        
        # Secondary: match by service data fingerprint (for randomized MACs)
        if self._service_data_fingerprint:
            device_service_data = service_info.service_data or {}
            for uuid, fingerprint in self._service_data_fingerprint.items():
                if uuid in device_service_data:
                    data_hex = device_service_data[uuid].hex()
                    # Match if fingerprint is a prefix of the actual data
                    if data_hex.startswith(fingerprint):
                        if service_info.address != self._address:
                            self._logger.debug(
                                "Device fingerprint matched: %s (was %s, now %s)",
                                service_info.name or "Unknown",
                                self._address,
                                service_info.address,
                            )
                            # Update runtime data with the latest matching MAC and timestamp
                            self._entry.runtime_data.latest_fingerprint_mac = service_info.address
                            self._entry.runtime_data.latest_fingerprint_time = service_info.time
                        return True
        
        return False

    async def async_added_to_hass(self) -> None:
        """Register for Bluetooth updates and restore last value."""
        # Restore last valid state if available
        last_state = await self.async_get_last_state()
        if (
            last_state is not None
            and last_state.state not in ("unknown", "unavailable")
            and last_state.state is not None
        ):
            self._restore_last_state(last_state)

        for info in bluetooth.async_discovered_service_info(self.hass):
            if self._matches_device(info):
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

    def _restore_last_state(self, last_state) -> None:
        """Restore the last valid state. Override in subclasses as needed."""
        # Default implementation: try to restore as numeric value
        try:
            self._attr_native_value = float(last_state.state)
            self._attr_extra_state_attributes = last_state.attributes
        except (ValueError, TypeError):
            pass

    @callback
    def _async_handle_bluetooth(
        self, service_info: BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        """Handle Bluetooth updates."""
        if self._matches_device(service_info):
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
        # GATT fetch control - can be enabled via options
        self._gatt_lock: asyncio.Lock = asyncio.Lock()
        self._last_gatt_fetch: float = 0.0
        self._gatt_timeout: float = 10.0
        # Set to True once we have checked for battery service
        self._gatt_battery_checked: bool = False
        # Enable GATT fetching (can be configured via config entry options)
        self._enable_gatt_fetch: bool = entry.options.get("enable_gatt_fetch", False)
        self._logger = logging.getLogger(__name__)

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor attributes from service info."""
        self._attr_native_value = service_info.rssi
        self._attr_extra_state_attributes = self._build_attributes(service_info)
        # If GATT fetching is enabled and device is connectable, attempt GATT fetch
        try:
            if self._enable_gatt_fetch and service_info.connectable:
                now = time.time()
                # Use a 5-minute throttle for GATT fetches
                if now - self._last_gatt_fetch > 300:
                    self._last_gatt_fetch = now
                    self.hass.async_create_task(self._async_fetch_gatt(service_info.address))
        except Exception as exc:  # protect main loop from unexpected errors
            self._logger.debug("Error scheduling GATT fetch: %s", exc)

    async def _async_fetch_gatt(self, address: str) -> None:
        """Connect and discover battery data via GATT.

        Attempts to read from the standard battery service (UUID 180F)
        and battery level characteristic (UUID 2A19).
        """
        if not address:
            return

        # Avoid overlapping fetches
        async with self._gatt_lock:
            client: BleakClient | None = None
            try:
                ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, address, connectable=True
                )
                if ble_device is None:
                    self._logger.debug("GATT: no BLEDevice found for %s", address)
                    return

                self._logger.debug("Starting GATT fetch for %s", address)

                if _HAS_RETRY_CONNECTOR and _establish_connection is not None:
                    client = await _establish_connection(
                        BleakClient,
                        ble_device,
                        ble_device.address,
                        max_attempts=3,
                    )
                else:
                    client = BleakClient(ble_device, timeout=self._gatt_timeout)
                    await client.connect()

                attrs: dict[str, Any] = dict(self._attr_extra_state_attributes or {})

                # Attempt to read battery level from standard GATT battery service
                try:
                    # Try reading the battery level characteristic directly
                    # Standard UUID: 2A19 (Battery Level)
                    battery_level_uuid = "00002a19-0000-1000-8000-00805f9b34fb"
                    
                    try:
                        battery_data = await asyncio.wait_for(
                            client.read_gatt_char(battery_level_uuid),
                            timeout=5.0,
                        )
                        if battery_data:
                            battery_level = int(battery_data[0])
                            if 0 <= battery_level <= 100:
                                attrs["gatt_battery_level"] = battery_level
                                # Store in runtime data for battery sensor
                                self._entry.runtime_data.gatt_battery_level = battery_level
                                self._logger.debug(
                                    "GATT: Battery level for %s: %d%%",
                                    address,
                                    battery_level,
                                )
                                # notify listeners that battery updated
                                self.hass.bus.async_fire(
                                    f"{DOMAIN}_gatt_battery",
                                    {"address": address, "battery_level": battery_level},
                                )
                    except asyncio.TimeoutError:
                        self._logger.debug(
                            "GATT: battery read timed out for %s", address
                        )
                    except BleakError as err:
                        # Device doesn't have battery service or it's not readable
                        self._logger.debug(
                            "GATT: Failed to read battery for %s (device may not expose battery service): %s",
                            address,
                            err,
                        )

                except Exception as err:
                    self._logger.debug(
                        "GATT: Error reading battery for %s: %s", address, err
                    )

                self._attr_extra_state_attributes = attrs
                self.async_write_ha_state()

                # Mark that we've checked battery service discovery
                self._gatt_battery_checked = True

            except asyncio.TimeoutError as err:
                self._logger.debug("GATT connection timeout for %s: %s", address, err)
            except BleakError as err:
                self._logger.debug("GATT connection failed for %s: %s", address, err)
            except Exception as exc:
                self._logger.warning("GATT fetch error for %s: %s", address, exc)
            finally:
                try:
                    if client is not None and client.is_connected:
                        await client.disconnect()
                except Exception:
                    pass

    def _build_attributes(
        self, service_info: BluetoothServiceInfoBleak | None
    ) -> dict[str, Any]:
        """Build the extra state attributes."""
        attrs = {
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
        
        if service_info is None:
            return attrs

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

        # Log service data for fingerprinting devices with randomized MACs
        if service_data and not self._service_data_fingerprint:
            for uuid, data_hex in service_data.items():
                # Show first 8 characters (4 bytes) as fingerprint example
                fingerprint_example = data_hex[:8] if len(data_hex) >= 8 else data_hex
                self._logger.debug(
                    "Service data fingerprint suggestion for %s: UUID=%s, Fingerprint=%s (full: %s)",
                    service_info.name or service_info.address,
                    uuid,
                    fingerprint_example,
                    data_hex,
                )

        # Try to extract battery from advertisement data
        batt_attrs = _extract_battery_from_manufacturer_data(service_info, self._address)
        
        attrs.update({
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
        })
        
        # Add any battery data found
        attrs.update(batt_attrs)
        
        return attrs


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

    def _restore_last_state(self, last_state) -> None:
        """Restore the last valid parsed value."""
        try:
            self._attr_native_value = float(last_state.state)
            self._attr_extra_state_attributes = (
                last_state.attributes or self._build_attributes(None, None)
            )
        except (ValueError, TypeError):
            pass

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor attributes from service info."""
        value, raw_hex = _parse_rule_value(service_info, self._rule)
        self._attr_native_value = value
        self._attr_extra_state_attributes = self._build_attributes(service_info, raw_hex)

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


class BleAdvertDataLatestMacSensor(BleAdvertDataBaseSensor):
    """Representation of the latest MAC address when using service fingerprinting."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "latest_mac"

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the latest MAC sensor."""
        super().__init__(entry)
        formatted_address = format_mac(self._address)
        self._attr_unique_id = f"{formatted_address}_latest_mac"
        self._attr_native_value = entry.runtime_data.latest_fingerprint_mac
        self._update_attributes()

    def _restore_last_state(self, last_state) -> None:
        """Restore the last valid MAC address."""
        self._attr_native_value = last_state.state
        self._attr_extra_state_attributes = (
            last_state.attributes or {"last_matched": None}
        )

    def _update_attributes(self) -> None:
        """Update the sensor attributes from runtime data."""
        latest_time = self._entry.runtime_data.latest_fingerprint_time
        if latest_time is not None:
            dt = datetime.fromtimestamp(latest_time)
            self._attr_extra_state_attributes = {
                "last_matched": dt.isoformat()
            }
        else:
            self._attr_extra_state_attributes = {
                "last_matched": None
            }

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor attributes from service info."""
        # Update the latest MAC from runtime data
        self._attr_native_value = self._entry.runtime_data.latest_fingerprint_mac
        self._update_attributes()


class BleAdvertDataGattBatterySensor(BleAdvertDataBaseSensor):
    """Representation of the GATT battery level sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "gatt_battery"

    def __init__(self, entry: BleAdvertDataConfigEntry) -> None:
        """Initialize the GATT battery sensor."""
        super().__init__(entry)
        formatted_address = format_mac(self._address)
        self._attr_unique_id = f"{formatted_address}_gatt_battery"
        self._attr_native_value = entry.runtime_data.gatt_battery_level
        self._last_battery_level: int | None = None

    def _restore_last_state(self, last_state) -> None:
        """Restore the last valid battery level."""
        try:
            battery_level = int(float(last_state.state))
            if 0 <= battery_level <= 100:
                self._attr_native_value = battery_level
                self._last_battery_level = battery_level
                self._attr_extra_state_attributes = last_state.attributes
        except (ValueError, TypeError):
            pass

    def _update_from_service_info(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update sensor value from runtime data."""
        current_level = self._entry.runtime_data.gatt_battery_level
        self._attr_native_value = current_level
        # Track changes to detect updates from async GATT fetches
        if current_level is not None and current_level != self._last_battery_level:
            self._last_battery_level = current_level

    async def async_added_to_hass(self) -> None:
        """Register for Bluetooth updates and listen for GATT events."""
        await super().async_added_to_hass()

        @callback
        def _handle_gatt_event(event: Event[Any]) -> None:
            """Handle GATT battery update events on the event loop."""
            data = event.data
            if data.get("address") != self._address:
                return

            level = data.get("battery_level")
            if level is None:
                return

            self._attr_native_value = level
            self._last_battery_level = level
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(f"{DOMAIN}_gatt_battery", _handle_gatt_event)
        )


def _extract_battery_from_manufacturer_data(
    service_info: BluetoothServiceInfoBleak, address: str
) -> dict[str, Any]:
    """Extract battery information from manufacturer data if available.
    
    Returns dict with any battery data found (empty if none).
    User can create custom parsing rules to extract specific battery data.
    """
    battery_attrs: dict[str, Any] = {}
    manufacturer_data = service_info.manufacturer_data or {}
    _logger = logging.getLogger(__name__)
    
    for mfg_id, data in manufacturer_data.items():
        if not isinstance(data, (bytes, bytearray)):
            continue
        
        _logger.debug(
            "Manufacturer data for %s (ID %d): %s",
            address,
            mfg_id,
            data.hex(),
        )
    
    return battery_attrs


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
