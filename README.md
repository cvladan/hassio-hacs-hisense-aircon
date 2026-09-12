# HiSense Air Conditioners

> [!IMPORTANT]
> This integration does not support ConnectLife app air conditioners. For those devices, you may want to try [oyvindwe/connectlife-ha](https://github.com/oyvindwe/connectlife-ha), though this has not been verified here.

Native Home Assistant custom integration for Hisense/Ayla LAN air conditioners. Requires Home Assistant 2026.3.0 or newer.

This repository is now structured for HACS. It no longer runs as a Docker container, Home Assistant add-on, MQTT bridge, or external Python service. Home Assistant hosts the local Ayla LAN endpoints directly and communicates with the device on your local network.

This integration implements the Ayla Networks LAN API used by many HiSense WiFi air conditioner modules, including AEH-W4B1 and AEH-W4E1 devices, and Fujitsu FGLair devices.

As discussed in the upstream project issue [deiger/AirCon#1](https://github.com/deiger/AirCon/issues/1), the AEH-W4A1 module appears to use a different protocol. That module is used by apps such as [Hi-Smart Life](https://play.google.com/store/apps/details?id=com.qd.android.livehome), [AirConnect](https://play.google.com/store/apps/details?id=com.oem.android.airconnect), [Smart Cool](https://play.google.com/store/apps/details?id=com.oem.android.livehome), [AC WIFI](https://play.google.com/store/apps/details?id=com.oem.android.ecold), and [Tornado WiFi](https://play.google.com/store/apps/details?id=com.oem.android.tornadowifi). If your module is AEH-W4A1, this integration may not work with it.

These modules are installed in air conditioners and humidifiers manufactured or branded by several companies, including Hisense, Beko, Westinghouse, Winia, Tornado, York, and others.

**This project is not affiliated with Hisense, Ayla Networks, Fujitsu, any of their subsidiaries, or any of their resellers.**

## What This Integration Does

- Adds devices through the normal Home Assistant config flow.
- Discovers LAN keys from the supported Hisense/Ayla cloud account, or accepts manual LAN key entry.
- Registers unauthenticated local LAN endpoints under `/local_lan/...` so the air conditioner can exchange encrypted local messages with Home Assistant.
- Exposes the main device as a `climate` entity.
- Exposes additional writable properties as `switch`, `select`, and `number` entities.
- Exposes read-only device properties as `sensor` and `binary_sensor` entities.
- Does not require MQTT.

## Prerequisites

1. A supported air conditioner or humidifier with a HiSense AEH-W4B1/AEH-W4E1 module, or a supported Fujitsu FGLair device.
2. The device must already be configured in its original mobile app and connected to your network.
3. The device must be reachable from Home Assistant on the local network.
4. The air conditioner must be able to reach a plain HTTP callback port on the Home Assistant host. If Home Assistant uses HTTPS, enable the integration's separate HTTP listener as described under Network Notes.
5. Pick the app code for the mobile app you used to configure the device:

   | Code       | App Name            | App link |
   |------------|---------------------|----------|
   | `beko-eu`    | Beko?               | |
   | `haxxair`    | HAXXAIR WIFI REMOTE | [Google Play](https://play.google.com/store/apps/details?id=com.aylanetworks.accontrol.haxxair) |
   | `denali-us`  | Denali Aire         | [Google Play](https://play.google.com/store/apps/details?id=com.smart.internationalus.denaliaire) |
   | `fglair-cn`  | FGLair China        | |
   | `fglair-eu`  | FGLair              | [Google Play](https://play.google.com/store/apps/details?id=com.fujitsu.fglair) |
   | `field-us`   | HiSmart Air         | [Google Play](https://play.google.com/store/apps/details?id=com.aylanetworks.accontrol.hisense) |
   | `hisense-eu` | HiSmart Life        | [Google Play](https://play.google.com/store/apps/details?id=com.hisense.hismartinternationalforandroid) |
   | `hisense-us` | HiSmart Home        | [Google Play](https://play.google.com/store/apps/details?id=com.hisense.hismartinternationalus) |
   | `hismart-eu` | Smart-Living        | [Google Play](https://play.google.com/store/apps/details?id=com.smart.international2) |
   | `hismart-us` | AI-Home             | [Google Play](https://play.google.com/store/apps/details?id=com.smart.internationalus) |
   | `huihe-us`   | SunHome             | [Google Play](https://play.google.com/store/apps/details?id=com.sunvalley.sunhome) |
   | `mid-eu`     | WiFi AC             | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.mid.europe.hisense) |
   | `mid-us`     | Smiling Air         | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.mid.america.hisense) |
   | `oem-eu`     | Hi-Smart AC         | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.europe.hisense) |
   | `oem-us`     | Hisense?            | |
   | `tornado-us` | Tornado WiFi        | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.tornado.america.hisense) |
   | `winia-us`   | Winia Air Conditioner HomeSmart | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.winia.america.hisense) |
   | `wwh-us`     | Westinghouse?       | |
   | `york-us`    | YORK Smart          | [Google Play](https://play.google.com/store/apps/details?id=com.accontrol.york.america.hisense) |

After the integration has fetched the LAN key, the device can usually be blocked from the internet as long as it can still reach Home Assistant locally. If you plan to give the device a static IP address, do that while the original app can still see the device, then use the same IP in Home Assistant.

## Install Using HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cvladan&repository=hassio-hacs-hisense-aircon&category=integration)

Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.

To add it manually:

1. Open **HACS**.
2. Go to **Integrations**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add `https://github.com/cvladan/hassio-hacs-hisense-aircon`.
5. Select category **Integration**.
6. Click **Download** for **Hisense Air Conditioner**.

After installing, restart Home Assistant. Then open **Settings -> Devices & services -> Add integration** and search for **Hisense Air Conditioner**.

## Supported Setup Methods

### Cloud Discovery

Use this if the device is still visible in the original mobile app.

1. Install the integration through HACS as a custom repository.
2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration**.
4. Search for **Hisense Air Conditioner**.
5. Choose **Discover from Hisense app**.
6. Enter:
   - app code, for example `hisense-eu`, `hisense-us`, `fglair-eu`
   - app username
   - app password
7. Select one or more discovered air conditioners to add. All discovered devices are selected by default.

Advanced settings are optional and can usually stay collapsed:

- device name filter, if you want discovery to look for only one exact app device name
- Home Assistant HTTP port, usually `8123`
- separate HTTP listener port, `0` to keep using the HA server or a free port such as `8124` when HA uses HTTPS
- optional Home Assistant local IP if HA has multiple network interfaces or VLANs
- device temperature unit override, if the automatic app-code detection reports the wrong unit

### Manual LAN Key Setup

Use this if you already know the device LAN key and key ID.

Enter:

- device name
- app code
- device IP address
- MAC address
- `lanip_key`
- `lanip_key_id`
- model
- temperature unit
- Home Assistant HTTP port
- optional separate HTTP listener port for HA installations using HTTPS
- optional Home Assistant local IP

## Managing Devices After Setup

Open the integration entry menu in **Settings > Devices & services** and choose **Reconfigure**. You can discover more devices from an app account, add a device with a LAN key, choose which devices to keep, or change the IP address of one device. Cloud discovery asks for credentials each time and does not save the password. Removing the last device requires deleting the configuration entry.

You can also add another integration entry for a different account or a manual device. Each device must have a unique MAC address and IP address across all entries. Runtime options such as the callback address apply to the entry and are edited through **Configure**.

## Updating Automations That Use Separate Climate Controls

The climate entity now provides the main controls. The matching standalone entities are removed on the next integration setup, including existing registry entries. The climate entity ID stays the same. Update dashboards, scripts, scenes, and automations that used these controls:

| Previous control | Replacement action on the climate entity |
|------------------|------------------------------------------|
| Power switch | `climate.turn_on` or `climate.turn_off` |
| Work mode select | `climate.set_hvac_mode`, with `hvac_mode` such as `cool` or `heat` |
| Target temperature number | `climate.set_temperature`, with `temperature` |
| Fan speed select | `climate.set_fan_mode`, using the entity's `fan_modes` values |
| Vertical swing switch | `climate.set_swing_mode`, with `swing_mode: on` or `off` |
| Horizontal swing switch | `climate.set_swing_horizontal_mode`, with `swing_horizontal_mode: on` or `off` |

Vertical and horizontal swing now have separate climate controls. Each action changes only its own direction. Fujitsu devices expose only their supported climate controls. Climate state attributes replace reads of the removed standalone controls.

When upgrading from 1.2, replace combined Hisense swing actions with these two actions. Use `swing_mode` for the vertical action and `swing_horizontal_mode` for the horizontal action:

| Previous `swing_mode` | New vertical value | New horizontal value |
| --- | --- | --- |
| `off` | `off` | `off` |
| `vertical` | `on` | `off` |
| `horizontal` | `off` | `on` |
| `both` | `on` | `on` |

The new `climate.set_swing_mode` with `off` stops vertical swing only. To stop both directions, send both actions with `off`. Entity IDs stay the same. `climate.turn_on` sends the device power command without selecting Auto. Use `climate.set_hvac_mode` when an automation needs a specific mode.

Sleep, Quiet, Eco, Super, backlight, swing angle, and the device display temperature unit remain separate controls. Humidifier controls also remain. Fujitsu controls that the climate entity does not provide, such as horizontal louver control, are kept.

## Network Notes

The air conditioner uses plain HTTP for callbacks, even when Home Assistant itself uses HTTPS. By default, the integration uses the Home Assistant web server and the configured **Home Assistant HTTP port**. It serves these device endpoints:

- `/local_lan/key_exchange.json`
- `/local_lan/commands.json`
- `/local_lan/property/datapoint.json`
- `/local_lan/property/datapoint/ack.json`
- `/local_lan/node/property/datapoint.json`
- `/local_lan/node/property/datapoint/ack.json`

When using the Home Assistant web server, you can open an endpoint in a browser for a small JSON connectivity explanation. The `/local_lan/commands.json` endpoint is special: the air conditioner uses `GET` there, so browser checks from other IP addresses get the explanation while requests from the configured air conditioner IP get the real command response.

Home Assistant selects a callback address for the route to each device. Leave **Home Assistant local IP address** empty for this automatic selection, or enter an IPv4 address to override it for every device in that configuration.

### Home Assistant with HTTPS

Starting with version 1.4.0, you can enable a separate HTTP listener for device callbacks while keeping HTTPS on Home Assistant:

1. Update the integration through HACS and restart Home Assistant.
2. Open **Settings > Devices & services > Hisense Air Conditioner > Configure**. During initial cloud setup, open **Advanced Settings** instead.
3. Set **Separate HTTP listener port (0 to disable)** to a free port, for example `8124`, and save.
4. Allow the air conditioner to reach that TCP port on the Home Assistant host. With container bridge networking, publish the same port on the host, for example `8124:8124`. With host networking, no extra container port mapping is needed.

This port overrides **Home Assistant HTTP port** for that configuration. The listener binds to all IPv4 interfaces and serves only the six device endpoints above, using the same source IP checks, LAN key exchange, message signatures, and request size limits. It does not expose the HA interface or API. Keep it on the local network. Browser requests from an unconfigured device address are rejected rather than showing the HA endpoint explanation.

All devices in one configuration share its listener. Each configuration using a separate listener needs a different free port, for example `8124` and `8125`. Configurations using the HA web server can continue alongside them. Reloading or removing one configuration closes only its listener. A busy port produces a setup error without stopping the configuration already using it.

The integration detects direct callbacks to HA's HTTPS port and explains how to enable the listener. Explicit callback address or port overrides are still allowed for existing plain HTTP proxies; those overrides must actually provide an HTTP route to HA. If HTTPS is handled by a reverse proxy and HA already serves HTTP on the local network, the separate listener is optional.

No changes are required for working HTTP installations. The default `0` keeps the existing callback settings. To switch back, set the separate port to `0` and make sure **Home Assistant HTTP port** is reachable over plain HTTP. Saving options also retries an entry whose setup previously failed.

## Supported App Codes

Common codes include:

- `hisense-eu`
- `hisense-us`
- `hismart-eu`
- `hismart-us`
- `fglair-eu`
- `fglair-us`
- `field-us`
- `oem-eu`
- `oem-us`
- `mid-eu`
- `mid-us`
- `tornado-us`
- `york-us`
- `beko-eu`
- `denali-us`
- `fglair-cn`
- `haxxair`
- `huihe-us`
- `winia-us`
- `wwh-us`

The full list is available in `custom_components/hisense_aircon/app_mappings.py`.

## Available Properties

The table below lists the main standard A/C properties available through the local protocol. FGLair devices and humidifiers expose different property sets, but Home Assistant will still create entities from whatever writable/read-only properties are known for that device class.

Home Assistant entity names are cleaned up from the raw protocol names. For example, `t_fan_leftright` is shown as **Horizontal Swing**, `t_fan_mute` as **Quiet**, and `f_e_intemp` as **Indoor Temperature Sensor Fault**. The original protocol property is still available on each entity as the `hisense_property` attribute, and the More info panel includes a short `description` attribute explaining what that entity controls or reports.

Protocol prefixes mean:

- `t_`: writable target/control property sent to the air conditioner
- `f_`: read-only feedback/status property reported by the air conditioner
- `f_e_`: read-only fault/error flag reported by the air conditioner

| Property         | Read Only | Values                                 | Comment                                                                  |
|------------------|-----------|----------------------------------------|--------------------------------------------------------------------------|
| `f_electricity`    | x         | Integer                                |                                                                          |
| `f_e_arkgrille`    | x         | 0, 1                                   | Alarm from cabinet grille protection                                     |
| `f_e_incoiltemp`   | x         | 0, 1                                   | Indoor coil temperature sensor in fault                                  |
| `f_e_incom`        | x         | 0, 1                                   | Indoor and outdoor communication fault                                   |
| `f_e_indisplay`    | x         | 0, 1                                   | Communication fault between indoor control panel and display panel       |
| `f_e_ineeprom`     | x         | 0, 1                                   | Error in EEPROM of indoor control panel                                  |
| `f_e_inele`        | x         | 0, 1                                   | Communication fault between indoor control panel and indoor power panel  |
| `f_e_infanmotor`   | x         | 0, 1                                   | Indoor fan motor abnormal                                                |
| `f_e_inhumidity`   | x         | 0, 1                                   | Indoor humidity sensor fault                                             |
| `f_e_inkeys`       | x         | 0, 1                                   | Communication fault between indoor control panel and keyboard plate      |
| `f_e_inlow`        | x         | 0, 1                                   |                                                                          |
| `f_e_intemp`       | x         | 0, 1                                   | Indoor temperature sensor fault                                          |
| `f_e_invzero`      | x         | 0, 1                                   | Indoor voltage zero-crossing detection fault                             |
| `f_e_outcoiltemp`  | x         | 0, 1                                   | Outdoor coil temperature sensor fault                                    |
| `f_e_outeeprom`    | x         | 0, 1                                   | Outdoor EEPROM error                                                     |
| `f_e_outgastemp`   | x         | 0, 1                                   | Exhaust temperature sensor fault                                         |
| `f_e_outmachine2`  | x         | 0, 1                                   |                                                                          |
| `f_e_outmachine`   | x         | 0, 1                                   |                                                                          |
| `f_e_outtemp`      | x         | 0, 1                                   | Outdoor ambient temperature sensor fault                                 |
| `f_e_outtemplow`   | x         | 0, 1                                   |                                                                          |
| `f_e_push`         | x         | 0, 1                                   | Communication fault between WiFi control panel and indoor control panel  |
| `f_filterclean`    | x         | 0, 1                                   | Filter requires cleaning                                                 |
| `f_humidity`       | x         | Integer                                | Relative humidity percent                                                |
| `f_power_display`  | x         | 0, 1                                   |                                                                          |
| `f_temp_in`        | x         | Decimal                                | Environment temperature                                                  |
| `f_voltage`        | x         | Integer                                |                                                                          |
| `t_backlight`      |           | ON, OFF                                | Turn indoor unit display/backlight on or off                             |
| `t_device_info`    |           | 0, 1                                   |                                                                          |
| `t_display_power`  |           | 0, 1                                   |                                                                          |
| `t_eco`            |           | OFF, ON                                | Economy mode                                                             |
| `t_fan_leftright`  |           | OFF, ON                                | Horizontal air flow                                                      |
| `t_fan_mute`       |           | OFF, ON                                | Quiet mode                                                               |
| `t_fan_power`      |           | OFF, ON                                | Vertical air flow                                                        |
| `t_fan_speed`      |           | AUTO, LOWER, LOW, MEDIUM, HIGH, HIGHER | Fan speed                                                                |
| `t_swing_angle`    |           | SWEEP, AUTO, ANGLE1-ANGLE6             | Vertical swing angle                                                     |
| `t_ftkt_start`     |           | Integer                                |                                                                          |
| `t_power`          |           | OFF, ON                                | Power                                                                    |
| `t_run_mode`       |           | OFF, ON                                | Double frequency                                                         |
| `t_setmulti_value` |           | Integer                                |                                                                          |
| `t_sleep`          |           | STOP, ONE, TWO, THREE, FOUR            | Sleep mode                                                               |
| `t_temp`           |           | Integer                                | Target temperature                                                       |
| `t_temptype`       |           | CELSIUS, FAHRENHEIT                    | Displayed temperature unit                                               |
| `t_temp_eight`     |           | OFF, ON                                | 8°C heat / frost protection mode                                         |
| `t_temp_heatcold`  |           | OFF, ON                                | Fast cool/heat, also known as Super or Turbo                             |
| `t_work_mode`      |           | FAN, HEAT, COOL, DRY, AUTO             | Work mode                                                                |

## Credits

Maintained by [@cvladan](https://github.com/cvladan). Thanks to [@wifi75](https://github.com/wifi75) for the logo!

The LAN protocol implementation is based on the original Ayla/Hisense AirCon project logic and has been repackaged as a native Home Assistant custom integration.

This project is not affiliated with Hisense, Ayla Networks, Fujitsu, or their subsidiaries.

## Technical Notes

This integration uses Home Assistant's shared `aiohttp` client session and HTTP view stack. `aiohttp` is managed by Home Assistant itself and is not pinned in this integration's `manifest.json` requirements.

## Diagnostics and Development

Download diagnostics from the integration entry menu. The export includes reported protocol values, device models, availability, and queue lengths. It excludes account credentials, LAN keys, device names, MAC addresses, IP addresses, and cloud device identifiers. Enable `custom_components.hisense_aircon: debug` for integration logs.

A reported electricity value is still a raw protocol value. No power or energy unit is assigned without a verified scale for the device model. Signature failures still require investigation of the device session and network. The parser and logging changes do not establish a fix for every cause of those failures.

Run the checks with Python 3.14:

```sh
python -m pip install homeassistant==2026.9.1 dataclasses-json==0.6.7 getmac==0.9.5 pycryptodome==3.23.0
python -m unittest discover -s tests -v
```

CI runs these checks on Home Assistant 2026.3.0 and 2026.9.1, plus HACS validation and hassfest. To check the minimum version locally, use a separate environment with `homeassistant==2026.3.0`.

The checks use Home Assistant classes and local HTTP and HTTPS test servers. They cover encrypted callbacks, multiple devices, mixed shared and separate listeners, source isolation, busy ports, and cleanup after failure or reload. The test with several loopback source addresses runs on Linux CI and is skipped on systems without those addresses. They do not contact the cloud or a physical air conditioner. Real device checks are still needed for Quiet behavior, recovery after connection loss, and cloud discovery across supported apps.
