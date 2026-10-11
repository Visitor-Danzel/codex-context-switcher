#import <Foundation/Foundation.h>
#import "CodexContextCore.h"
#import <sys/stat.h>
static int failures=0,checks=0;
#define CHECK(c,m) do { checks++; if(!(c)){ failures++; fprintf(stderr,"FAIL: %s\n",m); } } while(0)
static NSURL *Dir(void){ NSURL *p=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]]; [NSFileManager.defaultManager createDirectoryAtURL:p withIntermediateDirectories:YES attributes:nil error:nil]; return p; }
static void Write(NSURL *p,NSString *s){ [NSFileManager.defaultManager createDirectoryAtURL:p.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil]; [s writeToURL:p atomically:YES encoding:NSUTF8StringEncoding error:nil]; chmod(p.fileSystemRepresentation,0700); }
int main(void){ @autoreleasepool {
 Class cls=CCRuntimeResolver.class; SEL resolve=NSSelectorFromString(@"desktopExecutableForResourcesURL:error:"); SEL version=NSSelectorFromString(@"versionFromOutput:");
 CHECK([cls respondsToSelector:resolve],"desktop package resolver exists");
 CHECK([cls respondsToSelector:version],"strict prerelease version parser exists");
 if([cls respondsToSelector:resolve]) {
  NSURL *r=Dir(); NSURL *native=[r URLByAppendingPathComponent:@"codex-cli/CodexCLI.app/Contents/MacOS/codex"];
  Write(native,@"#!/bin/sh\nexit 0\n"); Write([r URLByAppendingPathComponent:@"codex-cli/bin/codex"],@"#!/bin/sh\nexit 0\n");
  NSString *manifest=@"{\"layoutVersion\":1,\"version\":\"0.162.0-alpha.17.2\",\"target\":\"aarch64-apple-darwin\",\"variant\":\"codex\",\"entrypoint\":\"bin/codex\"}";
  NSURL *meta=[r URLByAppendingPathComponent:@"codex-cli/codex-package.json"]; Write(meta,manifest);
  id (*fn)(id,SEL,id,id)=(void *)[cls methodForSelector:resolve];
  CHECK([[fn(cls,resolve,r,nil) path] isEqual:native.path],"current package resolves native binary instead of shell launcher");
  Write(meta,@"{\"layoutVersion\":9}"); CHECK(fn(cls,resolve,r,nil)==nil,"unknown package layout refuses unsafe guesses");
  Write(meta,manifest); [NSFileManager.defaultManager removeItemAtURL:native error:nil];
  CHECK(fn(cls,resolve,r,nil)==nil,"missing native binary does not fall back to launcher");
  Write(native,@"#!/bin/sh\nexit 0\n"); [NSFileManager.defaultManager removeItemAtURL:native error:nil];
  [NSFileManager.defaultManager createSymbolicLinkAtURL:native withDestinationURL:[NSURL fileURLWithPath:@"/bin/sh"] error:nil];
  CHECK(fn(cls,resolve,r,nil)==nil,"native symlink outside package rejected");
  [NSFileManager.defaultManager removeItemAtURL:r error:nil];
  NSURL *legacy=Dir(); Write([legacy URLByAppendingPathComponent:@"codex"],@"#!/bin/sh\nexit 0\n");
  CHECK(fn(cls,resolve,legacy,nil)!=nil,"previous desktop layout remains supported");
  [NSFileManager.defaultManager removeItemAtURL:legacy error:nil];
 }
 if([cls respondsToSelector:version]) {
  id (*fn)(id,SEL,id)=(void *)[cls methodForSelector:version];
  CHECK([fn(cls,version,@"codex-cli 0.162.0-alpha.17.2\n") isEqual:@"0.162.0-alpha.17.2"],"current alpha version retained exactly");
  CHECK([fn(cls,version,@"codex 0.153.4\n") isEqual:@"0.153.4"],"release version remains supported");
  CHECK(fn(cls,version,@"codex-cli 0.162.0-alpha.17.2\nextra\n")==nil,"multiple lines cannot masquerade as version");
  CHECK(fn(cls,version,@"codex-cli 0.162.0-\n")==nil,"empty prerelease rejected");
 }
 Class process=CCBoundedProcess.class; SEL policy=NSSelectorFromString(@"sandboxPolicyForExecutableURL:isolatedHomeURL:");
 CHECK([process respondsToSelector:policy],"official CLI probe requires isolation policy");
 if([process respondsToSelector:policy]) {
  id (*fn)(id,SEL,id,id)=(void *)[process methodForSelector:policy]; NSURL *home=Dir();
  NSURL *official=[NSURL fileURLWithPath:@"/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"];
  CHECK(fn(process,policy,official,home)!=nil,"temporary HOME supports restricted official probe");
  CHECK(fn(process,policy,official,[NSURL fileURLWithPath:NSHomeDirectory()])==nil,"real HOME refused before executing official CLI");
  [NSFileManager.defaultManager removeItemAtURL:home error:nil];
 }
 printf("%s: %d runtime repair checks\n",failures?"FAILED":"PASS",checks); return failures?1:0;
}}
