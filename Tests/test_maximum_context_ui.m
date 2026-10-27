#define main CCRepairMainForTests
#import "../Sources/CodexContextSwitcherApp/RepairCandidate.h"
#undef main
// A language change must never enter inspection or configuration operations.
@interface CCLanguageTestDelegate : CCMaximumContextDelegate
@property(nonatomic) NSUInteger unexpectedOperations;
@end
@implementation CCLanguageTestDelegate
- (void)refresh:(id)sender {(void)sender;self.unexpectedOperations++;}
- (void)prepare:(NSString *)action {(void)action;self.unexpectedOperations++;}
@end
static int failures=0,checks=0;
#define CHECK(c,m) do{checks++;if(!(c)){failures++;fprintf(stderr,"FAIL: %s\n",m);}}while(0)
int main(void){@autoreleasepool{
 [NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
 NSApp.appearance=[NSAppearance appearanceNamed:NSAppearanceNameAqua];
 Class cls=NSClassFromString(@"CCMaximumContextDelegate");
 CHECK(cls!=nil,"Missing functional maximum-context window");
 if(cls){
  id d=[CCLanguageTestDelegate new];[d performSelector:NSSelectorFromString(@"buildWindow")];
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
  SEL languageAction=NSSelectorFromString(@"changeLanguage:");
  CHECK([d respondsToSelector:languageAction],"English display option is available");
  if([d respondsToSelector:languageAction]){
   NSPopUpButton *picker=[d valueForKey:@"languagePicker"];
   CHECK(picker.numberOfItems==2 && picker.indexOfSelectedItem==0,"Chinese stays the default with one English option");
   NSSet *draft=[[d valueForKey:@"selection"] copy];
   id statusIdentity=[d valueForKey:@"status"];
   NSArray *sameButtons=[[d valueForKey:@"modelButtons"] copy];
   NSPoint scrollPosition=[[[d valueForKey:@"scroll"] contentView] bounds].origin;
   for(NSInteger i=0;i<4;i++){
    BOOL english=i%2==0;[picker selectItemAtIndex:english?1:0];[d performSelector:languageAction withObject:picker];
    CHECK([[d valueForKey:@"selection"] isEqual:draft] && [d valueForKey:@"status"]==statusIdentity,"language change preserves unsaved selection and configuration snapshot");
    CHECK([[d valueForKey:@"modelButtons"] isEqual:sameButtons],"language only relabels existing model controls");
    CHECK(NSEqualPoints(scrollPosition,[[[d valueForKey:@"scroll"] contentView] bounds].origin),"language preserves model list position");
    CHECK([[d valueForKey:@"saveButton"] isEnabled] && [[d valueForKey:@"undoButton"] isEnabled] && ![sameButtons[2] isEnabled],"language preserves saving, undo and fixed-model availability");
    CHECK([sameButtons[0] state]==NSControlStateValueOn && [sameButtons[1] state]==NSControlStateValueOn,"language never changes checked models");
    CHECK([[[d valueForKey:@"summaryLabel"] stringValue] containsString:english?@"Unsaved":@"未保存"],"unsaved status follows the selected display language");
   }
   [picker selectItemAtIndex:1];[d performSelector:languageAction withObject:picker];
   CHECK([[[d valueForKey:@"saveButton"] title] isEqual:@"Save"] && [[sameButtons[1] title] isEqual:@"Use maximum"],"English labels are visible on action and model buttons");
   for(NSString *key in @[@"saveButton",@"defaultsButton",@"undoButton",@"refreshButton"]){
    NSButton *b=[d valueForKey:key];if(b.cell.cellSize.width>b.frame.size.width)fprintf(stderr,"Clipped: %s, needed %.1f, available %.1f\n",b.title.UTF8String,b.cell.cellSize.width,b.frame.size.width);CHECK(b.cell.cellSize.width<=b.frame.size.width,"English action labels fit without clipping");
   }
   [d performSelector:NSSelectorFromString(@"setSummary:") withObject:@"已保存。重新打开 Codex，在新聊天中使用。"];
   [picker selectItemAtIndex:0];[d performSelector:languageAction withObject:picker];
   CHECK([[[d valueForKey:@"summaryLabel"] stringValue] hasPrefix:@"已保存"],"language preserves a completed-save message");
   [d performSelector:NSSelectorFromString(@"setSummary:") withObject:MaximumReason(@"desktop_check_unavailable")];
   [picker selectItemAtIndex:1];[d performSelector:languageAction withObject:picker];
   CHECK([[[d valueForKey:@"summaryLabel"] stringValue] containsString:@"cannot confirm"],"language preserves and translates process-query errors");
   NSButton *englishSecond=sameButtons[1];englishSecond.state=NSControlStateValueOff;
   [d performSelector:NSSelectorFromString(@"toggleModel:") withObject:englishSecond];
   CHECK([sameButtons[0] isEnabled] && [sameButtons[1] isEnabled] && ![sameButtons[2] isEnabled],"English tooltips do not break model eligibility after toggling");
   [d setValue:@YES forKey:@"busy"];[d performSelector:NSSelectorFromString(@"updateControls")];
   [picker selectItemAtIndex:0];[d performSelector:languageAction withObject:picker];
   CHECK([[d valueForKey:@"busy"] boolValue] && ![[d valueForKey:@"saveButton"] isEnabled] && ![sameButtons[0] isEnabled],"language preserves a busy operation and disabled controls");
   CHECK([(CCLanguageTestDelegate *)d unexpectedOperations]==0,"language never starts a refresh, preview or save");
   [d setValue:@NO forKey:@"busy"];
  }
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:status];
  CHECK(![[d valueForKey:@"saveButton"] isEnabled],"unchanged configuration not re-saved");
  CHECK([[d valueForKey:@"undoButton"] isEnabled],"previous real save can be manually undone");
  NSMutableDictionary *outdated=[status mutableCopy];outdated[@"state"]=@"catalog_outdated";
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:outdated];
  CHECK([[d valueForKey:@"saveButton"] isEnabled],"outdated trusted catalog can migrate without changing its selection");
  CHECK([[d valueForKey:@"defaultsButton"] isEnabled],"outdated trusted catalog can restore defaults");
  CHECK([[[d valueForKey:@"summaryLabel"] stringValue] containsString:@"模型清单需要更新"],"normal upgrade is not described as damage");
  CHECK([[[d valueForKey:@"modelButtons"] objectAtIndex:0] state]==NSControlStateValueOn,"upgrade keeps the prior checked model");
  NSMutableDictionary *paused=[outdated mutableCopy];paused[@"catalog_route_paused"]=@YES;
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:paused];
  CHECK(![[d valueForKey:@"saveButton"] isEnabled],"production catalog writes are paused");
  CHECK(![[[d valueForKey:@"modelButtons"] objectAtIndex:0] isEnabled],"production cannot draft another catalog override");
  CHECK([[d valueForKey:@"defaultsButton"] isEnabled],"explicit withdrawal remains available");
  CHECK(![[d valueForKey:@"undoButton"] isEnabled],"undo cannot reinstall the paused model list");
  CHECK([[[d valueForKey:@"summaryLabel"] stringValue] containsString:@"接管原生模型列表"],"native-list side effect is plainly disclosed");
  NSMutableDictionary *updated=[status mutableCopy];updated[@"runtime_compatible"]=@NO;
  [d performSelector:NSSelectorFromString(@"acceptStatus:") withObject:updated];
  CHECK(![[d valueForKey:@"saveButton"] isEnabled],"Codex update blocks stale catalog writes");
  CHECK([[d valueForKey:@"undoButton"] isEnabled],"update does not strand manual undo");
  [window close];
 }
 printf("%s: %d maximum-context UI checks\n",failures?"FAILED":"PASS",checks);return failures?1:0;
}}
