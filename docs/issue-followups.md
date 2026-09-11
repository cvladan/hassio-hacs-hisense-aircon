# Community changes and issue follow-ups

The changes are merged and pushed to `main`. The working branch has been deleted. No release has been published. Replies below link to the comments posted on September 11, 2026.

## Implementation map

| Issue | Change | Commit | What remains |
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

PR [#5](https://github.com/cvladan/hassio-hacs-hisense-aircon/pull/5) is closed without merging. Its useful functionality was implemented independently in `6397530`, with credit to @szupi-ipuzs. This avoids its migration and reconfiguration problems while preserving existing configuration and entity identifiers.

Other commits cover changing one device IP (`fbbe5b2`, inspired by @Gchaimke), removing duplicate climate controls (`3a79e83`, inspired by @wifi75), and the converted 16 C temperature boundary (`54c2362`, inspired by @castiel10k). The README contains replacements for automations that use the removed controls.

## Published replies

| Issue | Status | Reply |
| --- | --- | --- |
| #3 | Closed as completed | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/3#issuecomment-5628306630) |
| #4 | Closed as completed | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/4#issuecomment-5628306940) |
| #6 | Closed as completed | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/6#issuecomment-5628307249) |
| #7 | Open for investigation or device confirmation | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/7#issuecomment-5628307588) |
| #8 | Open for investigation or device confirmation | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/8#issuecomment-5628307737) |
| #9 | Closed as completed | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/9#issuecomment-5628307860) |
| #10 | Open for investigation or device confirmation | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/10#issuecomment-5628308175) |
| #11 | Closed as completed | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/11#issuecomment-5628308322) |
| #12 | Open for investigation or device confirmation | [Posted comment](https://github.com/cvladan/hassio-hacs-hisense-aircon/issues/12#issuecomment-5628308660) |
