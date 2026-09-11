# Community changes and issue follow-ups

These changes are committed locally on `codex/community-improvements`. They have not been pushed or released. The issue comments below are drafts for publication after the relevant changes are available. Keep issues open where device confirmation is still needed.

## Implementation map

| Issue | Local change | Commit | What remains |
| --- | --- | --- | --- |
| [#3 Logo](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/3) | Copy wifi75's two existing icons and thank the contributor. | `0c2c946` | Check display after installation. |
| [#4 Multiple units](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/4) | Add configurations and manage devices through Reconfigure. | `6397530` | Confirm discovery and commands with several physical units. |
| [#6 Unknown version property](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/6) | Ignore unsupported properties without a warning or loss of subsequent updates. | `769a44a` | Confirm the reported error stops on the affected devices. |
| [#7 Invalid signature](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/7) | Validate envelopes and key exchange; avoid logging decrypted payloads. | `7009343` | Root cause unresolved. Collect session timing and device details; do not bypass signature checks. |
| [#8 Quiet](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/8) | Decode fields independently and preserve queued control changes. | `769a44a`, `8f22928` | Test both the remote and HA switch on the affected model. |
| [#9 Sleep](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/9) | Keep the existing Sleep select and label its choices Off and Profile 1–4. | `cd72020` | Confirm which profiles the device supports; do not invent descriptions for their behavior. |
| [#10 Flapping](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/10) | Retry registration and require three consecutive failures before marking offline. | `a91e587` | Test connection loss and recovery on the user's network. |
| [#11 Commands with Quiet enabled](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/11) | Handle the two reported packed values without dropping other fields; route standalone commands correctly. | `769a44a`, `8f22928` | Verify commands on a real unit with Quiet enabled. |
| [#12 Multiple accounts and electricity](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/12) | Allow separate configurations; hide initial protocol defaults until state arrives. | `6397530`, `2bbd4e5`, `cedf6c2` | Multiple-account flow is tested with mocked discovery. Electricity units and scaling remain unknown. Real reports of 100 or 0 are still displayed. |

PR [#5](https://github.com/cvladan/hassio-hacs-hisense-aircon/pull/5) is not merged. Its useful functionality was implemented independently in `6397530`, with credit to @szupi-ipuzs. This avoids its migration and reconfiguration problems while preserving existing configuration and entity identifiers.

Other commits cover changing one device IP (`fbbe5b2`, inspired by @Gchaimke), removing duplicate climate controls (`3a79e83`, inspired by @wifi75), and the converted 16 C temperature boundary (`54c2362`, inspired by @castiel10k). The README contains replacements for automations that use the removed controls.

## Draft issue replies

Publish these only once the changes are available, and include the relevant branch or release link.

### #3

Thanks for the suggestion and the designs! I've added the existing logo from @wifi75's fork. Thanks @wifi75 for sharing it.

### #4

You can now add separate configurations and use Reconfigure to add or remove devices without recreating the integration. I only have one AC, so I'd appreciate confirmation that discovery and commands work with all four of yours.

### #6

The integration now ignores unsupported properties such as `version` instead of logging them as failed updates. Please let me know if this error still appears after updating.

### #7

I haven't confirmed the cause of this signature failure yet. I've improved message validation and removed decrypted payloads from error logs. Could you share your device model, diagnostics, and whether this starts after a restart or connection loss? Please don't post LAN keys or account credentials.

### #8

I've fixed the parser failure caused by the Quiet-mode value in your report and a problem with queued control changes. The Quiet switch is still available. Could you test enabling it from both HA and the remote, then check that HA follows the actual state?

### #9

Sleep is available as a select entity under the device. Its choices are now labeled Off and Profile 1–4. I haven't verified what each profile does on every model, so please let me know which ones work on yours.

### #10

The integration now retries failed registration requests and waits for three consecutive failures before marking a device unavailable. This should reduce brief state changes, but I haven't confirmed the cause on your network. Please let me know if the flapping continues.

### #11

I've added regression checks for both control values in your report. An unknown fan-speed value no longer prevents the other fields from updating, and unsupported properties are ignored. Could you try sending commands with Quiet enabled and confirm whether they work now?

### #12

Separate configurations are now supported, so you can add devices from both accounts. Electricity and voltage also stay unknown until a value arrives, instead of starting at the protocol defaults of 100 and 0.

I still don't have a verified unit or scale for `f_electricity`. If those values persist after updating, please share diagnostics so we can check what your units actually report.
