#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface CCModelContextOption : NSObject
@property(nonatomic, copy, readonly) NSString *slug;
@property(nonatomic, copy, readonly) NSString *displayName;
@property(nonatomic, readonly) NSInteger defaultContext;
@property(nonatomic, readonly) NSInteger maximumContext;
@property(nonatomic, readonly, getter=isExtended) BOOL extended;
@property(nonatomic, readonly) BOOL canExtend;
@property(nonatomic, readonly, getter=isRetired) BOOL retired;
@property(nonatomic, copy, readonly, nullable) NSString *replacementSlug;
@end

@interface CCCatalogTransformer : NSObject
+ (nullable NSData *)transformSourceData:(NSData *)sourceData
                            templateData:(NSData *)templateData
                           extendedSlugs:(NSSet<NSString *> *)extendedSlugs
                                 options:(NSArray<CCModelContextOption *> * _Nullable * _Nullable)options
                                   error:(NSError **)error;
@end

@interface CCContextStore : NSObject
@property(nonatomic, readonly) NSURL *sourceCatalogURL;
@property(nonatomic, readonly) NSURL *templateCatalogURL;
@property(nonatomic, readonly) NSURL *settingsDirectoryURL;
@property(nonatomic, readonly) NSURL *customCatalogURL;
@property(nonatomic, readonly) NSURL *stateURL;
@property(nonatomic, nullable) NSURL *validationExecutableURL;
@property(nonatomic, nullable) NSURL *secondaryValidationExecutableURL;
@property(nonatomic) BOOL secondaryConsumerUnresolved;
- (instancetype)initWithSourceCatalogURL:(NSURL *)sourceCatalogURL
                      templateCatalogURL:(NSURL *)templateCatalogURL
                     settingsDirectoryURL:(NSURL *)settingsDirectoryURL NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
- (nullable NSArray<CCModelContextOption *> *)loadOptions:(NSError **)error;
- (nullable NSArray<CCModelContextOption *> *)applyExtendedSlugs:(NSSet<NSString *> *)extendedSlugs
                                                           error:(NSError **)error;
- (nullable NSDictionary *)previewExtendedSlugs:(NSSet<NSString *> *)extendedSlugs error:(NSError **)error;
- (nullable NSArray<CCModelContextOption *> *)applyExtendedSlugs:(NSSet<NSString *> *)extendedSlugs expectedPreview:(NSString *)version error:(NSError **)error;
- (nullable NSArray<CCModelContextOption *> *)restoreDefaults:(NSError **)error;
- (NSSet<NSString *> *)savedExtendedSlugs:(NSError **)error;
- (nullable NSSet<NSString *> *)previousExtendedSlugs:(NSError **)error;
- (nullable NSArray<CCModelContextOption *> *)restorePreviousSelection:(NSError **)error;
// Recovery is explicit: read-only calls report an unfinished journal, never mutate it.
- (BOOL)recoverPendingTransaction:(NSError **)error;
- (nullable NSArray<CCModelContextOption *> *)refreshWithTemplateData:(NSData *)templateData
                                                      executableURL:(NSURL *)executableURL
                                                   temporaryRootURL:(NSURL *)temporaryRootURL
                                                              error:(NSError **)error;
@end

@interface CCRuntimeResolver : NSObject
+ (nullable NSURL *)desktopExecutableForResourcesURL:(NSURL *)resourcesURL error:(NSError **)error;
+ (nullable NSString *)versionFromOutput:(NSString *)output;
+ (NSDictionary *)resolveDesktopExecutableURL:(NSURL *)desktopURL independentCandidates:(NSArray<NSURL *> *)candidates;
@end

@interface CCBoundedProcess : NSObject
+ (nullable NSString *)sandboxPolicyForExecutableURL:(NSURL *)executableURL isolatedHomeURL:(NSURL *)homeURL;
+ (nullable NSDictionary *)runExecutableURL:(NSURL *)executableURL arguments:(NSArray<NSString *> *)arguments
                            isolatedHomeURL:(NSURL *)homeURL timeout:(NSTimeInterval)timeout
                               outputLimit:(NSUInteger)outputLimit error:(NSError **)error;
@end

@interface CCCodexConfigEditor : NSObject
+ (nullable NSString *)configByInstallingCatalogPath:(NSString *)catalogPath
                                              inText:(NSString *)configText
                                               error:(NSError **)error;
@end

@interface CCCodexCatalogProbe : NSObject
+ (nullable NSData *)catalogDataFromExecutableURL:(NSURL *)executableURL
                                  temporaryRootURL:(NSURL *)temporaryRootURL
                                             error:(NSError **)error;
+ (BOOL)isValidCatalogData:(NSData *)catalogData;
+ (BOOL)validateCatalogData:(NSData *)catalogData executableURL:(NSURL *)executableURL temporaryRootURL:(NSURL *)temporaryRootURL error:(NSError **)error;
@end

@interface CCCatalogTemplateCache : NSObject
+ (BOOL)replaceCatalogAtURL:(NSURL *)catalogURL
          withValidatedData:(NSData *)catalogData
                      error:(NSError **)error;
@end

@interface CCExecutableFingerprint : NSObject
+ (nullable NSString *)fingerprintForExecutableURL:(NSURL *)executableURL
                                              error:(NSError **)error;
@end

@interface CCFileContentFingerprint : NSObject
+ (nullable NSString *)fingerprintForFileURL:(NSURL *)fileURL error:(NSError **)error;
@end

@interface CCContextSelection : NSObject
+ (NSSet<NSString *> *)allExtensibleSlugsFromOptions:(NSArray<CCModelContextOption *> *)options;
+ (NSSet<NSString *> *)slugsByTogglingSlug:(NSString *)slug
                            inExtendedSlugs:(NSSet<NSString *> *)extendedSlugs;
@end

NS_ASSUME_NONNULL_END
