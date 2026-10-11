# Maximum-context acceptance summary

[中文](ACCEPTANCE.md) | English

Current version: **2.2.2 / 10**. Supported bundled CLI: **0.162.0-alpha.17.2**. The real-configuration and native-chat acceptance below was performed with version 2.2.1 / 9. Its configuration-processing and protection code is unchanged in this translation update.

| Item | Result and evidence |
| --- | --- |
| Individual model save and restore | Isolated configuration verified through the actual packaged application and official CLI; only selected models’ context values changed |
| Save to the real configuration | The user manually saved Astra only; restricted read-only inspection confirmed that the configuration and transaction record agreed |
| Reopen the switcher after saving | The tool was actually quit and reopened; it correctly recognized maximum context for Astra and defaults for the other models |
| Real manual undo | The user performed undo; read-only inspection confirmed that all configuration bytes matched the backup from before saving |
| Interface and error protections | The foreground window passed acceptance; the process-query failure message was corrected, and the actual production sandbox verified the no-match result |
| Native chat capacity | After saving and restarting Codex, the user observed 828k in a new Astra chat’s native context tooltip, matching the rounded effective window: 872000 × 95% = 828400 |
| Native model list | After saving and restarting Codex, the user reported that the model list looked unchanged; accepted on the basis of that actual observation |
| Original public source archive | Independent extraction and build succeeded; 68 explicit tests plus 34 runtime, isolation, and UI checks passed with zero failures and zero skips; strict signature and file digests passed |

The required maximum-context acceptance was completed. Native interface observations were supplied by the user. Public source excludes private records, configurations, and screenshots. The observed 828k confirms adoption of the expanded window by that new Astra chat; it is not a stress test of full-capacity server input and does not promise compatibility with future Codex versions.

## Chinese/English display update

The interface now offers Chinese or English, with Chinese as the default. The choice is process-local and resets when the tool is reopened. All 49 actual AppKit UI checks passed, including repeated language switching, unsaved selections, enabled controls, busy state, scroll position, success/error messages, and English button label sizes.

The 15 core files and the worker/sandbox function bodies are byte-for-byte identical to the accepted version. This update did not modify the user’s real configuration.

After rebuilding the final public source copy, all 68 tests, 14 runtime checks, 7 isolation checks, and 49 UI checks passed: 138 in total, with zero failures and zero skips. Strict signature verification passed.
