#define main CCRepairMainForTests
#import "../Sources/CodexContextSwitcherApp/RepairCandidate.h"
#undef main
int main(int argc,const char **argv){@autoreleasepool{
 if(argc!=3)return 2;
 NSString *policy=MaximumPolicy(@"/usr/local/bin/python3",[NSString stringWithUTF8String:argv[1]],[NSString stringWithUTF8String:argv[2]]);
 if(!policy)return 1;printf("%s",policy.UTF8String);return 0;
}}
