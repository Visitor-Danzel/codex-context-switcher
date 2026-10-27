# Codex Context Switcher

[中文](README.md) | English

A macOS maximum-context switcher with individual model selections. Version **2.2.4 / 12**.

Select the models you want to expand, save, and restart Codex. Unselected models retain their default context. The tool supports restoring defaults, undoing the last save, and reading the actual configuration again after you quit and reopen the tool.

## Application icon

<img src="AppIcon.png" width="128" height="128" alt="Codex Context Switcher application icon">

The icon resources are included with the source and are automatically packaged during a normal build. No separate download is needed. The icon update changes no functionality or settings.

## Interface language

Choose **中文** or **English** at the top right. Chinese is the default. Switching languages only changes interface labels, messages, and dialogs. It does not save or refresh the configuration, change model selections or unsaved choices, or change which controls are enabled. The language choice lasts for the current run only; reopening the tool restores Chinese. No language preference is written to the Codex configuration.

## Usage

1. Install Xcode Command Line Tools, Python 3.11 or later, and a currently supported Codex desktop application. The tool looks for `/usr/local/bin/python3` or `/opt/homebrew/bin/python3`.
2. From the source directory, run `sh scripts/build-context-repair-candidate.sh`, then run `open "build/legacy-context-repair-candidate/Codex Context Switcher.app"`.
3. Select models and click **Save**. Fully quit Codex desktop and the official CLI, close configuration editors, then confirm saving in the tool’s dialog. Do not let other programs edit the configuration during saving.
4. Reopen Codex to use the saved configuration. To undo, quit Codex again and click **Undo last save**. **Defaults** restores default context; its confirmation dialog explains the change before applying it.

To check a native chat’s context capacity, press `⌘,` in Codex to open Settings. Under General, enable **Show context window usage** (Chinese label: “显示上下文窗口使用情况”). Return to a chat using the selected model and hover over the context ring below the input. Read the total capacity in the tooltip. If no usage data is available, first let the model complete a short reply. Whether the indicator appears is separate from the saved configuration state; the numbers shown by this switcher are not proof of a chat’s actual capacity.

Codex must be closed during saving to avoid concurrent configuration edits. Restarting after saving is necessary because Codex loads the model catalog at startup. Closing the switcher does not automatically revert settings. Reopening it reads the current configuration again.

## Client updates, missing models, and saved-catalog upgrades

This tool does not modify the native Codex application, but its saved `model_catalog_json` setting controls the native model list's data source. A local catalog takes precedence over online model discovery. It is a snapshot from the installed client at build time, and does not automatically add later models. Updating Codex while retaining an old catalog can therefore hide new models.

Version 2.2.4 / 12 supports the complete 12-model catalog from bundled CLI `0.165.0-alpha.1.2`, including GPT-6.1-Terra (default 500000, maximum 872000 tokens). Only selected context values change; all other fields come from the complete current official snapshot. This does not grant model access.

To upgrade, open the new tool and check that your previous selections are preserved. If it says the catalog needs updating, fully quit Codex and the official CLI, close configuration editors, then click Save and confirm. Reopen Codex and check Advanced in the model picker. Replacing the tool alone does not write real settings or immediately expand an existing chat.

Migration requires a tool-owned content-addressed path and a match against reviewed historical catalog metadata, every model's other fields, and valid historical context values. Unknown catalogs, modified non-context fields, and invalid limits remain blocked. Old files are preserved and the configuration is backed up before saving. Explicit Defaults and manual Undo remain available. Undo can restore the older catalog, which can hide newer models again. External configuration changes are never silently rolled back.

If a future model is missing, update the tool and save as above, or explicitly restore defaults after quitting Codex to use native discovery again. Do not delete files, bypass checks, or re-sign Codex to repair the model list. See the official [catalog documentation](https://learn.chatgpt.com/docs/model-catalogs) and [Terra announcement](https://learn.chatgpt.com/docs/whats-new/october-26-30-2026).

## Supported environment

Tested on macOS arm64 with the desktop-bundled CLI `0.165.0-alpha.1.2`, under `/Applications/ChatGPT.app`. The model catalog is obtained from the locally installed official CLI in an isolated environment and is not distributed with this source. In the matched catalog, expandable models such as Astra have default context 272000 and maximum context 872000. Values depend on the catalog bundled with the matching version.

This tool changes a local setting supported by the official configuration mechanism. It does not bypass server, account, or model limits, and does not guarantee immediate expansion of an existing chat. **Enabled** means the setting has been saved and the configuration correctly references it; actual adoption by a chat must be confirmed separately. This is a third-party tool, not an official product.

When Codex updates, an older build stops accepting new saves while retaining safe manual undo. Rebuild and verify against the current version. Unknown layouts or incompatible catalogs stop the operation; compatibility with future versions is not assumed.

## Required protections

The tool edits only the root-level `model_catalog_json` key in the user’s `~/.codex/config.toml`. It uses the full current catalog and changes context values only for selected models, preserving model order, hidden status, and other fields. Tool-owned catalogs, private backups, and transaction records reside under `~/Library/Application Support/CodexContextSwitcher/`.

Configuration identity and external changes are checked before and after saving. Conflicts stop the operation. If saving is interrupted, backups and records are preserved; the tool does not automatically overwrite or roll back the configuration.

Restricted child processes are denied network access and access to chat databases, authentication data, and the keychain. The tool does not modify the Codex application or terminate native processes on the user’s behalf. Command-line access to the real configuration is read-only; write-testing commands accept only strictly private disposable directories. Public source excludes chats, personal configurations, backups, generated model catalogs, and unrelated product modules.

## Verification

Build first, then run `sh scripts/test-maximum-context.sh`. This command runs an explicit list of tests with isolated configuration fixtures; it does not replace real desktop acceptance. See [ACCEPTANCE.en.md](ACCEPTANCE.en.md) for evidence and limits. Actual saving, manual undo, switcher restart recognition, and a new native Astra chat displaying 828k were accepted in version 2.2.1 / 9. Version 2.2.2 / 10 adds display translation while preserving the underlying configuration and protection code.

Version 2.2.3 / 11 adds the MIT License and clarifies the footer: the saved configuration is shown above, and this tool does not automatically detect a chat’s actual capacity. Saving, undo, permissions, and the icon are unchanged. After the user reported updating the desktop client, local checks found the same bundled CLI version, `0.162.0-alpha.17.2`, and matching CLI binary. This does not automatically establish capacity acceptance for every new chat.

## Official configuration references

- [Model catalogs and startup loading](https://learn.chatgpt.com/docs/enterprise/roll-out-a-gateway)
- [Configuration layers and session state](https://learn.chatgpt.com/docs/developer-settings)

## License

This project is licensed under the [MIT License](LICENSE). Use, modification, distribution, and commercial use are permitted with preservation of the copyright and license notices. Modified versions need not remain open source. The software is provided as is. Automatic model routing, quota features, and other product work are outside this release’s scope.
