#import <Foundation/Foundation.h>
// Display-only, process-local preference. Never reads or writes user settings.
static BOOL MaximumEnglish = NO;
static NSString *MaximumText(NSString *chinese) {
 if (!MaximumEnglish) return chinese;
 static NSDictionary<NSString *, NSString *> *translations;
 static dispatch_once_t once;
 dispatch_once(&once, ^{
  translations=@{
   @"最大上下文":@"Maximum Context",
   @"为每个模型分别选择；其他模型保留默认。":@"Choose models individually; others keep their defaults.",
   @"正在读取设置…":@"Reading settings…",
   @"保存":@"Save",
   @"恢复默认":@"Defaults",
   @"撤销上次保存":@"Undo last save",
   @"刷新":@"Refresh",
   @"上方显示已保存的配置。保存后请重新打开 Codex，并使用新聊天。\n本工具不自动检测聊天实际容量，请在 Codex 上下文圆环中查看。":@"Saved configuration is shown above. Restart Codex after saving and use a new chat.\nThis tool does not detect chat capacity; check Codex’s context ring.",
   @"检查上次保存":@"Check last save",
   @"可扩展":@"Can be expanded",
   @"正在处理，请稍候…":@"Working, please wait…",
   @"上次保存中断，需要检查。备份已保留；工具不会自动覆盖配置。":@"The last save was interrupted and needs checking. Backups are preserved; the tool will not overwrite the configuration automatically.",
   @"Codex 已更新：暂停新设置，保留状态读取和安全撤销。请更新工具。":@"Codex has updated: new changes are paused; status reading and safe undo remain available. Update the tool.",
   @"已有其他上下文设置或配置档，存在冲突；请先处理，工具不会擅自删除。":@"Other context settings or profiles conflict with this setting. Resolve the conflict first; the tool will not delete them.",
   @"有未保存的选择 · 准备让 %lu 个模型使用最大上下文":@"Unsaved selections · Maximum-context models selected: %lu",
   @"当前配置：默认上下文。勾选模型后点“保存”。":@"Current configuration: default context. Select models, then click Save.",
   @"当前配置仍引用旧清单。点“保存”可换为当前完整清单，旧文件会保留。":@"The configuration still refers to an older catalog. Click Save to use the current full catalog; older files will be preserved.",
   @"模型清单需要更新，原有勾选已保留。点“保存”更新后重开 Codex，新增模型才会进入列表。":@"The model catalog needs updating; your selections are preserved. Save and restart Codex to load newly added models.",
   @"当前配置：已启用 · %lu 个模型使用最大上下文":@"Current configuration: enabled · Maximum-context models: %lu",
   @"默认 %@ → 最大 %@ tokens%@":@"Default %@ → Maximum %@ tokens%@",
   @" · 内部模型":@" · Internal model",
   @"使用最大":@"Use maximum",
   @"已是最大":@"Already maximum",
   @"可扩展；勾选后需点保存才写入配置。":@"Can be expanded; click Save after selecting to write the configuration.",
   @"该模型的默认值已经等于最大值。":@"This model’s default context is already its maximum.",
   @"操作未完成":@"Operation not completed",
   @"知道了":@"OK",
   @"检查上次中断的保存？":@"Check the interrupted save?",
   @"撤销上次保存？":@"Undo the last save?",
   @"恢复默认上下文？":@"Restore default context?",
   @"保存最大上下文选择？":@"Save maximum-context selections?",
   @"以下 %lu 个模型使用最大上下文：\n%@\n其他模型使用默认值。":@"These %lu models will use maximum context:\n%@\nOther models will use their defaults.",
   @"将配置还原到上次保存之前。":@"Restore the configuration to its state before the last save.",
   @"移除本工具的清单设置，恢复 Codex 内置默认值。":@"Remove this tool’s catalog setting and restore Codex’s built-in defaults.",
   @"对照备份确认上次保存是否完成。只更新本工具的记录，不改 Codex 配置；如果配置被其他程序改动，将停止检查。请先完全退出 Codex，并关闭配置编辑器。":@"Check the backup to determine whether the last save completed. Only this tool’s record is updated; the Codex configuration is unchanged. The check stops if another program has changed the configuration. Fully quit Codex and close configuration editors first.",
   @"\n\n只修改 config.toml 的模型清单路径。先完全退出 Codex；保存后重新打开 Codex，在新聊天中使用。原始配置备份会保留。":@"\n\nOnly the model catalog path in config.toml is changed. Fully quit Codex first; restart it after saving and use a new chat. A backup of the original configuration will be preserved.",
   @"确认保存":@"Confirm save",
   @"取消":@"Cancel",
   @"我已完全退出 Codex":@"I have fully quit Codex",
   @"配置编辑器已关闭，保存时没有其他程序改配置":@"Editors are closed; no other app will edit the config during saving",
   @"已撤销。重新打开 Codex 后加载恢复的配置。":@"Undone. Restart Codex to load the restored configuration.",
   @"已保存。重新打开 Codex，在新聊天中使用。":@"Saved. Restart Codex, then use a new chat.",
   @"退出最大上下文":@"Quit Maximum Context",
   @"仍检测到 Codex／ChatGPT 或 Codex 命令行进程在运行。请退出后再保存；工具不会代你结束这些进程。":@"Codex/ChatGPT or a Codex CLI process is still running. Quit it before saving; this tool will not stop those processes for you.",
   @"工具未能查询进程列表，不能确认 Codex 是否退出。操作已停止，请刷新检查当前状态；这不表示你没有退出 Codex。":@"The process list could not be checked, so the tool cannot confirm that Codex has quit. The operation stopped. Refresh to check again; this does not mean you failed to quit Codex.",
   @"请关闭配置编辑器，并确认保存期间没有其他程序修改配置。":@"Close configuration editors and confirm that no other program will edit the configuration during saving.",
   @"Codex 已更新。本版本会保留当前设置和撤销功能，暂停新设置；需要更新工具的模型清单。":@"Codex has updated. Current settings and undo are preserved, but new changes are paused. The tool’s model catalog needs updating.",
   @"工具模型清单发生变化，请使用重新验证的工具版本。":@"The tool’s model catalog has changed. Use a newly verified tool build.",
   @"配置中已有上下文覆盖、配置档或其他提供商。需要先处理冲突，工具不会擅自删除。":@"The configuration contains context overrides, profiles, or another provider. Resolve the conflict first; the tool will not remove them.",
   @"Codex 正在使用其他模型清单。工具不会直接覆盖它。":@"Codex is using another model catalog. The tool will not overwrite it.",
   @"当前模型清单发生了外部变化。请先检查，或在可用时撤销上次保存。":@"The current model catalog was changed externally. Check it first, or undo the last save if safe undo is available.",
   @"配置或模型资料已变化。没有覆盖这次变化，请刷新后重新操作。":@"The configuration or model data has changed. Those changes were not overwritten. Refresh and try the operation again.",
   @"确认等待超过两分钟，请重新操作。":@"The confirmation expired after two minutes. Start the operation again.",
   @"其他程序修改了配置，自动撤销已暂停，避免覆盖它的修改。":@"Another program changed the configuration. Automatic rollback is paused to avoid overwriting its changes.",
   @"当前没有可以安全撤销的保存。":@"There is no save that can be safely undone.",
   @"上次保存中途停止，结果需要检查。备份已保留，工具不会自动覆盖当前配置。":@"The last save stopped partway through and needs checking. Backups are preserved; the tool will not overwrite the current configuration automatically.",
   @"保存服务未能启动。请检查 Python 3.11 以上和系统沙箱是否可用。":@"The saving service could not start. Check that Python 3.11 or later and the system sandbox are available.",
   @"文件访问或保存未完成。请刷新状态；如果显示保存中断，请保留备份并检查。":@"File access or saving did not complete. Refresh the status; if it reports an interrupted save, preserve the backups and check it.",
   @"设置目录或请求不符合安全范围，操作已停止。":@"The settings directory or request is outside the permitted scope. The operation stopped.",
   @"选择的模型不可扩展或已经变化，请刷新模型列表。":@"A selected model cannot be expanded or has changed. Refresh the model list.",
   @"操作未完成。没有自动重试，请刷新状态并检查设置。":@"The operation did not complete. No automatic retry was attempted. Refresh the status and check the settings."
  };
 });
 return translations[chinese] ?: chinese;
}
