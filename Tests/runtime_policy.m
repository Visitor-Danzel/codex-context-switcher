#import <Foundation/Foundation.h>
#import "CodexContextCore.h"
int main(int argc,const char **argv){@autoreleasepool{
 if(argc!=2)return 2;
 NSString *p=[CCBoundedProcess sandboxPolicyForExecutableURL:[NSURL fileURLWithPath:@"/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"] isolatedHomeURL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]]];
 if(!p)return 1;printf("%s",p.UTF8String);return 0;
}}
