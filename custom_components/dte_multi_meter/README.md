# DTE Multi-Meter Usage for Home Assistant

Custom Home Assistant integration for DTE Green Button XML share links that contain multiple meters in one feed, such as two electric meters plus one gas meter.

This was built for DTE XML feeds where multiple `UsagePoint` entries are present in one response. It creates separate Home Assistant sensors for each meter and an optional combined electric total sensor.

## Entities created

Typical entities:

- `sensor.dte_electric_meter_1`
- `sensor.dte_electric_meter_2`
- `sensor.dte_electric_total`
- `sensor.dte_gas_meter`

Entity IDs can vary depending on Home Assistant naming rules.

## Install with HACS as a custom repository

1. Push this repository to GitHub.
2. In Home Assistant, open **HACS**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add your GitHub repo URL.
5. Select category **Integration**.
6. Install **DTE Multi-Meter Usage**.
7. Restart Home Assistant.
8. Go to **Settings → Devices & services → Add integration**.
9. Search for **DTE Multi-Meter Usage**.
10. Paste your DTE `https://usagedata.dteenergy.com/link/...` URL.

## Manual install

Copy this folder into Home Assistant:

```text
custom_components/dte_multi_meter
```

The final path should be:

```text
/config/custom_components/dte_multi_meter/manifest.json
```

Then restart Home Assistant and add the integration from **Settings → Devices & services**.

## Energy Dashboard

For electric usage, use either:

- `DTE Electric Total`, or
- both individual electric meter sensors.

Do **not** add both the total and the individual electric meter sensors, or electricity usage will be double-counted.

For gas usage, add `DTE Gas Meter` under gas consumption.

## Units

- Electric raw DTE XML values are converted from Wh-style values to `kWh`.
- Gas raw DTE XML values are converted using the DTE `ReadingType/gas` multiplier. For your feed, raw `1400` becomes `1.400 CCF`.

## Notes

DTE data is not real time. It usually lags actual usage and this integration polls every 24 hours.

Do not commit your private DTE share URL or downloaded XML export to GitHub.
