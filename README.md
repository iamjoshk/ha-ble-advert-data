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

## Parsing Data

Create sensors from manufacturer data by adding parsing rules in the device's options. Once a device has been added, click the gear for that device and select Add a parsing rule.

`Sensor name`: provide a name for your sensor
`Source type`: select Manufacturer, Source, or Raw data
`Source key`: enter the source key
`Byte offset`: tell the parser where to start looking for the data
`Byte length`: tell the parser how many bytes it should include when parsing
`Byte order`: select Big endian or Little endian. Does not matter when byte length = 1.
`Signed`: check if signed
`Scale`: set the scale for the data (default 1)
`Unit of measurement`: set the unit of measurement (example, `%` for battery percentage)

## Service UUID Fingerprinting

For devices that use randomized MAC addresses, service UUID fingerprinting has been under options. To enable: Once a device has been added, click the gear for that device and select Service Data Fingerprinting.

1. Check Enable fingerprinting matching
2. Add Service UUID
3. Add hex fingerprint (first 4 to 8 bytes of service data)
4. Click Submit

A new sensor will be added (disabled by default) in the device called `Latest MAC address`. This will display the most recent MAC address that has matched the fingerprint.

## GATT fetching

For devices that support GATT fetching and use the standard battery service (UUID 180F), enabling this may automatically capture battery data for the device.

A new battery sensor will be added (disabled by default) to the device. This will display the last known battery level.
