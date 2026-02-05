"""Config flow for BLE advert data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_ENDIAN,
    CONF_LENGTH,
    CONF_OFFSET,
    CONF_RULES,
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
)


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

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=value)
                            for key, value in devices.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            }
        )
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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "BleAdvertDataOptionsFlow":
        """Return the options flow."""
        return BleAdvertDataOptionsFlow(config_entry)


class BleAdvertDataOptionsFlow(config_entries.OptionsFlow):
    """Handle options for BLE advert data."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Handle the options flow start."""
        options = ["add_rule"]
        if self._rules:
            options.append("remove_rule")

        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_add_rule(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Add a parsing rule."""
        if user_input is not None:
            rule = {
                CONF_RULE_ID: uuid4().hex,
                CONF_RULE_NAME: user_input[CONF_RULE_NAME],
                CONF_SOURCE_TYPE: user_input[CONF_SOURCE_TYPE],
                CONF_SOURCE_KEY: user_input[CONF_SOURCE_KEY] or None,
                CONF_OFFSET: user_input[CONF_OFFSET],
                CONF_LENGTH: user_input[CONF_LENGTH],
                CONF_ENDIAN: user_input[CONF_ENDIAN],
                CONF_SIGNED: user_input[CONF_SIGNED],
                CONF_SCALE: user_input[CONF_SCALE],
                CONF_UNIT: user_input[CONF_UNIT] or None,
            }
            rules = [*self._rules, rule]
            return self.async_create_entry(title="", data={CONF_RULES: rules})

        source_options = {
            SOURCE_MANUFACTURER: "Manufacturer data",
            SOURCE_SERVICE: "Service data",
            SOURCE_RAW: "Raw data",
        }
        endian_options = {
            ENDIAN_BIG: "Big endian",
            ENDIAN_LITTLE: "Little endian",
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_RULE_NAME): str,
                vol.Required(CONF_SOURCE_TYPE, default=SOURCE_MANUFACTURER): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=value)
                            for key, value in source_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SOURCE_KEY, default=""): str,
                vol.Required(CONF_OFFSET, default=0): vol.All(int, vol.Range(min=0)),
                vol.Required(CONF_LENGTH, default=1): vol.All(int, vol.Range(min=1)),
                vol.Required(CONF_ENDIAN, default=ENDIAN_LITTLE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=value)
                            for key, value in endian_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_SIGNED, default=False): bool,
                vol.Required(CONF_SCALE, default=1.0): vol.Coerce(float),
                vol.Optional(CONF_UNIT, default=""): str,
            }
        )

        return self.async_show_form(step_id="add_rule", data_schema=schema)

    async def async_step_remove_rule(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Remove a parsing rule."""
        if not self._rules:
            return await self.async_step_init()

        if user_input is not None:
            rule_id = user_input[CONF_RULE_ID]
            rules = [rule for rule in self._rules if rule.get(CONF_RULE_ID) != rule_id]
            return self.async_create_entry(title="", data={CONF_RULES: rules})

        options = {
            rule[CONF_RULE_ID]: rule.get(CONF_RULE_NAME, rule[CONF_RULE_ID])
            for rule in self._rules
            if rule.get(CONF_RULE_ID)
        }
        schema = vol.Schema({vol.Required(CONF_RULE_ID): vol.In(options)})
        return self.async_show_form(step_id="remove_rule", data_schema=schema)

    @property
    def _rules(self) -> list[dict[str, Any]]:
        """Return rule list from options."""
        rules = self._entry.options.get(CONF_RULES, [])
        return [rule for rule in rules if isinstance(rule, dict)]
