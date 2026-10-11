#define main CCRepairMainForTests
#import "../Sources/CodexContextSwitcherApp/RepairCandidate.h"
#undef main
static int failures=0,checks=0;
#define CHECK(c,m) do{checks++;if(!(c)){failures++;fprintf(stderr,"FAIL: %s\n",m);}}while(0)
int main(void){@autoreleasepool{
 [NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
 NSApp.appearance=[NSAppearance appearanceNamed:NSAppearanceNameAqua];
 Class cls=NSClassFromString(@"CCMaximumContextDelegate");
 CHECK(cls!=nil,"Missing functional maximum-context window");
 if(cls){
  id d=[cls new];[d performSelector:NSSelectorFromString(@"buildWindow")];
  NSWindow *window=[d valueForKey:@"window"];
  CHECK(window!=nil,"maximum context has one understandable window");
  NSDictionary *status=@{@"state":@"configured",@"selected":@[@"a"],@"runtime_compatible":@YES,
   @"configuration_conflict":@NO,@"undo_available":@YES,@"transaction_state":@"saved",
   @"models":@[@{@"slug":@"a",@"name":@"Model A",@"default":@100,@"maximum":@400,@"can_extend":@YES},
               @{@"slug":@"b",@"name":@"Model B",@"default":@200,@"maximum":@500,@"can_extend":@YES},
               @{@"slug":@"fixed",@"name":@"Fixed",@"default":@200,@"maximum":@200,@"can_extend":@NO}]};
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:status];
  NSArray *buttons=[d valueForKey:@"modelButtons"];
  CHECK(buttons.count==3,"full model list preserved");
  CHECK([buttons[0] state]==NSControlStateValueOn,"selection initialized from real configuration");
  CHECK([buttons[1] state]==NSControlStateValueOff,"another model separately defaults");
  CHECK(![buttons[2] isEnabled],"unextendable model cannot be switched");
  NSButton *second=buttons[1];second.state=NSControlStateValueOn;
  [d performSelector:NSSelectorFromString(@"toggleModel:") withObject:second];
  CHECK(([[d valueForKey:@"selection"] isEqual:[NSSet setWithArray:@[@"a",@"b"]]]),"toggle drafts only the requested model");
  CHECK([[d valueForKey:@"saveButton"] isEnabled],"changed selection enables actual save");
  CHECK([[[d valueForKey:@"summaryLabel"] stringValue] containsString:@"未保存"],"draft is visibly distinct from saved settings");
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:status];
  CHECK(![[d valueForKey:@"saveButton"] isEnabled],"unchanged configuration not re-saved");
  CHECK([[d valueForKey:@"undoButton"] isEnabled],"previous real save can be manually undone");
  NSMutableDictionary *updated=[status mutableCopy];updated[@"runtime_compatible"]=@NO;
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:updated];
  CHECK(![[d valueForKey:@"saveButton"] isEnabled],"Codex update blocks stale catalog writes");
  CHECK([[d valueForKey:@"undoButton"] isEnabled],"update does not strand manual undo");
  [window close];
 }
 printf("%s: %d maximum-context UI checks\n",failures?"FAILED":"PASS",checks);return failures?1:0;
}}
