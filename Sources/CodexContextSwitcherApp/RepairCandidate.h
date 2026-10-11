#import <Cocoa/Cocoa.h>
#import "ContextRepairSession.h"
#import "MonitorSandbox.h"
#import "MaximumContext.h"
static CCRepairSession *RepairSession;
static NSString *RepairRoot;
static NSError *RepairError;
static NSString *RepairQuote(NSString *s){return CCMonitorSandboxLiteral(s);}
static NSDictionary *RepairActivation(void) {
 NSURL *resources=NSBundle.mainBundle.resourceURL;
 NSString *worker=[resources URLByAppendingPathComponent:@"legacy_context_readout.py"].path;
 NSString *base=RepairRoot ?: [NSHomeDirectory() stringByAppendingPathComponent:@".codex"];
 NSString *config=[base stringByAppendingPathComponent:@"config.toml"];
 NSString *catalog=RepairSession.store.customCatalogURL.path;
 NSString *python=nil;
 for(NSString *p in @[@"/usr/local/bin/python3",@"/opt/homebrew/bin/python3"])
  if([NSFileManager.defaultManager isExecutableFileAtPath:p]){python=p;break;}
 if(!python||!catalog)return @{@"activation":@"unknown",@"chat_verified":@NO};
 NSString *policy=[NSString stringWithFormat:@"(version 1) (deny default) (allow process*) (allow sysctl-read) (allow file-read-metadata) (allow file-read* (literal \"/\") (subpath \"/System\") (subpath \"/usr/lib\") (subpath \"/usr/bin\") (subpath \"/bin\") (subpath \"/Library/Apple\") (subpath \"/Library/Frameworks/Python.framework\") (literal \"/dev/null\") (literal \"/dev/urandom\") (literal %@) (literal %@) (literal %@) (literal %@) (literal %@)) (deny file-read* (subpath \"/Library/Keychains\") (subpath \"/System/Library/Keychains\")) (deny network*)",RepairQuote(python),RepairQuote(worker),RepairQuote(config),RepairQuote(catalog),RepairQuote(RepairSession.catalogURL.path)];
 NSURL *home=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
 if(![NSFileManager.defaultManager createDirectoryAtURL:home withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil])return @{@"activation":@"unknown",@"chat_verified":@NO};
 NSDictionary *p=[CCBoundedProcess runExecutableURL:[NSURL fileURLWithPath:@"/usr/bin/sandbox-exec"] arguments:@[@"-p",policy,python,@"-I",@"-S",@"-B",worker,config,catalog,RepairSession.catalogURL.path] isolatedHomeURL:home timeout:5 outputLimit:16384 error:nil];
 [NSFileManager.defaultManager removeItemAtURL:home error:nil];
 NSDictionary *r=p?[NSJSONSerialization JSONObjectWithData:p[@"stdout"] options:0 error:nil]:nil;
 return [r isKindOfClass:NSDictionary.class]?r:@{@"activation":@"unknown",@"chat_verified":@NO};
}
static BOOL RepairInitialize(NSString *root) {
 RepairRoot=root;
 if(root && ![CCRepairSession isIsolatedTestRoot:root]) {fprintf(stderr,"Unsafe isolated test root; nothing accessed.\n");return NO;}
 NSString *settings=root ?: [NSHomeDirectory() stringByAppendingPathComponent:@".codex/context-switcher"];
 NSError *error=nil;
 RepairSession=[[CCRepairSession alloc] initWithResourcesURL:NSBundle.mainBundle.resourceURL settingsURL:[NSURL fileURLWithPath:settings] isolated:root!=nil error:&error];
 RepairError=error;
 return RepairSession!=nil;
}
static int RepairProbe(BOOL models) {
 NSURL *cli=[CCRuntimeResolver desktopExecutableForResourcesURL:[NSURL fileURLWithPath:@"/Applications/ChatGPT.app/Contents/Resources"] error:nil];
 NSURL *home=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];
 if(!cli||![NSFileManager.defaultManager createDirectoryAtURL:home withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil])return 1;
 NSDictionary *p=[CCBoundedProcess runExecutableURL:cli arguments:models?@[@"debug",@"models",@"--bundled"]:@[@"--version"] isolatedHomeURL:home timeout:15 outputLimit:16*1024*1024 error:nil];
 [NSFileManager.defaultManager removeItemAtURL:home error:nil];
 if(!p)return 1;
 if(models) {if(![CCCodexCatalogProbe isValidCatalogData:p[@"stdout"]])return 1; fwrite([p[@"stdout"] bytes],1,[p[@"stdout"] length],stdout);}
 else {NSString *s=[[NSString alloc] initWithData:p[@"stdout"] encoding:NSUTF8StringEncoding];NSString *v=[CCRuntimeResolver versionFromOutput:s];if(!v)return 1;printf("%s\n",v.UTF8String);}
 return 0;
}
@interface CCRepairDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic) NSStatusItem *item;
@property(nonatomic) NSDictionary *activation;
@property(nonatomic) BOOL busy;
- (NSMenu *)menu;
@end
@implementation CCRepairDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)n {
 (void)n; self.item=[[NSStatusBar systemStatusBar] statusItemWithLength:NSSquareStatusItemLength];
 NSImage *image=[NSImage imageWithSystemSymbolName:@"rectangle.stack.badge.plus" accessibilityDescription:@"逐模型最大上下文候选版"];image.template=YES;self.item.button.image=image;
 self.item.menu=[self menu]; [self refresh:nil];
}
- (NSMenuItem *)label:(NSString *)s {NSMenuItem *i=[[NSMenuItem alloc] initWithTitle:s action:nil keyEquivalent:@""];i.enabled=NO;return i;}
- (NSMenuItem *)action:(NSString *)s selector:(SEL)a {NSMenuItem *i=[[NSMenuItem alloc] initWithTitle:s action:a keyEquivalent:@""];i.target=self;return i;}
- (NSMenu *)menu {
 NSMenu *m=[NSMenu new];m.autoenablesItems=NO;
 [m addItem:[self label:@"逐模型最大上下文 · 候选版"]];
 if(RepairError)[m addItem:[self label:RepairError.localizedDescription]];
 NSString *key=self.activation[@"activation"] ?: @"unknown";
 NSDictionary *labels=@{@"not_configured":@"根配置：未启用旧工具清单",@"configured":@"根配置：已启用当前完整清单",@"stale_catalog":@"根配置：引用了过时清单",@"other_catalog":@"根配置：使用其他清单",@"override_unverified":@"根配置：存在覆盖，启用情况未确认",@"unknown":@"根配置：启用情况未确认"};
 [m addItem:[self label:labels[key] ?: labels[@"unknown"]]];
 [m addItem:[self label:@"聊天实际生效：未确认"]];
 NSInteger saved=0; for(CCModelContextOption *o in RepairSession.options)if(o.extended)saved++;
 [m addItem:[self label:[NSString stringWithFormat:@"已保存 %ld 个扩展选择；勾选表示已保存",(long)saved]]];
 [m addItem:[NSMenuItem separatorItem]];
 NSMenuItem *group=[self action:@"逐模型选择" selector:nil]; NSMenu *models=[NSMenu new];models.autoenablesItems=NO;
 for(CCModelContextOption *o in RepairSession.options) {
  NSNumber *configured=self.activation[@"contexts"][o.slug];
  NSString *actual=@"配置未确认";
  if([key isEqual:@"configured"] && [configured isKindOfClass:NSNumber.class]) {
   actual=configured.integerValue==o.maximumContext && o.maximumContext>o.defaultContext ? @"配置最大" : @"配置默认";
  }
  NSMenuItem *i=[self action:[NSString stringWithFormat:@"%@ · 保存%@ / %@",o.displayName,o.extended?@"最大":@"默认",actual] selector:@selector(toggle:)];
  i.toolTip=[NSString stringWithFormat:@"默认 %@；最大 %@。配置状态只代表读取时的根配置，聊天实际生效未确认。",@(o.defaultContext),@(o.maximumContext)];
  i.representedObject=o.slug;i.state=o.extended?NSControlStateValueOn:NSControlStateValueOff;i.enabled=RepairSession.isolated&&o.canExtend&&!self.busy;[models addItem:i];
 }
 group.submenu=models;[m addItem:group];
 NSMenuItem *restore=[self action:@"恢复默认上下文" selector:@selector(restore:)];restore.enabled=RepairSession.isolated&&!self.busy;[m addItem:restore];
 NSMenuItem *undo=[self action:@"撤销上次选择" selector:@selector(undo:)];undo.enabled=RepairSession.isolated&&!self.busy;[m addItem:undo];
 [m addItem:[self label:RepairSession.isolated?@"仅操作隔离测试资料":@"候选版不写真实配置；真实开关接入待验收"]];
 [m addItem:[self action:@"刷新状态" selector:@selector(refresh:)]];
 [m addItem:[NSMenuItem separatorItem]];[m addItem:[self action:@"退出" selector:@selector(quit:)]];return m;
}
- (void)refresh:(id)sender {
 (void)sender;if(self.busy)return;self.busy=YES;
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSError *error=nil;[RepairSession reload:&error];NSDictionary *a=RepairActivation();dispatch_async(dispatch_get_main_queue(),^{RepairError=error;self.activation=a;self.busy=NO;self.item.menu=[self menu];});});
}
- (void)save:(NSSet *)selection undo:(BOOL)undo {
 if(self.busy||!RepairSession.isolated)return; self.busy=YES;self.item.menu=[self menu];
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSError *error=nil;BOOL ok=undo?[RepairSession undo:&error]:[RepairSession applySelection:selection error:&error];dispatch_async(dispatch_get_main_queue(),^{self.busy=NO;RepairError=error;if(!ok){NSAlert *a=[NSAlert new];a.messageText=@"隔离测试保存未成功";a.informativeText=error.localizedDescription ?: @"未知错误";[a runModal];}self.item.menu=[self menu];});});
}
- (void)toggle:(NSMenuItem *)item {
 NSMutableSet *s=[NSMutableSet new];for(CCModelContextOption *o in RepairSession.options)if(o.extended)[s addObject:o.slug];
 [self save:[CCContextSelection slugsByTogglingSlug:item.representedObject inExtendedSlugs:s] undo:NO];
}
- (void)restore:(id)s {(void)s;[self save:[NSSet set] undo:NO];}
- (void)undo:(id)s {(void)s;[self save:nil undo:YES];}
- (void)quit:(id)s {(void)s;[NSApp terminate:nil];}
@end
int main(int argc,const char **argv) { @autoreleasepool {
 if(argc==2 && strcmp(argv[1],"--emit-catalog")==0)return RepairProbe(YES);
 if(argc==2 && strcmp(argv[1],"--client-version")==0)return RepairProbe(NO);
 int index=1;NSString *root=nil;
 if(argc>=3 && strcmp(argv[1],"--test-root")==0){root=[NSString stringWithUTF8String:argv[2]];index=3;}
 NSString *command=index<argc?[NSString stringWithUTF8String:argv[index]]:nil;
 if([command isEqual:@"--settings-request"] || [command isEqual:@"--settings-status"] || (!root&&[command isEqual:@"--status"])) {
  BOOL request=[command isEqual:@"--settings-request"];
  if(argc!=index+(request?2:1) || (request&&!root) || (root&&![CCRepairSession isIsolatedTestRoot:root]))return 2;
  MaximumTestRoot=root;NSDictionary *input=@{@"operation":@"inspect"};
  if(request){NSData *data=[[NSString stringWithUTF8String:argv[index+1]] dataUsingEncoding:NSUTF8StringEncoding];input=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];if(![input isKindOfClass:NSDictionary.class])return 2;}
  NSDictionary *reply=MaximumCall(input);NSData *raw=[NSJSONSerialization dataWithJSONObject:reply options:NSJSONWritingSortedKeys error:nil];fwrite(raw.bytes,1,raw.length,stdout);printf("\n");return [reply[@"ok"] boolValue]?0:1;
 }
 if(!command) {
  if(root&&![CCRepairSession isIsolatedTestRoot:root])return 2;
  MaximumTestRoot=root;NSApplication *app=NSApplication.sharedApplication;CCMaximumContextDelegate *delegate=[CCMaximumContextDelegate new];app.delegate=delegate;[app setActivationPolicy:NSApplicationActivationPolicyRegular];[app run];return 0;
 }
 BOOL status=[command isEqual:@"--status"], toggle=[command isEqual:@"--toggle"], restore=[command isEqual:@"--restore-all"], undo=[command isEqual:@"--undo"];
 if(command && (!status&&!toggle&&!restore&&!undo)) {fprintf(stderr,"Unsupported command; no settings accessed.\n");return 2;}
 if(command && argc!=index+(toggle?2:1)){fprintf(stderr,"Invalid arguments; no settings accessed.\n");return 2;}
 if(command&&!status&&!root){fprintf(stderr,"Real configuration writes are disabled in this candidate.\n");return 2;}
 if(!RepairInitialize(root)){fprintf(stderr,"Candidate initialization failed; no write.\n");return 1;}
 if(command) {
  NSError *error=nil;BOOL ok=YES;
  if(toggle){NSMutableSet *s=[NSMutableSet new];for(CCModelContextOption *o in RepairSession.options)if(o.extended)[s addObject:o.slug];ok=[RepairSession applySelection:[CCContextSelection slugsByTogglingSlug:[NSString stringWithUTF8String:argv[index+1]] inExtendedSlugs:s] error:&error];}
  if(restore)ok=[RepairSession applySelection:[NSSet set] error:&error];if(undo)ok=[RepairSession undo:&error];
  if(!ok){fprintf(stderr,"Isolated selection failed: %s\n",error.localizedDescription.UTF8String);return 1;}
  NSMutableDictionary *r=[[RepairSession status] mutableCopy];r[@"configuration"]=RepairActivation();NSData *d=[NSJSONSerialization dataWithJSONObject:r options:NSJSONWritingSortedKeys error:nil];fwrite(d.bytes,1,d.length,stdout);printf("\n");return 0;
 }
 NSApplication *app=NSApplication.sharedApplication; CCRepairDelegate *delegate=[CCRepairDelegate new];app.delegate=delegate;[app setActivationPolicy:NSApplicationActivationPolicyAccessory];[app run];return 0;
}}
