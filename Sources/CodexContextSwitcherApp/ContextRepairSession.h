#import <Foundation/Foundation.h>
#import "CodexContextCore.h"
@interface CCRepairSession : NSObject
@property(nonatomic,readonly) CCContextStore *store;
@property(nonatomic,readonly) NSArray<CCModelContextOption *> *options;
@property(nonatomic,readonly) BOOL isolated;
@property(nonatomic,readonly) BOOL runtimeCompatible;
@property(nonatomic,readonly) NSURL *executableURL;
@property(nonatomic,readonly) NSURL *catalogURL;
@property(nonatomic,readonly) NSString *clientVersion;
+ (BOOL)isIsolatedTestRoot:(NSString *)path;
- (instancetype)initWithResourcesURL:(NSURL *)resources settingsURL:(NSURL *)settings isolated:(BOOL)isolated error:(NSError **)error;
- (BOOL)reload:(NSError **)error;
- (BOOL)applySelection:(NSSet<NSString *> *)selection error:(NSError **)error;
- (BOOL)undo:(NSError **)error;
- (NSDictionary *)status;
@end
