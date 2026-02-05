# ha-ble-advert-data

Create sensors from the raw BLE advertisement data that Home Assistant sees.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the integration from HACS.
3. Restart Home Assistant.

## Configuration

1. Open Settings -> Devices & Services.
2. Select Add integration and choose BLE advert data.
3. Pick a Bluetooth device from the list.
4. You can type to filter the list or paste a MAC address directly.

## Sensors

The sensor exposes the advertisement data as attributes, including:

- `manufacturer_data`
- `service_data`
- `service_uuids`
- `raw`