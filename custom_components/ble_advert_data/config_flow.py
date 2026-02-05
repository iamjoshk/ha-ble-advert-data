"""Config flow for BLE advert data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import entity_registry, selector
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
            options.extend(["edit_rule", "remove_rule"])

        return self.async_show_menu(step_id="init", menu_options=options)

    def _build_rule_schema(self, rule: dict[str, Any] | None = None) -> vol.Schema:
        """Build the schema for a rule form."""
        source_options = {
            SOURCE_MANUFACTURER: "Manufacturer data",
            SOURCE_SERVICE: "Service data",
            SOURCE_RAW: "Raw data",
        }
        endian_options = {
            ENDIAN_BIG: "Big endian",
            ENDIAN_LITTLE: "Little endian",
        }

        return vol.Schema(
            {
                vol.Required(
                    CONF_RULE_NAME, default=rule.get(CONF_RULE_NAME) if rule else None
                ): str,
                vol.Required(
                    CONF_SOURCE_TYPE,
                    default=rule.get(CONF_SOURCE_TYPE, SOURCE_MANUFACTURER),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=value)
                            for key, value in source_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SOURCE_KEY, default=rule.get(CONF_SOURCE_KEY) or ""
                ): str,
                vol.Required(
                    CONF_OFFSET, default=rule.get(CONF_OFFSET, 0)
                ): vol.All(int, vol.Range(min=0)),
                vol.Required(
                    CONF_LENGTH, default=rule.get(CONF_LENGTH, 1)
                ): vol.All(int, vol.Range(min=1)),
                vol.Required(
                    CONF_ENDIAN, default=rule.get(CONF_ENDIAN, ENDIAN_LITTLE)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=value)
                            for key, value in endian_options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SIGNED, default=rule.get(CONF_SIGNED, False)
                ): bool,
                vol.Required(
                    CONF_SCALE, default=rule.get(CONF_SCALE, 1.0)
                ): vol.Coerce(float),
                vol.Optional(CONF_UNIT, default=rule.get(CONF_UNIT) or ""): str,
            }
        )

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

        return self.async_show_form(
            step_id="add_rule", data_schema=self._build_rule_schema()
        )

    async def async_step_edit_rule(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Edit a parsing rule."""
        if not self._rules:
            return await self.async_step_init()

        # Check if we're selecting which rule to edit or editing the selected rule
        if CONF_RULE_ID not in self.context:
            # First step: select which rule to edit
            if user_input is not None:
                # Store the selected rule id and show the edit form
                self.context[CONF_RULE_ID] = user_input[CONF_RULE_ID]
                # Re-call this step to go to the edit form
                return await self.async_step_edit_rule()

            options = {
                rule[CONF_RULE_ID]: rule.get(CONF_RULE_NAME, rule[CONF_RULE_ID])
                for rule in self._rules
                if rule.get(CONF_RULE_ID)
            }
            schema = vol.Schema({vol.Required(CONF_RULE_ID): vol.In(options)})
            return self.async_show_form(step_id="edit_rule", data_schema=schema)

        # Second step: edit the selected rule
        rule_id = self.context[CONF_RULE_ID]
        rule = next(
            (r for r in self._rules if r.get(CONF_RULE_ID) == rule_id), None
        )
        if rule is None:
            return await self.async_step_init()

        if user_input is not None:
            updated_rule = {
                CONF_RULE_ID: rule_id,
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
            rules = [
                updated_rule if r.get(CONF_RULE_ID) == rule_id else r
                for r in self._rules
            ]
            return self.async_create_entry(title="", data={CONF_RULES: rules})

        return self.async_show_form(
            step_id="edit_rule", data_schema=self._build_rule_schema(rule)
        )

    async def async_step_remove_rule(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.FlowResult:
        """Remove a parsing rule."""
        if not self._rules:
            return await self.async_step_init()

        if user_input is not None:
            rule_id = user_input[CONF_RULE_ID]
            rules = [rule for rule in self._rules if rule.get(CONF_RULE_ID) != rule_id]
            
            # Clean up the associated entity
            await self._cleanup_rule_entity(rule_id)
            
            return self.async_create_entry(title="", data={CONF_RULES: rules})

        options = {
            rule[CONF_RULE_ID]: rule.get(CONF_RULE_NAME, rule[CONF_RULE_ID])
            for rule in self._rules
            if rule.get(CONF_RULE_ID)
        }
        schema = vol.Schema({vol.Required(CONF_RULE_ID): vol.In(options)})
        return self.async_show_form(step_id="remove_rule", data_schema=schema)

    async def _cleanup_rule_entity(self, rule_id: str) -> None:
        """Clean up the entity created by a rule."""
        registry = entity_registry.async_get(self.hass)
        address = self._entry.data[CONF_ADDRESS]
        formatted_address = format_mac(address)
        
        # Look up entity by unique_id
        entries = [
            entry
            for entry in registry.entities.values()
            if entry.unique_id == f"{formatted_address}_rule_{rule_id}"
        ]
        for entry in entries:
            registry.async_remove(entry.entity_id)

    @property
    def _rules(self) -> list[dict[str, Any]]:
        """Return rule list from options."""
        rules = self._entry.options.get(CONF_RULES, [])
        return [rule for rule in rules if isinstance(rule, dict)]
