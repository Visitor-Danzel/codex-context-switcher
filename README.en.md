# Codex Context Switcher

[中文](README.md) | English

## Important correction: catalog mode is paused

Version **2.2.5 / 13** is a containment and withdrawal release. **It is not a completed per-model maximum-context switcher that leaves native model discovery unchanged.**

Earlier versions used `model_catalog_json` for per-model context values. That setting also controls the native Codex model list and prevents normal online discovery. An old snapshot can omit newly released models. "The native application files are unchanged" did not establish "the native model list is unaffected." Refreshing the snapshot in 2.2.4 did not remove this fundamental side effect. The earlier completion/recommendation claim is withdrawn.

**Saving catalogs and using Undo to reinstall them are disabled for real configurations. Do not use earlier releases to enable or refresh the override.** Read-only status, explicitly confirmed Defaults withdrawal, and journal-only interrupted-record checks remain available. Historical functionality remains only in strictly disposable fixture mode for regression testing, not as a production feature promise.

## Restore native model discovery first

1. Build with `sh scripts/build-context-repair-candidate.sh`, then run `open "build/legacy-context-repair-candidate/Codex Context Switcher.app"`.
2. Fully quit Codex and the official CLI, and close configuration editors.
3. Click Defaults and explicitly confirm the withdrawal notice. It removes only the recognized `model_catalog_json` override written by this tool. **It also withdraws the maximum-context settings supplied by this tool.** Other configuration is preserved; backups and external-change checks remain.
4. Reopen Codex and inspect its native model picker. The official Terra entry is under Advanced; account and workspace access still determine availability.

Do not keep clicking Save in an old release to refresh the list, delete native chats/databases, or modify or re-sign Codex. Exiting this tool or installing a newer build does not automatically change real configuration; explicit withdrawal is required. Unknown/damaged catalogs, conflicts, and interrupted transactions stop safely rather than bypass checks.

## The goal remains unfinished

The goal is independent maximum-context control for GPT-6.1 Sol, GPT-6 Astra, GPT-6 Luna, GPT-6.1 Terra, and other models while leaving the native model list and other behavior unchanged. **No replacement satisfying that complete constraint has been verified.** A shared limit will not be represented as per-model control, nor a replacement catalog as a context-only edit.

The official `model_context_window` setting directly controls capacity, but this project has not verified an official path for independent persistent per-model control without taking over discovery. That must be established before production writes are enabled.

## Interface, build, and protections

Chinese and English are available at the top right; Chinese is the default. Language changes only relabel the interface. The icon is included in normal builds.

<img src="AppIcon.png" width="128" height="128" alt="Application icon">

Tested on macOS arm64 with bundled CLI `0.165.0-alpha.1.2` under `/Applications/ChatGPT.app`. Xcode Command Line Tools and Python 3.11 or later are required. The build does not modify native application files or read chat databases, authentication files, or keychains. Configuration workers cannot use the network. Path identity, preview confirmation, external-change, process-exit, and exclusive-edit protections remain. No automatic overwrite or rollback is performed; backups are retained.

Build first, then run `sh scripts/test-maximum-context.sh`. Only explicitly listed isolated fixtures are used. Technical tests do not prove that the native-list requirement is satisfied or that real withdrawal has occurred. See [ACCEPTANCE.en.md](ACCEPTANCE.en.md) for historical evidence and the correction. Public source excludes real configurations, chats, original generated model catalogs, private acceptance records, and unrelated modules.

## Official references

- [Catalogs control model discovery and take precedence over remote fetching](https://learn.chatgpt.com/docs/model-catalogs)
- [Official context configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Terra announcement and picker location](https://learn.chatgpt.com/docs/whats-new/october-26-30-2026)

## License

[MIT License](LICENSE). Use, modification, redistribution, and commercial use are permitted with preservation of the copyright and license notices. The software is provided as is. Routing, quota features, and other product work are outside this release.
