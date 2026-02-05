"""Constants for the BLE advert data integration."""

from __future__ import annotations

import logging

DOMAIN = "ble_advert_data"

CONF_ENDIAN = "endian"
CONF_LENGTH = "length"
CONF_RULES = "rules"
CONF_RULE_ID = "id"
CONF_RULE_NAME = "name"
CONF_SCALE = "scale"
CONF_SIGNED = "signed"
CONF_SOURCE_KEY = "source_key"
CONF_SOURCE_TYPE = "source_type"
CONF_UNIT = "unit"
CONF_OFFSET = "offset"

SOURCE_MANUFACTURER = "manufacturer_data"
SOURCE_SERVICE = "service_data"
SOURCE_RAW = "raw"

ENDIAN_BIG = "big"
ENDIAN_LITTLE = "little"

LOGGER = logging.getLogger(__name__)
