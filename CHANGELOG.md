# Changelog

## 1.4.0

- Add an optional separate HTTP listener for air conditioner callbacks, restoring support for Home Assistant installations that serve HTTPS directly. Fixes the limitation present since the original HACS conversion, reported in #13.
- Explain direct HTTPS callback incompatibility during setup and in integration options. Report listener port conflicts and binding failures.
- Keep each listener scoped to its own configuration and reuse the existing device IP checks, key exchange, signed messages, and request limits. Multiple devices can share one configuration; separate configurations use distinct listener ports.
- Close listener sockets after unload, cancellation, or failed setup. Saving options retries failed entries without adding a second reload for working entries.
- Add regression checks for HTTP and HTTPS coexistence, encrypted Fujitsu callbacks, multiple devices and mixed configurations, source isolation, and port lifecycle.

Migration: Working HTTP installations require no changes. For HA with HTTPS, update and restart Home Assistant, open the integration's Configure options, and set **Separate HTTP listener port (0 to disable)** to a free port such as `8124`. Make that port reachable from the air conditioner. Use a different port for each configuration. The default `0` preserves existing callback settings. No device rediscovery or new LAN keys are required.

## 1.3.0

- Require Home Assistant 2026.3.0 or newer, with regression checks on 2026.3.0 and 2026.9.1, HACS validation, and hassfest.
- Use the Home Assistant HTTP client's certificate verification, limit cloud requests to 15 seconds, and distinguish sign in failures, connection failures, and empty accounts.
- Select the callback IP for each device through Home Assistant networking. Validate manual overrides without breaking form rendering.
- Clean up background tasks after failed or cancelled setup and store controllers in configuration runtime data.
- Request fresh device state after registration and reconnect without duplicating pending reads.
- Replace combined swing modes with independent vertical and horizontal climate actions. This changes existing swing automations; see the README migration table.
- Turn devices on without selecting Auto mode.
- Avoid redundant state notifications while preserving first reports and unknown state transitions.
- Remove the obsolete issue follow-up document.

Thanks to Kamal Nasser (@kamaln7) and Juan Manuel Béc (@JuanmanDev) for the upstream swing and reconnect improvements. Their source commits are credited in the corresponding implementation commits.

## 1.2.0

- Add multiple configuration entries and device management through Reconfigure. Cloud passwords are not saved.
- Route device callbacks to the correct configuration and allow changing one device IP address.
- Handle unknown control fields without losing Quiet, temperature, or mode updates.
- Preserve pending changes when commands are queued together or older device reports arrive.
- Send properties outside the packed control register as standalone commands.
- Retry transient registration failures before marking devices unavailable.
- Keep unreported sensor values unknown and distinguish device reports from locally sent commands.
- Validate LAN message envelopes and body limits, redact diagnostics, and restore cloud certificate verification.
- Remove standalone controls covered by climate. See the README migration table before updating automations.
- Add Italian translations, readable Sleep profile labels, and the community logo.
- Accept the converted 16 C lower bound for Fahrenheit devices while preserving device precision.
- Add regression checks against Home Assistant 2026.9.1.

Thanks to Piotr Szulc (@szupi-ipuzs), Tiziano (@wifi75), Chaim (@Gchaimke), and @castiel10k for the original contributions and problem reports. Individual commits identify the source changes.

## 1.1.7

- Run the LAN notifier and status polling loops as background tasks so they do not delay Home Assistant startup.

## 1.1.6

- Scheduled entity state writes on the Home Assistant event loop so LAN availability and property updates are applied safely from update callbacks.

## 1.1.5

- Replaced raw protocol-style property names with friendly Home Assistant entity names.
- Added `hisense_property` and `description` attributes to property entities for protocol context.
- Documented the `t_`, `f_`, and `f_e_` protocol prefixes in the README.

## 1.1.4

- Added an explicit cloud discovery step for selecting one or more discovered air conditioners.
- Selected all discovered devices by default so multi-device accounts can be added in one setup flow.
- Updated setup documentation to describe the multi-device selection step.

## 1.1.3

- Added configurable device temperature units for cloud setup and integration options.
- Used Home Assistant's configured temperature unit as the fallback when cloud discovery cannot determine the device unit.
- Defaulted manual setup temperature units from Home Assistant instead of hardcoding Celsius.

## 1.1.2

- Fixed the collapsed Advanced Settings section so default values do not block cloud setup validation.
- Fixed Home Assistant section translations so the Advanced Settings heading and help text are visible.
- Added direct setup links to the Supported App Codes README section and corrected manifest repository links.

## 1.1.1

- Improved README documentation with upstream device notes, app-code prerequisites, and available properties.
- Simplified cloud setup so only app code, username, and password are shown by default.
- Moved optional cloud setup fields into a collapsed Advanced Settings section with clearer explanations.

## 1.1.0

- Ported recent community fork fixes for sleep mode, control-value work mode updates, and swing command handling.
- Added FGLair temperature scaling, half-degree target steps, display/outdoor temperature parsing, fan-only mode, diffuse fan mode, powerful mode, outdoor low noise, and refresh/get-prop controls.
- Added vertical swing angle support as a native Home Assistant select entity.
- Improved local registration keepalive handling with request timeouts and offline availability updates.
- Hardened property parsing and encrypted update logging for malformed payloads.

## 1.0.1

- Added browser-friendly `GET` explanations on real Hisense/Ayla LAN endpoints.
- Added root compatibility aliases for `/key_exchange.json` and `/commands.json`.
- Kept `/local_lan/commands.json` as a real `GET` protocol endpoint for requests that come from the configured air conditioner IP.

## 1.0.0

- Converted the project from a Docker/Home Assistant add-on MQTT bridge into a native HACS custom integration.
- Added Home Assistant config flow with cloud discovery and manual LAN key setup.
- Added options flow for callback IP, Home Assistant HTTP port, and status refresh interval.
- Added native Home Assistant entities:
  - `climate`
  - `switch`
  - `select`
  - `number`
  - `sensor`
  - `binary_sensor`
- Moved the Ayla/Hisense LAN protocol implementation under `custom_components/hisense_aircon`.
- Removed Docker, MQTT, add-on, CLI, and SmartThings packaging files.
