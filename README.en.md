# Codex Context Switcher

[中文](README.md) | English

**2.3.0 / 14 restores independent per-model maximum-context controls in catalog mode.** Startup only reads settings. Configuration changes require Save and explicit confirmation. Chinese / English and the app icon are preserved.

## Understand catalog mode first

This tool uses the official `model_catalog_json` configuration. It supplies per-model context capacities **and makes Codex use this tool's catalog instead of native online model discovery**. That tradeoff is explicit in this release. The earlier claim that the native model list was unaffected remains withdrawn.

At build time, the tool obtains the installed official CLI's complete bundled catalog using `debug models --bundled`. It preserves model order and all metadata, changing only selected models' `context_window`. Bundled inventory is not a live account-availability list: listing Terra or another model does not grant access. Models already at their maximum display “Already maximum” without a redundant switch.

**New models are not discovered automatically.** After a Codex client update, the tool blocks new saves using the old runtime identity. Rerun the build script to obtain the updated client's bundled catalog, then explicitly save the upgrade. A server-only model release may still be missing even if your client version has not changed. This release cannot discover or guarantee all server-side additions. Use Defaults when native live model discovery is needed.

## Build and use

Requires macOS 13+, Xcode Command Line Tools, and Python 3.11+. Tested on macOS arm64 with official bundled CLI 0.165.0-alpha.1.2 at `/Applications/ChatGPT.app`.

```sh
sh scripts/build-context-repair-candidate.sh
open "build/legacy-context-repair-candidate/Codex Context Switcher.app"
```

1. Select maximum context for each desired model. Others keep bundled defaults.
2. Fully quit the Codex / ChatGPT desktop app and official CLI, and close configuration editors.
3. Click Save, read the scope disclosure, and confirm the exit and exclusive-edit conditions.
4. Reopen Codex, use a new chat, and check actual capacity in the native context indicator.

This release does not guarantee that the next prompt reloads capacity in an existing chat; restart plus a new chat is the verification path. Restarting the switcher rereads actual configuration rather than guessing from previous UI state. Saved configuration and actual chat adoption are distinguished; the tool does not inspect chats to confirm adoption.

Defaults removes this tool's catalog override **and its capacity settings**, returning model discovery to Codex. Undo restores the previous configuration and may restore an older catalog; it stops if that catalog is modified or missing. Upgrades preserve still-expandable choices. Removed or no-longer-expandable previous choices are disclosed in the window and confirmation before they are omitted.

## Transaction protection and limits

Only the root `model_catalog_json` entry in the user's `~/.codex/config.toml` is edited. Generated catalogs and private transaction backups live under `~/Library/Application Support/CodexContextSwitcher`. Other configuration bytes are preserved. The tool does not modify or re-sign the native app, or handle chat databases, authentication files, keychains, routing, quotas, or personal controls. The configuration worker is denied network access.

Saving requires closed processes, a fresh confirmation, unchanged runtime/source identities, and no detected external configuration edits. Private backups are preserved. Interrupted operations are checked without automatic rollback or overwriting. Unsafe paths, unknown third-party catalogs, and conflicting capacity configuration stop the operation. Avoid concurrent editing during Save: the tool cannot lock out every external editor.

Quitting the tool does not withdraw settings automatically. Defaults, Undo, regeneration, and real-configuration saves always require explicit action.

## Verification

```sh
sh scripts/test-maximum-context.sh
```

Automated tests use explicit isolated fixtures; see [acceptance scope](ACCEPTANCE.en.md). Version 2.3.0 has now passed one real-use acceptance round: after the user quit Codex, saved the selections, and reopened it, both GPT‑6.1 Sol and GPT‑6 Luna showed 828k in the native context indicator, and GPT‑6.1 Terra appeared in the model list. Read-only verification confirmed 872000 configured for both models and a consistent saved transaction. Their current bundled metadata uses a 95% effective-context ratio: 872000 × 95% = 828400, consistent with the 828k display. The user performed the save; verification did not rewrite settings. These observations cover the selected models, not full-window server stress testing of every model or guaranteed compatibility with future versions.

<img src="AppIcon.png" width="128" height="128" alt="App icon">

## Official references and license

[Model catalogs](https://learn.chatgpt.com/docs/model-catalogs) · [Capacity configuration](https://learn.chatgpt.com/docs/config-file/config-reference)

[MIT License](LICENSE). Use, modification, distribution, and commercial use are permitted with the copyright and license notice retained. Routing, quota features, and other product modules are outside this release.
