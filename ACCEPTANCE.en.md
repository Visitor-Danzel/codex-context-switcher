# 2.3.0 / 14 catalog-mode acceptance scope

[中文](ACCEPTANCE.md) | English

**2026-10-28: this real-save, restart, and selected-model adoption round passed.** The user explicitly accepted catalog mode and restart/new-chat application. The catalog replaces native online discovery; an unaffected native list is not promised.

| Verification | Evidence from this round |
| --- | --- |
| Real configuration save | After the user's explicit save, read-only verification found Sol 6.1 and Luna 6 at 872000, other models at bundled defaults, the 12-model catalog active, and no configuration conflict |
| Transaction integrity | Current configuration matches the committed transaction; the before-backup and reverse span agree; only the root catalog reference changed, with other configuration content preserved |
| Restart and actual capacity | The user reported 828k in the native context indicator in both new Sol and Luna chats after reopening Codex |
| Terra visibility | The user confirmed GPT‑6.1 Terra is now visible in the native model list |
| Fresh reading and Undo | A new read-only inspection process correctly recognized the saved choices and an available Undo record. Actual packaged 2.3.0 fixtures passed Defaults and exact Undo. Historical manual real-Undo evidence remains historical, not a claim that Undo was repeated in this round |

Current bundled metadata for Sol and Luna uses a 95% effective-context ratio: 872000 × 95% = 828400, consistent with the 828k display. Native UI results are the user's actual observations. Chat/database inspection was not substituted for those observations, and verification did not rewrite real settings.

## Implementation and isolated checks

Independent build from the final minimal public source passed 89 automated tests, 14 runtime checks, 7 isolation checks, and 65 AppKit UI checks: 175 total, no failures or skips, plus strict app-signature verification. Five actual packaged end-to-end fixtures (Sol, Astra, Luna, Terra individually and Sol + Terra) loaded in the current official CLI. Every catalog field matched except selected capacities; Defaults, exact Undo, and fresh inspection passed.

A fresh review identified unsafe Undo when an older catalog was missing or modified; failing tests reproduced it before the fix. Closed-process, exclusive-edit, confirmation, runtime-identity, and external-edit protections remain. Both languages and obsolete-choice disclosures were checked.

## Scope and future updates

This round covers the current client, adoption for the two selected models, and Terra visibility. It is not full-window server stress testing of every model or guaranteed compatibility with future Codex versions. The tested bundled CLI is 0.165.0-alpha.1.2. After a client update, rebuild to obtain its updated bundled catalog and explicitly save; server-only additions are not discovered automatically.

The native Codex app was not modified or re-signed. Frozen personal-control modules were not run; authentication files, keychains, and real chats were not read. Routing, quotas, and other product modules are outside this release.
