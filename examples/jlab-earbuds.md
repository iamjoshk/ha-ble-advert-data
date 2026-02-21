## Using advertisement data from Jlab Earbuds

> Jlab Go Pop+ earbuds are used in this example

1. Identify the bluetooth MAC address
2. Check the bluetooth advertisement monitor
    - in HA 2026.1 and newer, go to settings then Bluetooth, then scroll down to Advertisement Monitor and click Advertiement monitor link.
3. When you find your device, click on it to open the Device information modal window
4. click Copy to clipboard
5. Paste the result in file where you can look at it.

Result should be similar to this.
```
{"name":"DF:F4:21:70:6E:70","address":"DF:F4:21:70:6E:70","rssi":-53,"manufacturer_data":{"1494":"0200060022dff421edf7fd01000a006f0102000000000000000057"},"service_data":{},"service_uuids":[],"source":"44:A3:BB:49:3E:68","connectable":true,"time":1771608781.9553425,"tx_power":null,"raw":"1effd6050200060022dff421edf7fd01000a006f0102000000000000000057"}
```
> Note: not all of this data will be populate, some devices to not advertise useful data

If you have already added the device to the integration, you can also enable the debug log for the integration and check the raw logs for the device's advertisement data. This will be easier to get repeated data sets as you try to figure out what data represents.

```
2026-02-20 11:49:03.142 DEBUG (MainThread) [custom_components.ble_advert_data.sensor] Manufacturer data for 9F:DA:08:0F:F8:A0 (ID 1494): 02000600229fda08240c3e01646400e001020000000000000000a0
```

In this case, the first 10 bytes were an identifier and do not change:
`02000600229fda08240c3e`

Then it got interesting in bytes 11, 12, and 13
`016464`
By testing different scenarios with earbuds like having them in the case, out of the case, connected and disconnected to a device, you can determine what these bytes represent.

Byte 11: earbud connection status. Regardless of left or right, `01` is disconnected, `02` is connected, `03` is attempting to connect. Sometimes `00` would be sent, but this seemed to be an in-between state.

Byte 12: left earbud battery level in hex. Only reported when earbud is not in the case. `64` is 100%

Byte 13: right earbud battery level in hex. Only reported when earbud is not in the case. `64` is 100%. 

The rest of the advertisement data seems to be some kind of counter and is inconsequential to the information we are trying to gather.

Creating a parsing rule like this:


`name`: "Earbud Connection Status"
`source_type`: Manufacturer data
`source_key`: 1494
`offset`: 11
`length`: 3
`endian`: little
`signed`: false
`scale`: 1
`unit`: ""

Click submit and a new entity will be created in the device. Monitor this to make sure the entity is reporting the data the way you intend.

Remember, advertisement data is not always sent, so updates to entities may be intermitten or inconsistent.

For example, these Jlab earbuds will not always send an advertisement when the earbuds have been returned to the case, so their status may not always be representative of their current state.