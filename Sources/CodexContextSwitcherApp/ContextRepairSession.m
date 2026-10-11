#import "ContextRepairSession.h"
#import <CommonCrypto/CommonDigest.h>
#import <sys/stat.h>
#import <fcntl.h>
#import <unistd.h>
static BOOL RepairFail(NSError **error,NSString *message) {
 if(error)*error=[NSError errorWithDomain:@"CodexContextRepair" code:1 userInfo:@{NSLocalizedDescriptionKey:message}]; return NO;
}
static NSString *RepairHash(NSURL *url) {
 int fd=open(url.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK); if(fd<0)return nil;
 struct stat before,after; if(fstat(fd,&before)||!S_ISREG(before.st_mode)||before.st_size>1024LL*1024*1024){close(fd);return nil;}
 CC_SHA256_CTX ctx; CC_SHA256_Init(&ctx); unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH]; ssize_t n;
 while((n=read(fd,buf,sizeof(buf)))>0) CC_SHA256_Update(&ctx,buf,(CC_LONG)n);
 BOOL stable=n==0&&!fstat(fd,&after)&&before.st_ino==after.st_ino&&before.st_size==after.st_size&&before.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec&&before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec&&before.st_ctimespec.tv_sec==after.st_ctimespec.tv_sec&&before.st_ctimespec.tv_nsec==after.st_ctimespec.tv_nsec;
 close(fd); if(!stable)return nil; CC_SHA256_Final(digest,&ctx); NSMutableString *s=[NSMutableString new]; for(NSUInteger i=0;i<sizeof(digest);i++)[s appendFormat:@"%02x",digest[i]]; return s;
}
static BOOL RepairSafeFiles(NSString *path) {
 for(NSString *name in @[@"state.json",@"models-custom.json",@"runtime.json",@"pending-transaction.json",@"transaction.lock"]) {
  struct stat st; NSString *p=[path stringByAppendingPathComponent:name];
  int result=lstat(p.fileSystemRepresentation,&st);
  if(result==0 && (!S_ISREG(st.st_mode)||st.st_size>16*1024*1024||st.st_nlink!=1))return NO;
  if(result!=0 && errno!=ENOENT)return NO;
 } return YES;
}
@interface CCRepairSession ()
@property(nonatomic,readwrite) CCContextStore *store;
@property(nonatomic,readwrite) NSArray<CCModelContextOption *> *options;
@property(nonatomic,readwrite) BOOL isolated;
@property(nonatomic,readwrite) BOOL runtimeCompatible;
@property(nonatomic,readwrite) NSURL *executableURL;
@property(nonatomic,readwrite) NSURL *catalogURL;
@property(nonatomic,readwrite) NSString *clientVersion;
@property(nonatomic) NSDictionary *record;
@end
@implementation CCRepairSession
+ (BOOL)isIsolatedTestRoot:(NSString *)path {
 if(![path isKindOfClass:NSString.class]||![path hasPrefix:@"/private/tmp/legacy-context-repair-"]||[path containsString:@"/../"])return NO;
 char *canonical=realpath(path.fileSystemRepresentation,NULL); if(!canonical)return NO;
 BOOL same=[path isEqual:[NSString stringWithUTF8String:canonical]]; free(canonical); struct stat st;
 if(!same||lstat(path.fileSystemRepresentation,&st)||!S_ISDIR(st.st_mode)||st.st_uid!=getuid()||(st.st_mode&0777)!=0700)return NO;
 return RepairSafeFiles(path);
}
- (instancetype)initWithResourcesURL:(NSURL *)resources settingsURL:(NSURL *)settings isolated:(BOOL)isolated error:(NSError **)error {
 if(!(self=[super init]))return nil;
 if(!isolated) {
  NSString *expected=[NSHomeDirectory() stringByAppendingPathComponent:@".codex/context-switcher"];
  struct stat st;
  if(![settings.path isEqual:expected] || (lstat(settings.fileSystemRepresentation,&st)==0 && !S_ISDIR(st.st_mode))) {
   RepairFail(error,@"只读候选版只读取既有上下文设置目录。");return nil;
  }
 }
 if(isolated && ![CCRepairSession isIsolatedTestRoot:settings.path]){RepairFail(error,@"测试目录不安全；不会访问设置。");return nil;}
 if(!RepairSafeFiles(settings.path)){RepairFail(error,@"旧设置文件不安全；停止读取。");return nil;}
 _isolated=isolated; _catalogURL=[resources URLByAppendingPathComponent:@"current-models.json"];
 NSData *raw=[NSData dataWithContentsOfURL:[resources URLByAppendingPathComponent:@"catalog-record.json"]];
 _record=raw?[NSJSONSerialization JSONObjectWithData:raw options:0 error:nil]:nil;
 if(![_record isKindOfClass:NSDictionary.class]){RepairFail(error,@"候选目录证据缺失。");return nil;}
 _clientVersion=_record[@"cli_version"];
 _executableURL=[CCRuntimeResolver desktopExecutableForResourcesURL:[NSURL fileURLWithPath:@"/Applications/ChatGPT.app/Contents/Resources"] error:error];
 if(!_executableURL)return nil;
 _store=[[CCContextStore alloc] initWithSourceCatalogURL:_catalogURL templateCatalogURL:_catalogURL settingsDirectoryURL:settings];
 _store.validationExecutableURL=_executableURL;
 if(![self reload:error])return nil; return self;
}
- (BOOL)reload:(NSError **)error {
 if(self.isolated && ![CCRepairSession isIsolatedTestRoot:self.store.settingsDirectoryURL.path])return RepairFail(error,@"测试目录发生变化；已停止。");
 if(!RepairSafeFiles(self.store.settingsDirectoryURL.path))return RepairFail(error,@"设置发生不安全变化；停止读取。");
 self.runtimeCompatible=[RepairHash(self.executableURL) isEqual:self.record[@"native_sha256"]] && [RepairHash(self.catalogURL) isEqual:self.record[@"catalog_sha256"]];
 if(!self.runtimeCompatible) { self.options=@[]; return RepairFail(error,@"Codex 或模型清单已更新；需要重新验证，不能使用旧目录。"); }
 NSArray *options=[self.store loadOptions:error]; if(!options)return NO; self.options=options; return YES;
}
- (BOOL)applySelection:(NSSet<NSString *> *)selection error:(NSError **)error {
 if(!self.isolated)return RepairFail(error,@"候选版仅允许隔离测试保存；真实配置尚未接入。");
 if(![self reload:error])return NO;
 NSDictionary *preview=[self.store previewExtendedSlugs:selection error:error]; if(!preview)return NO;
 NSArray *updated=[self.store applyExtendedSlugs:selection expectedPreview:preview[@"version"] error:error];
 if(!updated)return NO; self.options=updated; return YES;
}
- (BOOL)undo:(NSError **)error {
 if(!self.isolated)return RepairFail(error,@"候选版不撤销真实设置。");
 if(![self reload:error])return NO; NSSet *previous=[self.store previousExtendedSlugs:error]; return previous&&[self applySelection:previous error:error];
}
- (NSDictionary *)status {
 NSMutableArray *models=[NSMutableArray new];
 for(CCModelContextOption *o in self.options)[models addObject:@{@"slug":o.slug,@"display_name":o.displayName,@"default":@(o.defaultContext),@"maximum":@(o.maximumContext),@"saved_extended":@(o.extended),@"can_extend":@(o.canExtend)}];
 return @{@"models":models,@"isolated_test":@(self.isolated),@"runtime_compatible":@(self.runtimeCompatible),@"cli_version":self.clientVersion ?: @"unknown",@"chat_verified":@NO,@"real_settings_writable":@NO};
}
@end
