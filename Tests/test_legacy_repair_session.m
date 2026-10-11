#import <Foundation/Foundation.h>
#import "CodexContextCore.h"
#import "ContextRepairSession.h"
static int failures=0,checks=0;
#define CHECK(c,m) do { checks++; if(!(c)){ failures++; fprintf(stderr,"FAIL: %s\n",m); } } while(0)
int main(void){ @autoreleasepool {
 Class cls=NSClassFromString(@"CCRepairSession"); SEL root=NSSelectorFromString(@"isIsolatedTestRoot:");
 CHECK(cls && [cls respondsToSelector:root],"session enforces isolated write root");
 if(cls && [cls respondsToSelector:root]) {
  BOOL (*fn)(id,SEL,id)=(void *)[cls methodForSelector:root];
  NSString *r=[@"/private/tmp/legacy-context-repair-" stringByAppendingString:NSUUID.UUID.UUIDString];
  [NSFileManager.defaultManager createDirectoryAtPath:r withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil];
  CHECK(fn(cls,root,r),"existing isolated root allowed");
  CHECK(!fn(cls,root,@"/private/tmp"),"whole temp directory is never writable target");
  CHECK(!fn(cls,root,[NSHomeDirectory() stringByAppendingPathComponent:@".codex"]),"real Codex directory cannot be a test target");
  NSString *link=[@"/private/tmp/legacy-context-repair-" stringByAppendingString:NSUUID.UUID.UUIDString];
  [NSFileManager.defaultManager createSymbolicLinkAtPath:link withDestinationPath:r error:nil];
  CHECK(!fn(cls,root,link),"directory symlink rejected before test writes");
  [NSFileManager.defaultManager removeItemAtPath:link error:nil];
  NSString *state=[r stringByAppendingPathComponent:@"state.json"];
  [NSFileManager.defaultManager createSymbolicLinkAtPath:state withDestinationPath:@"/does-not-exist/native-history" error:nil];
  CHECK(!fn(cls,root,r),"input symlink rejected before state reads or writes");
  [NSFileManager.defaultManager removeItemAtPath:r error:nil];
 }
 NSString *bad=[@"/private/tmp/legacy-context-repair-" stringByAppendingString:NSUUID.UUID.UUIDString];
 [NSFileManager.defaultManager createDirectoryAtPath:bad withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil];
 NSURL *binary=[NSURL fileURLWithPath:NSProcessInfo.processInfo.arguments[0]];
 NSURL *resources=[binary.URLByDeletingLastPathComponent.URLByDeletingLastPathComponent URLByAppendingPathComponent:@"Codex Context Switcher.app/Contents/Resources"];
 CCRepairSession *unexpected=[[CCRepairSession alloc] initWithResourcesURL:resources settingsURL:[NSURL fileURLWithPath:bad] isolated:NO error:nil];
 CHECK(!unexpected,"normal candidate cannot read an arbitrary settings root");
 [NSFileManager.defaultManager removeItemAtPath:bad error:nil];
 printf("%s: %d isolation checks\n",failures?"FAILED":"PASS",checks); return failures?1:0;
}}
