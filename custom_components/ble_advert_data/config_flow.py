"""Config flow for BLE advert data."""

from __future__ import annotations

from collections.abc import Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN


class BleAdvertDataConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BLE advert data."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(format_mac(address))
            self._abort_if_unique_id_configured()

            self._async_abort_entries_match({CONF_ADDRESS: address})
            return self.async_create_entry(
                title=self._format_title(address),
                data={CONF_ADDRESS: address},
            )

        devices = self._discovered_devices()
        if not devices:
            errors["base"] = "no_devices"

        schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    def _discovered_devices(self) -> Mapping[str, str]:
        """Return a mapping of discovered BLE device addresses to labels."""
        items: dict[str, str] = {}
        service_infos = bluetooth.async_discovered_service_info(self.hass)
        for info in sorted(
            service_infos,
            key=lambda service_info: (
                service_info.name is None,
                service_info.name or "",
                service_info.address,
            ),
        ):
            address = info.address
            if address in items:
                continue
            name = info.name or address
            items[address] = f"{name} ({address})"

        return items

    def _format_title(self, address: str) -> str:
        """Return a title for a config entry."""
        for info in bluetooth.async_discovered_service_info(self.hass):
            if info.address == address:
                return info.name or address

        return address
