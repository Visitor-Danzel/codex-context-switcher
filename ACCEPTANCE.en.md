# 2.3.0 / 14 catalog-mode acceptance scope

The user explicitly accepted catalog mode and restart/new-chat application. Catalog mode replaces native online model discovery; this release no longer promises an unaffected native list.

Current state: implementation and isolated acceptance are in progress; real configuration has not been changed automatically. Final public-package counts and official CLI loading results will be recorded after verification. Historical Astra 828k and real Undo observations remain historical evidence, not acceptance of every model in this release.

Changes: restore production Save and Undo while retaining closed-process, exclusive-edit, confirmation, and external-edit protection; disclose catalog scope in both languages; explicitly disclose obsolete choices; validate the catalog restored by Undo and recheck it before publication. A fresh review's missing/modified Undo-catalog finding was reproduced by failing tests and fixed.

After a client upgrade, rebuilding obtains its current bundled catalog, recognizes supported previous choices, and requires an explicit save. This is not automatic online discovery and cannot guarantee immediate visibility of server-only models. Frozen personal-control modules, real chats, credentials, and keychains were not accessed.

Independent public-source build passed 89 automated tests, 14 runtime checks, 7 isolation checks, and 65 AppKit UI checks: 175 total, no failures or skips, plus strict app-signature verification. Five actual packaged end-to-end fixtures (Sol, Astra, Luna, Terra individually and Sol + Terra) loaded successfully in the current official CLI. Every catalog field matched the source except selected capacities; Defaults, exact Undo, and restart inspection passed.
