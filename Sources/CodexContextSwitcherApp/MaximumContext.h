#import <Cocoa/Cocoa.h>
#import "CodexContextCore.h"
#import "MonitorSandbox.h"
#import "MaximumLanguage.h"

static NSString *MaximumTestRoot;
static NSString *MaximumPolicy(NSString *python,NSString *resources,NSString *testRoot) {
 resources=CCMonitorSandboxPath([resources stringByAppendingPathComponent:@"current-models.json"]).stringByDeletingLastPathComponent;
 if(!resources.length || !CCMonitorSandboxPath(python))return nil;
 if(testRoot && ![CCRepairSession isIsolatedTestRoot:testRoot])return nil;
 NSString *base=testRoot ?: [NSHomeDirectory() stringByAppendingPathComponent:@".codex"];
 NSString *config=[base stringByAppendingPathComponent:@"config.toml"];
 NSString *root=testRoot?[testRoot stringByAppendingPathComponent:@"settings"]:[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/CodexContextSwitcher"];
 NSString *legacy=testRoot?[testRoot stringByAppendingPathComponent:@"models-custom.json"]:[base stringByAppendingPathComponent:@"context-switcher/models-custom.json"];
 if(!CCMonitorSandboxPath(config) || !CCMonitorSandboxPath(root))return nil;
 NSMutableString *policy=[NSMutableString stringWithString:@"(version 1) (deny default) (allow process*) (allow sysctl-read) (allow file-read-metadata) (allow file-read* (literal \"/\") (literal \"/dev/null\") (literal \"/dev/urandom\") (subpath \"/System\") (subpath \"/usr/lib\") (subpath \"/usr/bin\") (subpath \"/bin\") (subpath \"/Library/Apple\") (subpath \"/Library/Frameworks/Python.framework\") (subpath \"/Library/Developer/CommandLineTools\")) (allow file-write-data (literal \"/dev/null\")) "];
 // pgrep obtains names through sysmond on current macOS. No other service
 // lookup, process arguments, native files or networking is authorized here.
 [policy appendString:@"(allow mach-lookup (global-name \"com.apple.sysmond\")) "];
 for(NSString *path in @[python,resources,config,base,root.stringByDeletingLastPathComponent,legacy,
      [resources stringByAppendingPathComponent:@"current-models.json"],[resources stringByAppendingPathComponent:@"catalog-record.json"],
      @"/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json",
      @"/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"]) {
  [policy appendFormat:@"(allow file-read* (literal %@)) ",CCMonitorSandboxLiteral(path)];
 }
 for(NSString *path in @[[resources stringByAppendingPathComponent:@"ModelContextSettings"],[resources stringByAppendingPathComponent:@"ContextSettings"],root])
  [policy appendFormat:@"(allow file-read* (subpath %@)) ",CCMonitorSandboxLiteral(path)];
 NSMutableString *hex=[NSMutableString new];for(NSUInteger i=0;i<32;i++)[hex appendString:@"[a-f0-9]"];
 NSString *stage=[NSString stringWithFormat:@"^%@/\\.codex-context-%@\\.tmp$",[NSRegularExpression escapedPatternForString:config.stringByDeletingLastPathComponent],hex];
 [policy appendFormat:@"(allow file-write* (literal %@) (subpath %@) (regex %@)) (allow file-read* (regex %@)) ",CCMonitorSandboxLiteral(config),CCMonitorSandboxLiteral(root),CCMonitorSandboxLiteral(stage),CCMonitorSandboxLiteral(stage)];
 [policy appendFormat:@"(deny file-read* (subpath %@) (subpath \"/System/Library/Keychains\") (subpath \"/Library/Keychains\")) (deny network*) ",CCMonitorSandboxLiteral([NSHomeDirectory() stringByAppendingPathComponent:@"Library/Keychains"])];
 return policy;
}

static NSDictionary *MaximumCall(NSDictionary *request) {
 NSString *python=nil;
 for(NSString *p in @[@"/usr/local/bin/python3",@"/opt/homebrew/bin/python3",@"/usr/bin/python3"])
  if([NSFileManager.defaultManager isExecutableFileAtPath:p]){python=p;break;}
 NSString *resources=NSBundle.mainBundle.resourcePath;
 NSString *policy=python?MaximumPolicy(python,resources,MaximumTestRoot):nil;
 NSData *raw=[NSJSONSerialization dataWithJSONObject:request options:NSJSONWritingSortedKeys error:nil];
 if(!policy||!raw)return @{@"ok":@NO,@"error":@"worker_unavailable"};
 NSString *json=[[NSString alloc] initWithData:raw encoding:NSUTF8StringEncoding];
 NSArray *args=@[@"-p",policy,python,@"-I",@"-S",@"-B",[resources stringByAppendingPathComponent:@"ModelContextSettings/worker.py"],
   MaximumTestRoot?@"--test-root":@"--home",MaximumTestRoot ?: NSHomeDirectory(),@"--request",json];
 NSURL *home=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
 if(![NSFileManager.defaultManager createDirectoryAtURL:home withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil])return @{@"ok":@NO,@"error":@"worker_unavailable"};
 NSDictionary *process=[CCBoundedProcess runExecutableURL:[NSURL fileURLWithPath:@"/usr/bin/sandbox-exec"] arguments:args isolatedHomeURL:home timeout:20 outputLimit:1024*1024 error:nil];
 [NSFileManager.defaultManager removeItemAtURL:home error:nil];
 NSDictionary *reply=process?[NSJSONSerialization JSONObjectWithData:process[@"stdout"] options:0 error:nil]:nil;
 return [reply isKindOfClass:NSDictionary.class]?reply:@{@"ok":@NO,@"error":@"worker_unavailable"};
}

static NSString *MaximumReason(NSString *reason) {
 NSDictionary *reasons=@{
 @"catalog_route_paused":@"此方式会接管 Codex 原生模型列表，已暂停保存。请退出 Codex 后用“恢复默认”撤回本工具的清单覆盖。",
 @"codex_running_or_unknown":@"仍检测到 Codex／ChatGPT 或 Codex 命令行进程在运行。请退出后再保存；工具不会代你结束这些进程。",
 @"desktop_check_unavailable":@"工具未能查询进程列表，不能确认 Codex 是否退出。操作已停止，请刷新检查当前状态；这不表示你没有退出 Codex。",
 @"exclusive_edit_not_confirmed":@"请关闭配置编辑器，并确认保存期间没有其他程序修改配置。",
 @"runtime_changed":@"Codex 已更新。本版本会保留当前设置和撤销功能，暂停新设置；需要更新工具的模型清单。",
 @"catalog_source_changed":@"工具模型清单发生变化，请使用重新验证的工具版本。",
 @"configuration_override":@"配置中已有上下文覆盖、配置档或其他提供商。需要先处理冲突，工具不会擅自删除。",
 @"other_catalog":@"Codex 正在使用其他模型清单。工具不会直接覆盖它。",
 @"damaged_catalog":@"当前模型清单发生了外部变化。请先检查，或在可用时撤销上次保存。",
 @"preview_changed":@"配置或模型资料已变化。没有覆盖这次变化，请刷新后重新操作。",
 @"source_changed":@"配置或模型资料已变化。没有覆盖这次变化，请刷新后重新操作。",
 @"preview_expired":@"确认等待超过两分钟，请重新操作。",
 @"external_change":@"其他程序修改了配置，自动撤销已暂停，避免覆盖它的修改。",
 @"undo_catalog_unverified":@"撤销要恢复的模型清单已变化或缺失，已停止。当前配置和备份保留；请检查后再操作。",
 @"undo_unavailable":@"当前没有可以安全撤销的保存。",
 @"uncertain_previous_transaction":@"上次保存中途停止，结果需要检查。备份已保留，工具不会自动覆盖当前配置。",
 @"worker_unavailable":@"保存服务未能启动。请检查 Python 3.11 以上和系统沙箱是否可用。",
 @"operation_failed_check_current_file":@"文件访问或保存未完成。请刷新状态；如果显示保存中断，请保留备份并检查。",
 @"invalid_target_or_request":@"设置目录或请求不符合安全范围，操作已停止。",
 @"invalid_selection":@"选择的模型不可扩展或已经变化，请刷新模型列表。"};
 return reasons[reason] ?: @"操作未完成。没有自动重试，请刷新状态并检查设置。";
}

@interface CCMaximumContextDelegate : NSObject <NSApplicationDelegate,NSWindowDelegate>
@property(nonatomic) NSWindow *window;
@property(nonatomic) NSTextField *summaryLabel;
@property(nonatomic) NSTextField *headingLabel;
@property(nonatomic) NSTextField *subtitleLabel;
@property(nonatomic) NSPopUpButton *languagePicker;
@property(nonatomic) NSArray<NSTextField *> *rangeLabels;
@property(nonatomic) NSString *summarySource;
@property(nonatomic) NSUInteger summaryCount;
@property(nonatomic) NSUInteger omittedCount;
@property(nonatomic) NSMenuItem *quitItem;
@property(nonatomic) NSTextField *footnote;
@property(nonatomic) NSScrollView *scroll;
@property(nonatomic) NSButton *saveButton;
@property(nonatomic) NSButton *defaultsButton;
@property(nonatomic) NSButton *undoButton;
@property(nonatomic) NSButton *refreshButton;
@property(nonatomic) NSArray<NSButton *> *modelButtons;
@property(nonatomic) NSMutableSet *selection;
@property(nonatomic) NSDictionary *status;
@property(nonatomic) BOOL busy;
- (void)buildWindow;
- (void)acceptStatus:(NSDictionary *)status;
@end
@implementation CCMaximumContextDelegate
- (NSTextField *)text:(NSString *)text frame:(NSRect)frame size:(CGFloat)size {
 NSTextField *label=[NSTextField wrappingLabelWithString:text];label.frame=frame;label.font=[NSFont systemFontOfSize:size];return label;
}
- (NSButton *)button:(NSString *)title action:(SEL)action frame:(NSRect)frame {
 NSButton *button=[NSButton buttonWithTitle:title target:self action:action];button.frame=frame;return button;
}
- (void)buildWindow {
 if(self.window)return;
 self.window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,660,570) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable backing:NSBackingStoreBuffered defer:NO];
 self.window.title=MaximumText(@"最大上下文");self.window.releasedWhenClosed=NO;self.window.delegate=self;
 NSView *view=self.window.contentView;
 self.headingLabel=[self text:MaximumText(@"最大上下文") frame:NSMakeRect(24,511,450,36) size:25];[view addSubview:self.headingLabel];
 self.subtitleLabel=[self text:MaximumText(@"为每个模型分别选择 · 清单模式") frame:NSMakeRect(24,482,610,24) size:14];[view addSubview:self.subtitleLabel];
 self.languagePicker=[[NSPopUpButton alloc] initWithFrame:NSMakeRect(512,515,124,28) pullsDown:NO];
 [self.languagePicker addItemsWithTitles:@[@"中文",@"English"]];self.languagePicker.target=self;self.languagePicker.action=@selector(changeLanguage:);
 self.languagePicker.accessibilityLabel=@"语言 / Language";[view addSubview:self.languagePicker];
 self.summaryLabel=[self text:MaximumText(@"正在读取设置…") frame:NSMakeRect(24,427,610,48) size:13];[view addSubview:self.summaryLabel];self.summarySource=@"正在读取设置…";
 self.scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(24,145,612,273)];self.scroll.hasVerticalScroller=YES;self.scroll.borderType=NSBezelBorder;[view addSubview:self.scroll];
 self.saveButton=[self button:MaximumText(@"保存") action:@selector(save:) frame:NSMakeRect(24,96,106,34)];self.saveButton.keyEquivalent=@"\r";
 self.defaultsButton=[self button:MaximumText(@"恢复默认") action:@selector(defaults:) frame:NSMakeRect(144,96,116,34)];
 self.undoButton=[self button:MaximumText(@"撤销上次保存") action:@selector(undo:) frame:NSMakeRect(272,96,145,34)];
 self.refreshButton=[self button:MaximumText(@"刷新") action:@selector(refresh:) frame:NSMakeRect(532,96,104,34)];
 for(NSButton *b in @[self.saveButton,self.defaultsButton,self.undoButton,self.refreshButton])[view addSubview:b];
 self.footnote=[self text:MaximumText(@"模型列表将使用本工具清单；Codex 更新后需重新生成清单。\n随附模型不代表账户实时可用；保存后重启 Codex，在新聊天中使用。\n实际容量请在 Codex 上下文圆环查看。") frame:NSMakeRect(24,24,612,60) size:11];self.footnote.textColor=NSColor.secondaryLabelColor;[view addSubview:self.footnote];
 [self updateControls];[self.window center];
}
- (void)renderSummary {
 NSString *format=MaximumText(self.summarySource ?: @"正在读取设置…");
 self.summaryLabel.stringValue=[NSString stringWithFormat:format,(unsigned long)self.summaryCount];
}
- (void)setSummaryFormat:(NSString *)source count:(NSUInteger)count {
 self.summarySource=source;self.summaryCount=count;[self renderSummary];
}
- (void)setSummary:(NSString *)source {[self setSummaryFormat:source count:0];}
- (void)changeLanguage:(NSPopUpButton *)sender {
 MaximumEnglish=sender.indexOfSelectedItem==1;
 self.window.title=MaximumText(@"最大上下文");self.headingLabel.stringValue=self.window.title;
 self.subtitleLabel.stringValue=MaximumText([self.status[@"catalog_route_paused"] boolValue]?@"清单方式已暂停；仅可检查状态或恢复默认。":@"为每个模型分别选择 · 清单模式");
 self.saveButton.title=MaximumText(@"保存");self.defaultsButton.title=MaximumText(@"恢复默认");
 self.undoButton.title=MaximumText([self.status[@"transaction_state"] isEqual:@"uncertain"]?@"检查上次保存":@"撤销上次保存");
 self.refreshButton.title=MaximumText(@"刷新");self.quitItem.title=MaximumText(@"退出最大上下文");
 self.footnote.stringValue=MaximumText(@"模型列表将使用本工具清单；Codex 更新后需重新生成清单。\n随附模型不代表账户实时可用；保存后重启 Codex，在新聊天中使用。\n实际容量请在 Codex 上下文圆环查看。");
 NSArray *rows=self.status[@"models"] ?: @[];
 for(NSUInteger i=0;i<self.modelButtons.count && i<rows.count;i++) {
  NSDictionary *row=rows[i];NSButton *button=self.modelButtons[i];
  button.title=MaximumText([row[@"can_extend"] boolValue]?@"使用最大":@"已是最大");
  button.toolTip=MaximumText([row[@"can_extend"] boolValue]?@"可扩展；勾选后需点保存才写入配置。":@"该模型的默认值已经等于最大值。");
  if(i<self.rangeLabels.count)self.rangeLabels[i].stringValue=[NSString stringWithFormat:MaximumText(@"默认 %@ → 最大 %@ tokens%@"),row[@"default"],row[@"maximum"],[row[@"hidden"] boolValue]?MaximumText(@" · 内部模型"):@""];
 }
 [self renderSummary];
}
- (void)updateControls {
 BOOL compatible=[self.status[@"runtime_compatible"] boolValue];
 NSString *state=self.status[@"state"];BOOL safe=[@[@"configured",@"default",@"legacy_configured",@"legacy_stale",@"catalog_outdated"] containsObject:state];
 BOOL uncertain=[self.status[@"transaction_state"] isEqual:@"uncertain"];
 BOOL paused=[self.status[@"catalog_route_paused"] boolValue];
 self.subtitleLabel.stringValue=MaximumText(paused?@"清单方式已暂停；仅可检查状态或恢复默认。":@"为每个模型分别选择 · 清单模式");
 BOOL allowed=compatible&&safe&&![self.status[@"configuration_conflict"] boolValue]&&!uncertain&&!self.busy;
 BOOL dirty=self.status && ![self.selection isEqual:[NSSet setWithArray:self.status[@"selected"] ?: @[]]];
 self.saveButton.enabled=allowed&&!paused&&(dirty||[state isEqual:@"legacy_stale"]||[state isEqual:@"catalog_outdated"]);
 self.defaultsButton.enabled=allowed&&![state isEqual:@"default"];
 self.undoButton.title=uncertain?MaximumText(@"检查上次保存"):MaximumText(@"撤销上次保存");
 self.undoButton.enabled=([self.status[@"undo_available"] boolValue]||uncertain)&&!self.busy&&(!paused||uncertain);
 self.refreshButton.enabled=!self.busy;
 for(NSButton *button in self.modelButtons)button.enabled=allowed&&!paused&&[button.toolTip hasPrefix:MaximumText(@"可扩展")];
 if(self.busy)[self setSummary:@"正在处理，请稍候…"];
 else if(uncertain)[self setSummary:@"上次保存中断，需要检查。备份已保留；工具不会自动覆盖配置。"];
 else if(self.status && !compatible)[self setSummary:@"Codex 已更新：暂停新设置，保留状态读取和安全撤销。请更新工具。"];
 else if([self.status[@"configuration_conflict"] boolValue])[self setSummary:@"已有其他上下文设置或配置档，存在冲突；请先处理，工具不会擅自删除。"];
 else if([state isEqual:@"other_catalog"] || [state isEqual:@"damaged_catalog"])[self setSummary:MaximumReason(state)];
 else if(paused && [state isEqual:@"default"])[self setSummary:@"当前使用 Codex 原生模型列表。逐模型上下文开关已暂停，尚无不接管清单的已验证方案。"];
 else if(paused)[self setSummary:@"本工具的清单设置会接管原生模型列表，此方式已暂停。请退出 Codex 后点“恢复默认”撤回。"];
 else if(self.omittedCount>0 && [state isEqual:@"catalog_outdated"])[self setSummaryFormat:@"清单已变化：%lu 个旧选择已移除或不再可扩展；保存后不再沿用。" count:self.omittedCount];
 else if(dirty)[self setSummaryFormat:@"有未保存的选择 · 准备让 %lu 个模型使用最大上下文" count:(unsigned long)self.selection.count];
 else if([state isEqual:@"catalog_outdated"])[self setSummary:@"模型清单需要更新，原有勾选已保留。点“保存”更新后重开 Codex，新增模型才会进入列表。"];
 else if([state isEqual:@"default"])[self setSummary:@"当前配置：默认上下文。勾选模型后点“保存”。"];
 else if([state isEqual:@"legacy_stale"])[self setSummary:@"当前配置仍引用旧清单。点“保存”可换为当前完整清单，旧文件会保留。"];
 else if(self.status)[self setSummaryFormat:@"当前配置：已启用 · %lu 个模型使用最大上下文" count:(unsigned long)self.selection.count];
}
- (void)acceptStatus:(NSDictionary *)status {
 self.status=status;self.selection=[NSMutableSet setWithArray:status[@"selected"] ?: @[]];
 NSArray *rows=status[@"models"] ?: @[];NSMutableSet *eligible=[NSMutableSet new];
 for(NSDictionary *row in rows)if([row[@"can_extend"] boolValue])[eligible addObject:row[@"slug"]];
 NSMutableSet *omitted=[self.selection mutableCopy];[omitted minusSet:eligible];self.omittedCount=omitted.count;
 [self.selection intersectSet:eligible];CGFloat height=MAX(273,rows.count*48);
 NSView *document=[[NSView alloc] initWithFrame:NSMakeRect(0,0,590,height)];NSMutableArray *buttons=[NSMutableArray new];NSMutableArray *ranges=[NSMutableArray new];
 NSUInteger index=0;
 for(NSDictionary *row in rows) {
  CGFloat y=height-(++index)*48;
  NSString *name=[row[@"name"] isKindOfClass:NSString.class]?row[@"name"]:row[@"slug"];
  NSTextField *model=[self text:name frame:NSMakeRect(12,y+24,380,20) size:13];[document addSubview:model];
  NSString *range=[NSString stringWithFormat:MaximumText(@"默认 %@ → 最大 %@ tokens%@"),row[@"default"],row[@"maximum"],[row[@"hidden"] boolValue]?MaximumText(@" · 内部模型"):@""];
  NSTextField *numbers=[self text:range frame:NSMakeRect(12,y+4,390,19) size:11];numbers.textColor=NSColor.secondaryLabelColor;[document addSubview:numbers];[ranges addObject:numbers];
  NSButton *button=[NSButton checkboxWithTitle:[row[@"can_extend"] boolValue]?MaximumText(@"使用最大"):MaximumText(@"已是最大") target:self action:@selector(toggleModel:)];
  button.frame=NSMakeRect(448,y+12,122,24);button.identifier=row[@"slug"];
  button.toolTip=[row[@"can_extend"] boolValue]?MaximumText(@"可扩展；勾选后需点保存才写入配置。"):MaximumText(@"该模型的默认值已经等于最大值。");
  button.state=[self.selection containsObject:row[@"slug"]]?NSControlStateValueOn:NSControlStateValueOff;
  [document addSubview:button];[buttons addObject:button];
 }
 self.scroll.documentView=document;self.modelButtons=buttons;self.rangeLabels=ranges;
 [self.scroll.contentView scrollToPoint:NSMakePoint(0,MAX(0,height-self.scroll.contentView.bounds.size.height))];[self.scroll reflectScrolledClipView:self.scroll.contentView];
 [self updateControls];
}
- (void)toggleModel:(NSButton *)sender {
 if(self.busy||[self.status[@"catalog_route_paused"] boolValue])return;
 if(sender.state==NSControlStateValueOn)[self.selection addObject:sender.identifier];else[self.selection removeObject:sender.identifier];
 [self updateControls];
}
- (void)refresh:(id)sender {
 (void)sender;if(self.busy)return;self.busy=YES;[self updateControls];
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSDictionary *reply=MaximumCall(@{@"operation":@"inspect"});dispatch_async(dispatch_get_main_queue(),^{self.busy=NO;
  if([reply[@"ok"] boolValue])[self acceptStatus:reply[@"result"]];
  else {self.status=nil;self.modelButtons=@[];self.rangeLabels=@[];self.scroll.documentView=nil;[self updateControls];[self setSummary:MaximumReason(reply[@"error"])];}
 });});
}
- (void)showFailure:(NSString *)reason {
 NSAlert *alert=[NSAlert new];alert.messageText=MaximumText(@"操作未完成");alert.informativeText=MaximumText(MaximumReason(reason));[alert addButtonWithTitle:MaximumText(@"知道了")];[alert runModal];
}
- (void)prepare:(NSString *)action {
 if(self.busy)return;self.busy=YES;[self updateControls];NSArray *selected=self.selection.allObjects ?: @[];
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSDictionary *reply=MaximumCall(@{@"operation":@"preview",@"action":action,@"selected":selected});dispatch_async(dispatch_get_main_queue(),^{
  if(![reply[@"ok"] boolValue]){self.busy=NO;[self updateControls];[self showFailure:reply[@"error"]];return;}
  NSDictionary *preview=reply[@"result"];
  NSAlert *alert=[NSAlert new];alert.messageText=[action isEqual:@"recover"]?MaximumText(@"检查上次中断的保存？"):([action isEqual:@"undo"]?MaximumText(@"撤销上次保存？"):([action isEqual:@"defaults"]?MaximumText(@"恢复默认上下文？"):MaximumText(@"保存最大上下文选择？")));
  BOOL withdraw=[self.status[@"catalog_route_paused"] boolValue]&&[action isEqual:@"defaults"];
  if(withdraw)alert.messageText=MaximumText(@"撤回本工具的模型清单设置？");
  NSString *change=[action isEqual:@"save"]?[NSString stringWithFormat:MaximumText(@"以下 %lu 个模型使用最大上下文：\n%@\n其他模型使用默认值。"),(unsigned long)[preview[@"selected"] count],[preview[@"selected"] componentsJoinedByString:@"、"]]:([action isEqual:@"undo"]?MaximumText(@"将配置还原到上次保存之前；也可能恢复当时的旧模型清单。"):MaximumText(@"移除本工具的清单设置，恢复 Codex 内置默认值。"));
  alert.informativeText=[action isEqual:@"recover"]?MaximumText(@"对照备份确认上次保存是否完成。只更新本工具的记录，不改 Codex 配置；如果配置被其他程序改动，将停止检查。请先完全退出 Codex，并关闭配置编辑器。"):[change stringByAppendingString:MaximumText(@"\n\n清单方式会让 Codex 使用本工具的模型列表，并暂停原生在线模型发现；本工具不会自动获得新发布的模型。Codex 更新后需重新生成清单。\n\n只修改 config.toml 的模型清单路径；清单中只改选中模型的上下文值。先完全退出 Codex；保存后重开并使用新聊天。原始配置备份保留。")];
  if([preview[@"omitted_selected"] count])alert.informativeText=[alert.informativeText stringByAppendingFormat:MaximumText(@"\n\n以下旧选择已移除或不再可扩展，保存后不再沿用：%@"),[preview[@"omitted_selected"] componentsJoinedByString:@"、"]];
  if(withdraw)alert.informativeText=MaximumText(@"只移除本工具写入的 model_catalog_json，恢复 Codex 原生模型发现；同时撤回本工具提供的最大上下文设置。其他配置不变，备份保留。\n\n请先完全退出 Codex 和官方 CLI，关闭配置编辑器；确认后重新打开 Codex。");
  [alert addButtonWithTitle:MaximumText(withdraw?@"确认恢复默认":@"确认保存")];[alert addButtonWithTitle:MaximumText(@"取消")];
  NSView *accessory=[[NSView alloc] initWithFrame:NSMakeRect(0,0,440,64)];
  NSButton *closed=[NSButton checkboxWithTitle:MaximumText(@"我已完全退出 Codex") target:nil action:nil];closed.frame=NSMakeRect(0,36,430,24);
  NSButton *exclusive=[NSButton checkboxWithTitle:MaximumText(@"配置编辑器已关闭，保存时没有其他程序改配置") target:nil action:nil];exclusive.frame=NSMakeRect(0,6,440,24);[accessory addSubview:closed];[accessory addSubview:exclusive];alert.accessoryView=accessory;
  NSInteger answer=[alert runModal];
  if(answer!=NSAlertFirstButtonReturn){self.busy=NO;[self updateControls];return;}
  if(closed.state!=NSControlStateValueOn||exclusive.state!=NSControlStateValueOn){self.busy=NO;[self updateControls];[self showFailure:@"exclusive_edit_not_confirmed"];return;}
  NSDictionary *request=@{@"operation":@"apply",@"preview":preview,@"confirmation":preview[@"confirmation"],@"exclusive_edit":@YES};
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSDictionary *saved=MaximumCall(request);dispatch_async(dispatch_get_main_queue(),^{self.busy=NO;
    if([saved[@"ok"] boolValue]){[self acceptStatus:saved[@"result"]];[self setSummary:withdraw?@"已撤回本工具的清单覆盖。请重开 Codex，恢复原生模型发现。":([action isEqual:@"recover"]?@"记录已检查，原生配置没有修改。":([action isEqual:@"undo"]?@"已撤销。重新打开 Codex 后加载恢复的配置。":@"已保存。重新打开 Codex，在新聊天中使用。"))];}
    else {[self updateControls];[self showFailure:saved[@"error"]];[self refresh:nil];}
  });});
 });});
}
- (void)save:(id)sender{(void)sender;[self prepare:@"save"];}
- (void)defaults:(id)sender{(void)sender;[self prepare:@"defaults"];}
- (void)undo:(id)sender{(void)sender;[self prepare:[self.status[@"transaction_state"] isEqual:@"uncertain"]?@"recover":@"undo"];}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
 (void)notification;
 NSMenu *menu=[NSMenu new];NSMenuItem *group=[NSMenuItem new];NSMenu *application=[NSMenu new];
 self.quitItem=[application addItemWithTitle:MaximumText(@"退出最大上下文") action:@selector(terminate:) keyEquivalent:@"q"];group.submenu=application;[menu addItem:group];NSApp.mainMenu=menu;
 [self buildWindow];[self.window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];[self refresh:nil];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender{(void)sender;return YES;}
@end
