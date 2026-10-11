#import "CodexContextCore.h"
#import <poll.h>
#import <fcntl.h>
#import <signal.h>
#import <unistd.h>
#import <time.h>
#import <sys/file.h>
#import <sys/stat.h>
#import <CommonCrypto/CommonDigest.h>

static NSString *const CCContextErrorDomain = @"CodexContextSwitcher";

static BOOL CCFail(NSError **error, NSString *description) {
    if (error) *error = [NSError errorWithDomain:CCContextErrorDomain code:1 userInfo:@{NSLocalizedDescriptionKey:description}];
    return NO;
}

static BOOL CCExecutableUnchanged(NSURL *url, NSString *fingerprint, NSError **error) {
    if (fingerprint && [fingerprint isEqual:[CCExecutableFingerprint fingerprintForExecutableURL:url error:nil]]) return YES;
    return CCFail(error, @"Desktop CLI changed during validation; previous catalog preserved. Retry refresh.");
}

@implementation CCRuntimeResolver
+ (NSURL *)desktopExecutableForResourcesURL:(NSURL *)resourcesURL error:(NSError **)error {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSURL *package = [resourcesURL URLByAppendingPathComponent:@"codex-cli"];
    NSURL *manifest = [package URLByAppendingPathComponent:@"codex-package.json"];
    NSDictionary *attributes = [fm attributesOfItemAtPath:manifest.path error:nil];
    NSURL *candidate = nil;
    if (attributes) {
        if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes[NSFileSize] unsignedLongLongValue] > 1024*1024) {
            CCFail(error,@"Desktop package metadata is unsafe."); return nil;
        }
        NSDictionary *metadata = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:manifest] options:0 error:nil];
#if defined(__arm64__)
        NSString *target = @"aarch64-apple-darwin";
#else
        NSString *target = @"x86_64-apple-darwin";
#endif
        if (![metadata isKindOfClass:NSDictionary.class] || ![metadata[@"layoutVersion"] isEqual:@1] ||
            ![metadata[@"target"] isEqual:target] || ![metadata[@"variant"] isEqual:@"codex"] ||
            ![metadata[@"entrypoint"] isEqual:@"bin/codex"]) {
            CCFail(error,@"Unknown desktop package layout; no executable selected."); return nil;
        }
        candidate = [package URLByAppendingPathComponent:@"CodexCLI.app/Contents/MacOS/codex"];
    } else {
        candidate = [resourcesURL URLByAppendingPathComponent:@"codex"];
    }
    NSURL *canonical = candidate.URLByResolvingSymlinksInPath;
    NSURL *boundary = (attributes ? package : resourcesURL).URLByResolvingSymlinksInPath;
    NSDictionary *nativeAttributes = [fm attributesOfItemAtPath:canonical.path error:nil];
    if (![canonical.path hasPrefix:[boundary.path stringByAppendingString:@"/"]] ||
        ![nativeAttributes[NSFileType] isEqual:NSFileTypeRegular] || ![fm isExecutableFileAtPath:canonical.path]) {
        CCFail(error,@"Desktop native executable is missing or outside the package."); return nil;
    }
    return canonical;
}

+ (NSString *)versionFromOutput:(NSString *)output {
    if (![output isKindOfClass:NSString.class] || output.length > 4096) return nil;
    NSRegularExpression *pattern = [NSRegularExpression regularExpressionWithPattern:@"\\Acodex(?:-cli)?[ \\t]+([0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)[\\r\\n]*\\z" options:0 error:nil];
    NSTextCheckingResult *match = [pattern firstMatchInString:output options:0 range:NSMakeRange(0,output.length)];
    return match ? [output substringWithRange:[match rangeAtIndex:1]] : nil;
}

+ (NSURL *)nativeExecutableForLauncher:(NSURL *)launcher {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSURL *resolved = launcher.URLByResolvingSymlinksInPath;
    if (![resolved.pathExtension isEqual:@"js"]) return launcher;
    // Known npm layout only. Never execute Node or search arbitrary directories.
    if (![resolved.lastPathComponent isEqual:@"codex.js"] || ![resolved.URLByDeletingLastPathComponent.lastPathComponent isEqual:@"bin"]) return nil;
    NSURL *package = resolved.URLByDeletingLastPathComponent.URLByDeletingLastPathComponent;
    NSURL *manifest = [package URLByAppendingPathComponent:@"package.json"];
    NSDictionary *attributes = [fm attributesOfItemAtPath:manifest.path error:nil];
    if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes[NSFileSize] unsignedLongLongValue] > 1024*1024) return nil;
    NSData *raw = [NSData dataWithContentsOfURL:manifest];
    NSDictionary *metadata = raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:nil] : nil;
    if (![metadata isKindOfClass:NSDictionary.class] || ![metadata[@"name"] isEqual:@"@openai/codex"]) return nil;
#if defined(__arm64__)
    NSString *relative = @"node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex";
#else
    NSString *relative = @"node_modules/@openai/codex-darwin-x64/vendor/x86_64-apple-darwin/bin/codex";
#endif
    NSURL *native = [package URLByAppendingPathComponent:relative];
    NSURL *canonical = native.URLByResolvingSymlinksInPath;
    if (![canonical.path hasPrefix:[package.path stringByAppendingString:@"/"]] || ![fm isExecutableFileAtPath:canonical.path]) return nil;
    NSDictionary *nativeAttributes = [fm attributesOfItemAtPath:canonical.path error:nil];
    return [nativeAttributes[NSFileType] isEqual:NSFileTypeRegular] ? native : nil;
}

+ (NSDictionary *)resolveDesktopExecutableURL:(NSURL *)desktopURL independentCandidates:(NSArray<NSURL *> *)candidates {
    NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObject:@"desktop" forKey:@"source"];
    NSFileManager *fm = NSFileManager.defaultManager;
    if ([fm isExecutableFileAtPath:desktopURL.path]) {
        result[@"selectedURL"] = desktopURL;
        result[@"fingerprint"] = [CCExecutableFingerprint fingerprintForExecutableURL:desktopURL error:nil] ?: @"";
    }
    for (NSURL *candidate in candidates) {
        if ([fm isExecutableFileAtPath:candidate.path]) {
            result[@"independentURL"] = candidate;
            NSURL *native = [self nativeExecutableForLauncher:candidate];
            if (native) result[@"independentNativeURL"] = native;
            result[@"independentStatus"] = native ? @"resolved" : @"unknown";
            break;
        }
    }
    NSURL *secondary = result[@"independentNativeURL"] ?: result[@"independentURL"];
    NSString *secondaryFingerprint = secondary ? [CCExecutableFingerprint fingerprintForExecutableURL:secondary error:nil] : @"not-detected";
    result[@"consumerFingerprint"] = [NSString stringWithFormat:@"%@|%@|%@",result[@"fingerprint"] ?: @"desktop-missing",result[@"independentStatus"] ?: @"not-detected",secondaryFingerprint ?: @"unknown"];
    return result;
}
@end

static NSString *CCConsumerVersion(NSURL *url) {
    NSURL *home = [[NSURL fileURLWithPath:NSTemporaryDirectory()] URLByAppendingPathComponent:NSUUID.UUID.UUIDString];
    if (![NSFileManager.defaultManager createDirectoryAtURL:home withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil]) return @"unknown";
    NSDictionary *result = [CCBoundedProcess runExecutableURL:url arguments:@[@"--version"] isolatedHomeURL:home timeout:2 outputLimit:4096 error:nil];
    [NSFileManager.defaultManager removeItemAtURL:home error:nil];
    NSString *text = result ? [[NSString alloc] initWithData:result[@"stdout"] encoding:NSUTF8StringEncoding] : nil;
    return [CCRuntimeResolver versionFromOutput:text] ?: @"unknown";
}

static NSString *CCFileVersion(NSURL *url, NSError **error) {
    int fd = open(url.fileSystemRepresentation, O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
    if (fd < 0) { if (errno == ENOENT) return @"missing"; CCFail(error,@"Cannot safely fingerprint context input."); return nil; }
    struct stat before, after;
    if (fstat(fd,&before) != 0 || !S_ISREG(before.st_mode) || before.st_size > 16*1024*1024) { close(fd); CCFail(error,@"Unsafe or oversized context input."); return nil; }
    NSMutableData *data = [NSMutableData data]; uint8_t buffer[65536]; ssize_t count;
    while ((count = read(fd,buffer,sizeof(buffer))) > 0) {
        [data appendBytes:buffer length:(NSUInteger)count];
        if (data.length > 16*1024*1024) break;
    }
    BOOL stable = count == 0 && fstat(fd,&after) == 0 && data.length <= 16*1024*1024 && before.st_dev == after.st_dev && before.st_ino == after.st_ino && before.st_size == after.st_size && before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec && before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec && before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec && before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec;
    close(fd);
    if (!stable) { CCFail(error,@"Context input changed during fingerprinting; preview again."); return nil; }
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *hash = [NSMutableString string];
    for (NSUInteger i=0;i<CC_SHA256_DIGEST_LENGTH;i++) [hash appendFormat:@"%02x",digest[i]];
    return [NSString stringWithFormat:@"%llu:%llu:%lld:%ld:%ld:%@",(unsigned long long)before.st_dev,(unsigned long long)before.st_ino,(long long)before.st_size,before.st_mtimespec.tv_sec,before.st_mtimespec.tv_nsec,hash];
}

@implementation CCBoundedProcess
+ (NSString *)sandboxPolicyForExecutableURL:(NSURL *)executableURL isolatedHomeURL:(NSURL *)homeURL {
    NSArray *allowed = @[@"/Applications/ChatGPT.app/Contents/Resources/codex", @"/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"];
    if (![allowed containsObject:executableURL.path]) return nil;
    char *canonical = realpath(homeURL.fileSystemRepresentation,NULL);
    if (!canonical) return nil;
    NSString *home = [NSString stringWithUTF8String:canonical]; free(canonical);
    char *tempCanonical = realpath(NSTemporaryDirectory().fileSystemRepresentation,NULL);
    NSString *temp = tempCanonical ? [NSString stringWithUTF8String:tempCanonical] : @""; free(tempCanonical);
    BOOL temporary = [home hasPrefix:@"/private/tmp/"] || (temp.length && [home hasPrefix:[temp stringByAppendingString:@"/"]]);
    if (!temporary || [home containsString:@"\n"] || [home containsString:@"\r"]) return nil;
    NSString *(^quote)(NSString *) = ^NSString *(NSString *s) { return [NSString stringWithFormat:@"\"%@\"",[[s stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"] stringByReplacingOccurrencesOfString:@"\"" withString:@"\\\""]]; };
    NSString *runtimeRoot = [executableURL.path containsString:@"/codex-cli/"] ? @"/Applications/ChatGPT.app/Contents/Resources/codex-cli" : executableURL.path;
    return [NSString stringWithFormat:@"(version 1) (deny default) (allow process*) (allow sysctl-read) (allow file-read-metadata) (allow mach-lookup (global-name \"com.apple.system.logger\") (global-name \"com.apple.logd\")) (allow file-read* (literal \"/\") (subpath \"/System\") (subpath \"/usr/lib\") (subpath \"/usr/bin\") (subpath \"/bin\") (subpath \"/Library/Apple\") (subpath \"/Library/Developer/CommandLineTools\") (subpath \"/private/var/db/dyld\") (subpath %@) (literal \"/dev/null\") (literal \"/dev/random\") (literal \"/dev/urandom\")) (allow file-read* file-write* (subpath %@)) (deny file-read* (subpath \"/Library/Keychains\") (subpath \"/System/Library/Keychains\")) (deny network*)",quote(runtimeRoot),quote(home)];
}

+ (NSDictionary *)runExecutableURL:(NSURL *)executableURL arguments:(NSArray<NSString *> *)arguments
                   isolatedHomeURL:(NSURL *)homeURL timeout:(NSTimeInterval)timeout
                       outputLimit:(NSUInteger)outputLimit error:(NSError **)error {
    NSTask *task = [NSTask new];
    BOOL official = [executableURL.path isEqual:@"/Applications/ChatGPT.app/Contents/Resources/codex"] || [executableURL.path isEqual:@"/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"];
    NSString *policy = official ? [self sandboxPolicyForExecutableURL:executableURL isolatedHomeURL:homeURL] : nil;
    if (official && !policy) { CCFail(error,@"Official CLI probe isolation could not be established; no fallback."); return nil; }
    task.executableURL = official ? [NSURL fileURLWithPath:@"/usr/bin/sandbox-exec"] : executableURL;
    task.arguments = official ? [@[@"-p",policy,executableURL.path] arrayByAddingObjectsFromArray:arguments] : arguments;
    task.currentDirectoryURL = homeURL;
    task.environment = @{@"HOME":homeURL.path, @"CODEX_HOME":homeURL.path, @"TMPDIR":homeURL.path,
                         @"PATH":@"/usr/bin:/bin", @"LANG":@"en_US.UTF-8"};
    task.standardInput = [NSFileHandle fileHandleWithNullDevice];
    NSPipe *out = [NSPipe pipe], *err = [NSPipe pipe];
    task.standardOutput = out; task.standardError = err;
    if (![task launchAndReturnError:error]) return nil;
    [out.fileHandleForWriting closeFile]; [err.fileHandleForWriting closeFile];
    int fds[2] = {out.fileHandleForReading.fileDescriptor, err.fileHandleForReading.fileDescriptor};
    for (int i=0;i<2;i++) fcntl(fds[i], F_SETFL, fcntl(fds[i], F_GETFL) | O_NONBLOCK);
    NSMutableData *buffers[2] = {[NSMutableData data], [NSMutableData data]};
    BOOL open[2] = {YES, YES};
    uint64_t start = clock_gettime_nsec_np(CLOCK_MONOTONIC);
    NSString *failure = nil;
    while (open[0] || open[1] || task.running) {
        if ((clock_gettime_nsec_np(CLOCK_MONOTONIC)-start)/1e9 >= timeout) { failure = @"Codex probe timed out; previous catalog preserved."; break; }
        struct pollfd watched[2] = {{open[0]?fds[0]:-1,POLLIN,0},{open[1]?fds[1]:-1,POLLIN,0}};
        int ready = poll(watched, 2, 20);
        if (ready < 0 && errno != EINTR) { failure = @"Unable to drain Codex probe output."; break; }
        for (int i=0;i<2;i++) {
            if (!open[i] || !(watched[i].revents & (POLLIN|POLLHUP|POLLERR))) continue;
            uint8_t bytes[65536];
            ssize_t count = read(fds[i], bytes, sizeof(bytes));
            if (count == 0) open[i] = NO;
            else if (count > 0) {
                if (buffers[0].length + buffers[1].length + (NSUInteger)count > outputLimit) { failure = @"Codex probe exceeded output limit; previous catalog preserved."; break; }
                [buffers[i] appendBytes:bytes length:(NSUInteger)count];
            } else if (errno != EAGAIN && errno != EINTR) { failure = @"Unable to read Codex probe output."; break; }
        }
        if (failure) break;
    }
    if (failure && task.running) kill(task.processIdentifier, SIGKILL);
    [out.fileHandleForReading closeFile]; [err.fileHandleForReading closeFile];
    [task waitUntilExit];
    if (failure) { CCFail(error, failure); return nil; }
    // Never put arbitrary stderr (which can contain private information) into UI diagnostics.
    if (task.terminationStatus != 0) { CCFail(error, [NSString stringWithFormat:@"Codex probe exited with status %d.", task.terminationStatus]); return nil; }
    return @{@"stdout":buffers[0], @"stderr":buffers[1], @"status":@(task.terminationStatus)};
}
@end

typedef NS_ENUM(NSInteger, CCContextErrorCode) {
    CCContextErrorInvalidCatalog = 1,
    CCContextErrorSerialization = 2,
};

@interface CCModelContextOption ()
@property(nonatomic, copy, readwrite) NSString *slug;
@property(nonatomic, copy, readwrite) NSString *displayName;
@property(nonatomic, readwrite) NSInteger defaultContext;
@property(nonatomic, readwrite) NSInteger maximumContext;
@property(nonatomic, readwrite, getter=isExtended) BOOL extended;
@property(nonatomic, readwrite) BOOL canExtend;
@property(nonatomic, readwrite, getter=isRetired) BOOL retired;
@property(nonatomic, copy, readwrite, nullable) NSString *replacementSlug;
@end

@implementation CCModelContextOption
@end

static NSDate *CCRetirementDate(NSString *text) {
    if (!text.length) return nil;
    NSISO8601DateFormatter *parser = [NSISO8601DateFormatter new];
    parser.formatOptions = NSISO8601DateFormatWithInternetDateTime;
    NSDate *date = [parser dateFromString:text];
    if (date) return date;
    parser.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    return [parser dateFromString:text];
}

@implementation CCCatalogTransformer

+ (NSData *)transformSourceData:(NSData *)sourceData
                   templateData:(NSData *)templateData
                  extendedSlugs:(NSSet<NSString *> *)extendedSlugs
                        options:(NSArray<CCModelContextOption *> **)options
                          error:(NSError **)error {
    if (![CCCodexCatalogProbe isValidCatalogData:sourceData] || ![CCCodexCatalogProbe isValidCatalogData:templateData]) {
        CCFail(error, @"Catalog contains invalid or duplicate model identities.");
        return nil;
    }
    NSError *jsonError = nil;
    id parsedSource = [NSJSONSerialization JSONObjectWithData:sourceData
                                                      options:NSJSONReadingMutableContainers
                                                        error:&jsonError];
    if (![parsedSource isKindOfClass:[NSMutableDictionary class]]) {
        if (error) {
            NSString *description = jsonError.localizedDescription ?: @"The model catalog root is not an object.";
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: description}];
        }
        return nil;
    }

    NSMutableDictionary *sourceRoot = parsedSource;
    id rawSourceModels = sourceRoot[@"models"];
    if (![rawSourceModels isKindOfClass:[NSMutableArray class]]) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"The model catalog does not contain a models array."}];
        }
        return nil;
    }

    jsonError = nil;
    id parsedTemplate = [NSJSONSerialization JSONObjectWithData:templateData
                                                        options:NSJSONReadingMutableContainers
                                                          error:&jsonError];
    id rawTemplateModels = [parsedTemplate isKindOfClass:[NSMutableDictionary class]]
        ? parsedTemplate[@"models"]
        : nil;
    if (![parsedTemplate isKindOfClass:[NSMutableDictionary class]] ||
        ![rawTemplateModels isKindOfClass:[NSMutableArray class]] ||
        [(NSMutableArray *)rawTemplateModels count] == 0) {
        if (error) {
            NSString *description = jsonError.localizedDescription ?: @"The strict model-catalog template is malformed.";
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: description}];
        }
        return nil;
    }

    NSMutableDictionary<NSString *, NSDictionary *> *templatesBySlug = [NSMutableDictionary dictionary];
    NSDictionary *fallbackTemplate = nil;
    for (id rawTemplate in (NSMutableArray *)rawTemplateModels) {
        if (![rawTemplate isKindOfClass:[NSDictionary class]]) {
            continue;
        }
        NSString *slug = [rawTemplate[@"slug"] isKindOfClass:[NSString class]] ? rawTemplate[@"slug"] : nil;
        if (slug.length == 0) {
            continue;
        }
        templatesBySlug[slug] = rawTemplate;
        if (!fallbackTemplate || [slug isEqualToString:@"gpt-5.6-sol"]) {
            fallbackTemplate = rawTemplate;
        }
    }
    if (!fallbackTemplate) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"The strict model-catalog template has no usable model."}];
        }
        return nil;
    }

    NSMutableDictionary *root = [(NSDictionary *)parsedTemplate mutableCopy];
    for (NSString *key in sourceRoot) {
        if (![key isEqualToString:@"models"]) {
            root[key] = sourceRoot[key];
        }
    }
    NSMutableArray *mergedModels = [NSMutableArray array];

    NSMutableArray<CCModelContextOption *> *modelOptions = [NSMutableArray array];
    for (id rawModel in (NSMutableArray *)rawSourceModels) {
        if (![rawModel isKindOfClass:[NSDictionary class]]) {
            continue;
        }
        NSDictionary *sourceModel = rawModel;
        NSString *slug = [sourceModel[@"slug"] isKindOfClass:[NSString class]] ? sourceModel[@"slug"] : @"";
        if (slug.length == 0) {
            continue;
        }
        NSDictionary *strictTemplate = templatesBySlug[slug] ?: fallbackTemplate;
        NSMutableDictionary *model = [strictTemplate mutableCopy];
        [model addEntriesFromDictionary:sourceModel];
        NSString *displayName = [model[@"display_name"] isKindOfClass:[NSString class]]
            ? model[@"display_name"]
            : slug;
        NSInteger defaultContext = [sourceModel[@"context_window"] respondsToSelector:@selector(integerValue)]
            ? [sourceModel[@"context_window"] integerValue]
            : [model[@"context_window"] respondsToSelector:@selector(integerValue)]
                ? [model[@"context_window"] integerValue]
            : 0;
        NSInteger maximumContext = [sourceModel[@"max_context_window"] respondsToSelector:@selector(integerValue)]
            ? [sourceModel[@"max_context_window"] integerValue]
            : defaultContext;
        BOOL hasLargerContext = defaultContext > 0 && maximumContext > defaultContext;
        NSDictionary *upgrade = [sourceModel[@"upgrade"] isKindOfClass:NSDictionary.class] ? sourceModel[@"upgrade"] : nil;
        NSString *retirementText = [upgrade[@"retirement_at"] isKindOfClass:NSString.class] ? upgrade[@"retirement_at"] : nil;
        NSDate *retirement = CCRetirementDate(retirementText);
        BOOL retired = retirement && [retirement compare:[NSDate date]] != NSOrderedDescending;
        BOOL canExtend = hasLargerContext && !retired;
        BOOL isExtended = hasLargerContext && [extendedSlugs containsObject:slug];

        if (defaultContext > 0) {
            model[@"context_window"] = @(isExtended ? maximumContext : defaultContext);
        }

        CCModelContextOption *option = [CCModelContextOption new];
        option.slug = slug;
        option.displayName = displayName;
        option.defaultContext = defaultContext;
        option.maximumContext = MAX(defaultContext, maximumContext);
        option.canExtend = canExtend;
        option.extended = isExtended;
        option.retired = retired;
        option.replacementSlug = [upgrade[@"model"] isKindOfClass:NSString.class] ? upgrade[@"model"] : nil;
        [modelOptions addObject:option];
        [mergedModels addObject:model];
    }

    root[@"models"] = mergedModels;

    NSData *output = [NSJSONSerialization dataWithJSONObject:root
                                                     options:(NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys)
                                                       error:&jsonError];
    if (!output) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorSerialization
                                     userInfo:@{NSLocalizedDescriptionKey: jsonError.localizedDescription ?: @"Unable to serialize the custom model catalog."}];
        }
        return nil;
    }
    if (options) {
        *options = [modelOptions copy];
    }
    return output;
}

@end

@interface CCContextStore ()
@property(nonatomic, readwrite) NSURL *sourceCatalogURL;
@property(nonatomic, readwrite) NSURL *templateCatalogURL;
@property(nonatomic, readwrite) NSURL *settingsDirectoryURL;
@property(nonatomic, readwrite) NSURL *customCatalogURL;
@property(nonatomic, readwrite) NSURL *stateURL;
- (nullable NSData *)transformedCatalogForExtendedSlugs:(NSSet<NSString *> *)extendedSlugs
                                                 options:(NSArray<CCModelContextOption *> * _Nullable * _Nullable)options
                                                   error:(NSError **)error;
@end

@implementation CCContextStore

- (NSURL *)journalURL { return [self.settingsDirectoryURL URLByAppendingPathComponent:@"pending-transaction.json"]; }

// The persistent lock inode is never renamed or removed. Every cooperating process
// holds it from recovery/read/derivation through validation and final commit.
- (int)acquireTransactionLockForWriting:(BOOL)writing error:(NSError **)error {
    NSFileManager *fm = NSFileManager.defaultManager;
    if (writing && ![fm createDirectoryAtURL:self.settingsDirectoryURL withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:error]) return -1;
    NSURL *url = [self.settingsDirectoryURL URLByAppendingPathComponent:@"transaction.lock"];
    int fd = open(url.fileSystemRepresentation, (writing ? O_RDWR|O_CREAT : O_RDONLY) | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK, 0600);
    if (fd < 0) {
        if (!writing && errno == ENOENT) return -2; // A read never creates settings or a lock.
        CCFail(error, @"Cannot open catalog transaction lock."); return -1;
    }
    struct stat info;
    if (fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) || flock(fd, (writing ? LOCK_EX : LOCK_SH) | LOCK_NB) != 0) {
        close(fd); CCFail(error, @"Catalog transaction is busy or lock is unsafe; retry after the active operation finishes."); return -1;
    }
    return fd;
}

- (id)withTransactionLockForWriting:(BOOL)writing error:(NSError **)error perform:(id (^)(NSError **))operation {
    int fd = [self acquireTransactionLockForWriting:writing error:error];
    if (fd == -1) return nil;
    @try {
        NSError *localError = nil;
        id result = operation(&localError);
        if (localError && error) *error = localError;
        return result;
    }
    @finally { if (fd >= 0) { flock(fd, LOCK_UN); close(fd); } }
}

- (BOOL)writeTransactionData:(NSData *)data toURL:(NSURL *)url error:(NSError **)error {
    return [data writeToURL:url options:NSDataWritingAtomic error:error];
}

- (BOOL)recoverPendingTransaction:(NSError **)error {
    return [[self withTransactionLockForWriting:YES error:error perform:^id(NSError **localError){
        return @([self recoverPendingTransactionLocked:localError]);
    }] boolValue];
}

- (BOOL)recoverPendingTransactionLocked:(NSError **)error {
    NSFileManager *fm = NSFileManager.defaultManager;
    if (![fm fileExistsAtPath:self.journalURL.path]) return YES;
    NSData *raw = [NSData dataWithContentsOfURL:self.journalURL options:0 error:error];
    id journal = raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:error] : nil;
    if (![journal isKindOfClass:NSDictionary.class] || ![journal[@"version"] isEqual:@1]) return CCFail(error, @"Incomplete catalog recovery: unsupported journal version.");
    NSDictionary *entries = [journal isKindOfClass:NSDictionary.class] ? journal[@"entries"] : nil;
    NSSet *allowed = [NSSet setWithArray:@[@"state.json", @"models-custom.json", @"codex-template-current.json", @"runtime.json"]];
    if (![entries isKindOfClass:NSDictionary.class] || !entries.count) return CCFail(error, @"Incomplete catalog recovery: invalid journal.");
    // Check every entry before restoring any file. External edits are never overwritten.
    for (NSString *name in entries) {
        id entry = entries[name];
        if (![allowed containsObject:name] || ![entry isKindOfClass:NSDictionary.class]) return CCFail(error, @"Incomplete catalog recovery: unsafe journal entry.");
        id before = entry[@"before"];
        id after = entry[@"after"];
        if (!(before == NSNull.null || [before isKindOfClass:NSString.class]) || ![after isKindOfClass:NSString.class]) return CCFail(error, @"Incomplete catalog recovery: invalid snapshot.");
        NSData *old = before == NSNull.null ? nil : [[NSData alloc] initWithBase64EncodedString:before options:0];
        NSData *new = [[NSData alloc] initWithBase64EncodedString:after options:0];
        if (!new || (before != NSNull.null && !old)) return CCFail(error, @"Incomplete catalog recovery: invalid snapshot encoding.");
        NSURL *url = [self.settingsDirectoryURL URLByAppendingPathComponent:name];
        NSDictionary *attributes = [fm attributesOfItemAtPath:url.path error:nil];
        if (attributes && ![attributes[NSFileType] isEqual:NSFileTypeRegular]) return CCFail(error, @"Incomplete catalog recovery: target is not a regular file.");
        NSData *current = [NSData dataWithContentsOfURL:url];
        if (!((!current && !old) || [current isEqual:old] || [current isEqual:new])) return CCFail(error, @"Incomplete catalog recovery: target was edited externally; journal retained.");
    }
    for (NSString *name in entries) {
        NSURL *url = [self.settingsDirectoryURL URLByAppendingPathComponent:name];
        id before = entries[name][@"before"];
        if (before == NSNull.null) {
            if ([fm fileExistsAtPath:url.path] && ![fm removeItemAtURL:url error:error]) return NO;
        } else if (![self writeTransactionData:[[NSData alloc] initWithBase64EncodedString:before options:0] toURL:url error:error]) return NO;
    }
    return [fm removeItemAtURL:self.journalURL error:error];
}

- (BOOL)commitFiles:(NSDictionary<NSString *, NSData *> *)files error:(NSError **)error {
    NSFileManager *fm = NSFileManager.defaultManager;
    if (![self recoverPendingTransactionLocked:error]) return NO;
    if (![fm createDirectoryAtURL:self.settingsDirectoryURL withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:error]) return NO;
    NSMutableDictionary *entries = [NSMutableDictionary dictionary];
    for (NSString *name in files) {
        NSURL *url = [self.settingsDirectoryURL URLByAppendingPathComponent:name];
        NSDictionary *attributes = [fm attributesOfItemAtPath:url.path error:nil];
        if (attributes && ![attributes[NSFileType] isEqual:NSFileTypeRegular]) return CCFail(error, @"Catalog transaction target is not a regular file.");
        NSData *old = attributes ? [NSData dataWithContentsOfURL:url options:0 error:error] : nil;
        if (attributes && !old) return NO;
        entries[name] = @{@"before":old ? [old base64EncodedStringWithOptions:0] : NSNull.null,
                          @"after":[files[name] base64EncodedStringWithOptions:0]};
    }
    NSData *journal = [NSJSONSerialization dataWithJSONObject:@{@"version":@1,@"entries":entries} options:NSJSONWritingSortedKeys error:error];
    if (!journal || ![journal writeToURL:self.journalURL options:NSDataWritingAtomic error:error]) return NO;
    [fm setAttributes:@{NSFilePosixPermissions:@0600} ofItemAtPath:self.journalURL.path error:nil];
    // State first is intentional; the persisted before-images make any interruption recoverable.
    NSArray *order = @[@"state.json", @"codex-template-current.json", @"models-custom.json", @"runtime.json"];
    for (NSString *name in order) {
        NSData *data = files[name]; if (!data) continue;
        NSURL *url = [self.settingsDirectoryURL URLByAppendingPathComponent:name];
        NSError *writeError = nil;
        if (![self writeTransactionData:data toURL:url error:&writeError] || ![[NSData dataWithContentsOfURL:url] isEqual:data]) {
            NSError *recoveryError = nil;
            BOOL recovered = [self recoverPendingTransactionLocked:&recoveryError];
            return CCFail(error, recovered ? (writeError.localizedDescription ?: @"Catalog readback failed; prior files restored.") : [NSString stringWithFormat:@"Incomplete catalog recovery: %@", recoveryError.localizedDescription]);
        }
    }
    if (![fm removeItemAtURL:self.journalURL error:error]) {
        NSError *recoveryError = nil;
        [self recoverPendingTransactionLocked:&recoveryError];
        return CCFail(error, @"Unable to finalize catalog transaction; inspect recovery journal.");
    }
    return YES;
}

- (instancetype)initWithSourceCatalogURL:(NSURL *)sourceCatalogURL
                      templateCatalogURL:(NSURL *)templateCatalogURL
                     settingsDirectoryURL:(NSURL *)settingsDirectoryURL {
    self = [super init];
    if (self) {
        _sourceCatalogURL = sourceCatalogURL;
        _templateCatalogURL = templateCatalogURL;
        _settingsDirectoryURL = settingsDirectoryURL;
        _customCatalogURL = [settingsDirectoryURL URLByAppendingPathComponent:@"models-custom.json"];
        _stateURL = [settingsDirectoryURL URLByAppendingPathComponent:@"state.json"];
    }
    return self;
}

- (NSArray<CCModelContextOption *> *)loadOptions:(NSError **)error {
    return [self withTransactionLockForWriting:NO error:error perform:^id(NSError **localError){ return [self loadOptionsLocked:localError]; }];
}

- (NSArray<CCModelContextOption *> *)loadOptionsLocked:(NSError **)error {
    NSSet<NSString *> *saved = [self savedExtendedSlugsLocked:error];
    if (!saved) {
        return nil;
    }
    NSArray<CCModelContextOption *> *options = nil;
    if (![self transformedCatalogForExtendedSlugs:saved options:&options error:error]) {
        return nil;
    }
    return options;
}

- (NSData *)transformedCatalogForExtendedSlugs:(NSSet<NSString *> *)extendedSlugs
                                        options:(NSArray<CCModelContextOption *> **)options
                                          error:(NSError **)error {
    NSError *localError = nil;
    NSData *sourceData = [NSData dataWithContentsOfURL:self.sourceCatalogURL
                                               options:0
                                                 error:&localError];
    if (!sourceData) {
        if (error) {
            *error = localError;
        }
        return nil;
    }

    NSData *templateData = [NSData dataWithContentsOfURL:self.templateCatalogURL
                                                 options:0
                                                   error:&localError];
    if (!templateData) {
        if (error) {
            *error = localError;
        }
        return nil;
    }

    NSData *customData = [CCCatalogTransformer transformSourceData:sourceData
                                                      templateData:templateData
                                                     extendedSlugs:extendedSlugs
                                                           options:options
                                                             error:&localError];
    if (!customData) {
        if (error) {
            *error = localError;
        }
        return nil;
    }
    return customData;
}

- (NSArray<CCModelContextOption *> *)applyExtendedSlugs:(NSSet<NSString *> *)extendedSlugs
                                                   error:(NSError **)error {
    return [self withTransactionLockForWriting:YES error:error perform:^id(NSError **localError){ return [self applyExtendedSlugsLocked:extendedSlugs error:localError]; }];
}

- (NSString *)contextVersionLocked:(NSError **)error {
    NSArray *urls = @[self.stateURL,self.sourceCatalogURL,self.templateCatalogURL,self.customCatalogURL,
                     [self.settingsDirectoryURL URLByAppendingPathComponent:@"runtime.json"],self.journalURL];
    NSMutableArray *parts = [NSMutableArray array];
    for (NSURL *url in urls) {
        NSString *version = CCFileVersion(url,error); if (!version) return nil;
        [parts addObject:[NSString stringWithFormat:@"%@=%@",url.path,version]];
    }
    NSData *raw = [[parts componentsJoinedByString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(raw.bytes,(CC_LONG)raw.length,digest);
    NSMutableString *token = [NSMutableString string];
    for (NSUInteger index=0;index<CC_SHA256_DIGEST_LENGTH;index++) [token appendFormat:@"%02x",digest[index]];
    return token;
}

- (NSDictionary *)previewExtendedSlugs:(NSSet<NSString *> *)extendedSlugs error:(NSError **)error {
    return [self withTransactionLockForWriting:NO error:error perform:^id(NSError **localError){
        NSString *version = [self contextVersionLocked:localError]; if (!version) return nil;
        NSArray *options = [self loadOptionsLocked:localError]; if (!options) return nil;
        NSMutableSet *allowed = [[CCContextSelection allExtensibleSlugsFromOptions:options] mutableCopy];
        for (CCModelContextOption *option in options) if (option.isExtended) [allowed addObject:option.slug];
        if (![extendedSlugs isSubsetOfSet:allowed]) { CCFail(localError,@"Requested context model is retired or no longer available; preview again."); return nil; }
        if (![version isEqual:[self contextVersionLocked:localError]]) { CCFail(localError,@"Context changed while creating preview; retry."); return nil; }
        return @{@"version":version,@"options":options,@"selection":[[extendedSlugs allObjects] sortedArrayUsingSelector:@selector(compare:)]};
    }];
}

- (NSArray<CCModelContextOption *> *)applyExtendedSlugs:(NSSet<NSString *> *)extendedSlugs expectedPreview:(NSString *)version error:(NSError **)error {
    if (!version.length) { CCFail(error,@"Context preview version is missing; preview again."); return nil; }
    return [self withTransactionLockForWriting:YES error:error perform:^id(NSError **localError){
        return [self applyExtendedSlugsLocked:extendedSlugs expectedVersion:version error:localError];
    }];
}

- (BOOL)validateSharedCatalog:(NSData *)catalog desktop:(NSURL *)desktop temporaryRoot:(NSURL *)root error:(NSError **)error {
    if (self.secondaryConsumerUnresolved) return CCFail(error,@"Consumer compatibility unknown: detected independent CLI native runtime could not be resolved. Previous shared catalog preserved.");
    NSString *primaryFingerprint = desktop ? [CCExecutableFingerprint fingerprintForExecutableURL:desktop error:nil] : nil;
    NSString *secondaryFingerprint = self.secondaryValidationExecutableURL ? [CCExecutableFingerprint fingerprintForExecutableURL:self.secondaryValidationExecutableURL error:nil] : nil;
    if (desktop && ![CCCodexCatalogProbe validateCatalogData:catalog executableURL:desktop temporaryRootURL:root error:error]) return NO;
    if (self.secondaryValidationExecutableURL && ![CCCodexCatalogProbe validateCatalogData:catalog executableURL:self.secondaryValidationExecutableURL temporaryRootURL:root error:nil]) {
        return CCFail(error,[NSString stringWithFormat:@"Consumer conflict: independent CLI %@ rejected the shared catalog generated for desktop CLI %@; previous compatible catalog preserved.",CCConsumerVersion(self.secondaryValidationExecutableURL),desktop ? CCConsumerVersion(desktop) : @"unknown"]);
    }
    if (desktop && !CCExecutableUnchanged(desktop,primaryFingerprint,error)) return NO;
    if (self.secondaryValidationExecutableURL && ![secondaryFingerprint isEqual:[CCExecutableFingerprint fingerprintForExecutableURL:self.secondaryValidationExecutableURL error:nil]]) return CCFail(error,@"Independent CLI changed during validation; previous shared catalog preserved.");
    return YES;
}

- (NSArray<CCModelContextOption *> *)applyExtendedSlugsLocked:(NSSet<NSString *> *)extendedSlugs error:(NSError **)error {
    return [self applyExtendedSlugsLocked:extendedSlugs expectedVersion:nil error:error];
}

- (NSArray<CCModelContextOption *> *)applyExtendedSlugsLocked:(NSSet<NSString *> *)extendedSlugs expectedVersion:(NSString *)expectedVersion error:(NSError **)error {
    if (expectedVersion && ![expectedVersion isEqual:[self contextVersionLocked:error]]) { CCFail(error,@"Context preview is stale (state or catalog changed); preview again before applying."); return nil; }
    if (![self recoverPendingTransactionLocked:error]) return nil;
    NSString *version = [self contextVersionLocked:error]; if (!version) return nil;
    NSArray *currentOptions = [self loadOptionsLocked:error]; if (!currentOptions) return nil;
    NSMutableSet *allowedSelection = [[CCContextSelection allExtensibleSlugsFromOptions:currentOptions] mutableCopy];
    for (CCModelContextOption *option in currentOptions) if (option.isExtended) [allowedSelection addObject:option.slug];
    if (![extendedSlugs isSubsetOfSet:allowedSelection]) { CCFail(error,@"Requested context selection would newly extend a retired or unavailable model."); return nil; }
    NSError *localError = nil;
    NSArray<CCModelContextOption *> *options = nil;
    NSData *customData = [self transformedCatalogForExtendedSlugs:extendedSlugs
                                                           options:&options
                                                             error:&localError];
    if (!customData) {
        if (error) {
            *error = localError;
        }
        return nil;
    }

    if (![extendedSlugs isSubsetOfSet:allowedSelection]) { CCFail(error, @"Requested context selection contains unavailable models."); return nil; }
    NSSet *previous = [self savedExtendedSlugsLocked:error]; if (!previous) return nil;
    NSArray<NSString *> *sortedSlugs = [[extendedSlugs allObjects] sortedArrayUsingSelector:@selector(compare:)];
    NSArray *history = [[previous allObjects] sortedArrayUsingSelector:@selector(compare:)];
    if ([previous isEqual:extendedSlugs]) {
        NSData *existingState = [NSData dataWithContentsOfURL:self.stateURL];
        NSDictionary *existing = existingState ? [NSJSONSerialization JSONObjectWithData:existingState options:0 error:nil] : nil;
        if ([existing isKindOfClass:NSDictionary.class] && [existing[@"previous_extended_slugs"] isKindOfClass:NSArray.class]) history = existing[@"previous_extended_slugs"];
    }
    NSData *stateData = [NSJSONSerialization dataWithJSONObject:@{@"extended_slugs": sortedSlugs, @"previous_extended_slugs":history}
                                                        options:(NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys)
                                                          error:&localError];
    if (!stateData) {
        if (error) {
            *error = localError;
        }
        return nil;
    }

    if (![self validateSharedCatalog:customData desktop:self.validationExecutableURL temporaryRoot:[NSURL fileURLWithPath:NSTemporaryDirectory()] error:error]) return nil;
    if (![version isEqual:[self contextVersionLocked:error]]) { CCFail(error,@"Context state/catalog changed during validation; preview again. Nothing committed."); return nil; }
    if (![self commitFiles:@{@"state.json":stateData, @"models-custom.json":customData} error:error]) return nil;
    return options;
}

- (NSArray<CCModelContextOption *> *)refreshWithTemplateData:(NSData *)templateData executableURL:(NSURL *)executableURL temporaryRootURL:(NSURL *)temporaryRootURL error:(NSError **)error {
    return [self withTransactionLockForWriting:YES error:error perform:^id(NSError **localError){ return [self refreshWithTemplateDataLocked:templateData executableURL:executableURL temporaryRootURL:temporaryRootURL error:localError]; }];
}

- (NSArray<CCModelContextOption *> *)refreshWithTemplateDataLocked:(NSData *)templateData executableURL:(NSURL *)executableURL temporaryRootURL:(NSURL *)temporaryRootURL error:(NSError **)error {
    NSString *fingerprint = [CCExecutableFingerprint fingerprintForExecutableURL:executableURL error:error];
    if (!fingerprint) return nil;
    if (![self recoverPendingTransactionLocked:error]) return nil;
    NSSet *saved = [self savedExtendedSlugsLocked:error]; if (!saved) return nil;
    NSData *source = [NSData dataWithContentsOfURL:self.sourceCatalogURL options:0 error:error]; if (!source) return nil;
    NSArray *options = nil;
    NSData *custom = [CCCatalogTransformer transformSourceData:source templateData:templateData extendedSlugs:saved options:&options error:error];
    if (!custom || ![CCCodexCatalogProbe validateCatalogData:templateData executableURL:executableURL temporaryRootURL:temporaryRootURL error:error] ||
        ![self validateSharedCatalog:custom desktop:executableURL temporaryRoot:temporaryRootURL error:error]) return nil;
    if (!CCExecutableUnchanged(executableURL, fingerprint, error)) return nil;
    NSMutableDictionary *stateObject = [@{@"extended_slugs":[[saved allObjects] sortedArrayUsingSelector:@selector(compare:)]} mutableCopy];
    NSData *existingState = [NSData dataWithContentsOfURL:self.stateURL];
    NSDictionary *existing = existingState ? [NSJSONSerialization JSONObjectWithData:existingState options:0 error:nil] : nil;
    if ([existing isKindOfClass:NSDictionary.class] && existing[@"previous_extended_slugs"]) stateObject[@"previous_extended_slugs"] = existing[@"previous_extended_slugs"];
    NSData *state = [NSJSONSerialization dataWithJSONObject:stateObject options:NSJSONWritingSortedKeys error:error];
    NSURL *appURL = [[[executableURL URLByDeletingLastPathComponent] URLByDeletingLastPathComponent] URLByDeletingLastPathComponent];
    NSDictionary *info = [NSDictionary dictionaryWithContentsOfURL:[appURL URLByAppendingPathComponent:@"Contents/Info.plist"]] ?: @{};
    NSData *metadata = [NSJSONSerialization dataWithJSONObject:@{@"source":@"desktop", @"cli_path":executableURL.path,
        @"fingerprint":fingerprint, @"generated_at":@([NSDate date].timeIntervalSince1970),
        @"source_client_version":[NSJSONSerialization JSONObjectWithData:source options:0 error:nil][@"client_version"] ?: @"unknown", @"source_freshness":@"unverified",
        @"app_version":info[@"CFBundleShortVersionString"] ?: @"unknown", @"app_build":info[@"CFBundleVersion"] ?: @"unknown"} options:NSJSONWritingSortedKeys error:error];
    if (!state || !metadata || ![self commitFiles:@{@"state.json":state,@"models-custom.json":custom,@"codex-template-current.json":templateData,@"runtime.json":metadata} error:error]) return nil;
    self.templateCatalogURL = [self.settingsDirectoryURL URLByAppendingPathComponent:@"codex-template-current.json"];
    self.validationExecutableURL = executableURL;
    return options;
}

- (NSArray<CCModelContextOption *> *)restoreDefaults:(NSError **)error {
    return [self applyExtendedSlugs:[NSSet set] error:error];
}

- (NSSet<NSString *> *)savedExtendedSlugs:(NSError **)error {
    return [self withTransactionLockForWriting:NO error:error perform:^id(NSError **localError){ return [self savedExtendedSlugsLocked:localError]; }];
}

- (NSSet<NSString *> *)previousExtendedSlugsLocked:(NSError **)error {
    if (![self savedExtendedSlugsLocked:error]) return nil;
    NSData *raw = [NSData dataWithContentsOfURL:self.stateURL];
    NSDictionary *state = raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:nil] : nil;
    id previous = [state isKindOfClass:NSDictionary.class] ? state[@"previous_extended_slugs"] : nil;
    if (![previous isKindOfClass:NSArray.class]) { CCFail(error, @"No previous context selection is available."); return nil; }
    NSMutableSet *slugs = [NSMutableSet set];
    for (id slug in previous) {
        if (![slug isKindOfClass:NSString.class] || ![slug length] || [slugs containsObject:slug]) { CCFail(error, @"Previous context selection is malformed."); return nil; }
        [slugs addObject:slug];
    }
    NSArray *options = [self loadOptionsLocked:error]; if (!options) return nil;
    if (![slugs isSubsetOfSet:[CCContextSelection allExtensibleSlugsFromOptions:options]]) { CCFail(error, @"Previous selection includes models unavailable in the current catalog; unchanged."); return nil; }
    return slugs;
}

- (NSSet<NSString *> *)previousExtendedSlugs:(NSError **)error {
    return [self withTransactionLockForWriting:NO error:error perform:^id(NSError **localError){ return [self previousExtendedSlugsLocked:localError]; }];
}

- (NSArray<CCModelContextOption *> *)restorePreviousSelection:(NSError **)error {
    return [self withTransactionLockForWriting:YES error:error perform:^id(NSError **localError){
        if (![self recoverPendingTransactionLocked:localError]) return nil;
        NSSet *previous = [self previousExtendedSlugsLocked:localError];
        return previous ? [self applyExtendedSlugsLocked:previous error:localError] : nil;
    }];
}

- (NSSet<NSString *> *)savedExtendedSlugsLocked:(NSError **)error {
    if ([[NSFileManager defaultManager] fileExistsAtPath:self.journalURL.path]) {
        CCFail(error, @"Unfinished catalog transaction; explicit recovery is required.");
        return nil;
    }
    if (![[NSFileManager defaultManager] fileExistsAtPath:self.stateURL.path]) {
        return [NSSet set];
    }
    NSError *localError = nil;
    NSData *data = [NSData dataWithContentsOfURL:self.stateURL options:0 error:&localError];
    if (!data) {
        if (error) {
            *error = localError;
        }
        return nil;
    }
    id parsed = [NSJSONSerialization JSONObjectWithData:data options:0 error:&localError];
    NSArray *rawSlugs = [parsed isKindOfClass:[NSDictionary class]] ? parsed[@"extended_slugs"] : nil;
    if (![rawSlugs isKindOfClass:[NSArray class]]) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"The saved context-switcher state is malformed."}];
        }
        return nil;
    }
    NSMutableSet<NSString *> *slugs = [NSMutableSet set];
    for (id value in rawSlugs) {
        if ([value isKindOfClass:[NSString class]]) {
            [slugs addObject:value];
        }
    }
    return [slugs copy];
}

@end

@implementation CCCodexConfigEditor

+ (NSString *)configByInstallingCatalogPath:(NSString *)catalogPath
                                      inText:(NSString *)configText
                                       error:(NSError **)error {
    if (catalogPath.length == 0 || [catalogPath containsString:@"\n"] || [catalogPath containsString:@"\r"]) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"The custom catalog path is invalid."}];
        }
        return nil;
    }
    NSString *escaped = [[catalogPath stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"]
        stringByReplacingOccurrencesOfString:@"\"" withString:@"\\\""];
    NSString *newLine = [NSString stringWithFormat:@"model_catalog_json = \"%@\"", escaped];
    NSMutableArray<NSString *> *lines = [[configText componentsSeparatedByString:@"\n"] mutableCopy];
    BOOL replaced = NO;
    BOOL reachedTable = NO;
    NSCharacterSet *whitespace = [NSCharacterSet whitespaceCharacterSet];

    // This deliberately narrow editor rejects syntaxes it cannot safely preserve.
    if ([configText containsString:@"\"\"\""] || [configText containsString:@"'''"]) {
        CCFail(error, @"Multiline TOML is unsupported by the catalog-path editor."); return nil;
    }
    NSString *ending = [configText containsString:@"\r\n"] ? @"\r" : @"";

    for (NSUInteger index = 0; index < lines.count; index++) {
        NSString *trimmed = [lines[index] stringByTrimmingCharactersInSet:whitespace];
        if ([trimmed hasPrefix:@"["]) {
            reachedTable = YES;
        }
        if (!reachedTable && ![trimmed hasPrefix:@"#"]) {
            NSRange equals = [trimmed rangeOfString:@"="];
            if (equals.location == NSNotFound) continue;
            // Single-line arrays are safe; an open array across lines can make a
            // nested '[' look like a table header to this deliberately narrow editor.
            NSString *value = [trimmed substringFromIndex:equals.location+1];
            NSInteger arrayDepth = 0;
            unichar quote = 0; BOOL escapedCharacter = NO;
            for (NSUInteger i=0; i<value.length; i++) {
                unichar c = [value characterAtIndex:i];
                if (quote) {
                    if (escapedCharacter) escapedCharacter = NO;
                    else if (quote == '"' && c == '\\') escapedCharacter = YES;
                    else if (c == quote) quote = 0;
                } else if (c == '#') break;
                else if (c == '"' || c == '\'') quote = c;
                else if (c == '[') arrayDepth++;
                else if (c == ']') arrayDepth--;
            }
            if (arrayDepth != 0) { CCFail(error, @"Multiline arrays are unsupported by the catalog-path editor; configuration unchanged."); return nil; }
            NSString *key = [[trimmed substringToIndex:equals.location] stringByTrimmingCharactersInSet:whitespace];
            if ([key containsString:@"\""] || [key containsString:@"'"] || ([key containsString:@"model_catalog_json"] && [key containsString:@"."])) {
                CCFail(error, @"Quoted or dotted catalog keys are unsupported; configuration unchanged."); return nil;
            }
            if ([key isEqual:@"model_catalog_json"]) {
                if (replaced) { CCFail(error, @"Duplicate model_catalog_json keys; configuration unchanged."); return nil; }
                NSRegularExpression *assignment = [NSRegularExpression regularExpressionWithPattern:@"^([ \\t]*model_catalog_json[ \\t]*=[ \\t]*)(\"(?:\\\\.|[^\"\\\\])*\"|'[^']*')([ \\t]*(?:#.*)?)(\\r?)$" options:0 error:nil];
                NSTextCheckingResult *match = [assignment firstMatchInString:lines[index] options:0 range:NSMakeRange(0, lines[index].length)];
                if (!match) { CCFail(error, @"Unsupported catalog assignment; configuration unchanged."); return nil; }
                NSString *prefix = [lines[index] substringWithRange:[match rangeAtIndex:1]];
                NSString *suffix = [lines[index] substringFromIndex:NSMaxRange([match rangeAtIndex:2])];
                lines[index] = [NSString stringWithFormat:@"%@\"%@\"%@",prefix,escaped,suffix];
                replaced = YES;
            }
        }
    }
    if (!replaced) {
        [lines insertObject:[newLine stringByAppendingString:ending] atIndex:0];
    }
    return [lines componentsJoinedByString:@"\n"];
}

@end

@implementation CCCodexCatalogProbe

+ (BOOL)isValidCatalogData:(NSData *)catalogData {
    if (catalogData.length == 0) {
        return NO;
    }
    id root = [NSJSONSerialization JSONObjectWithData:catalogData options:0 error:nil];
    NSArray *models = [root isKindOfClass:[NSDictionary class]] ? root[@"models"] : nil;
    if (![models isKindOfClass:[NSArray class]] || models.count == 0) {
        return NO;
    }
    NSMutableSet *seen = [NSMutableSet set];
    NSCharacterSet *validSlug = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/"];
    for (id model in models) {
        if (![model isKindOfClass:[NSDictionary class]]) {
            return NO;
        }
        NSString *slug = [model[@"slug"] isKindOfClass:[NSString class]] ? model[@"slug"] : nil;
        if (slug.length == 0 || [slug rangeOfCharacterFromSet:validSlug.invertedSet].location != NSNotFound || [seen containsObject:slug]) {
            return NO;
        }
        [seen addObject:slug];
    }
    return YES;
}

+ (NSData *)catalogDataFromExecutableURL:(NSURL *)executableURL
                         temporaryRootURL:(NSURL *)temporaryRootURL
                                    error:(NSError **)error {
    NSFileManager *fileManager = NSFileManager.defaultManager;
    NSURL *isolatedHome = [temporaryRootURL URLByAppendingPathComponent:NSUUID.UUID.UUIDString
                                                            isDirectory:YES];
    NSError *localError = nil;
    if (![fileManager createDirectoryAtURL:isolatedHome
                withIntermediateDirectories:YES
                                 attributes:nil
                                      error:&localError]) {
        if (error) {
            *error = localError;
        }
        return nil;
    }

    NSDictionary *result = [CCBoundedProcess runExecutableURL:executableURL arguments:@[@"debug", @"models", @"--bundled"] isolatedHomeURL:isolatedHome timeout:10 outputLimit:16*1024*1024 error:&localError];
    NSData *outputData = result[@"stdout"];
    [fileManager removeItemAtURL:isolatedHome error:nil];
    if (!result) { if (error) *error = localError; return nil; }
    if (![self isValidCatalogData:outputData]) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"Codex returned an invalid model catalog."}];
        }
        return nil;
    }
    return outputData;
}

+ (BOOL)validateCatalogData:(NSData *)catalogData executableURL:(NSURL *)executableURL temporaryRootURL:(NSURL *)temporaryRootURL error:(NSError **)error {
    if (![self isValidCatalogData:catalogData]) return CCFail(error, @"Invalid model catalog identity.");
    NSString *fingerprint = [CCExecutableFingerprint fingerprintForExecutableURL:executableURL error:error];
    if (!fingerprint) return NO;
    NSFileManager *fm = NSFileManager.defaultManager;
    NSURL *home = [temporaryRootURL URLByAppendingPathComponent:NSUUID.UUID.UUIDString isDirectory:YES];
    if (![fm createDirectoryAtURL:home withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:error]) return NO;
    NSURL *catalog = [home URLByAppendingPathComponent:@"candidate.json"];
    BOOL written = [catalogData writeToURL:catalog options:NSDataWritingAtomic error:error];
    NSString *path = [[catalog.path stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"] stringByReplacingOccurrencesOfString:@"\"" withString:@"\\\""];
    NSDictionary *result = written ? [CCBoundedProcess runExecutableURL:executableURL arguments:@[@"debug", @"models", @"-c", [NSString stringWithFormat:@"model_catalog_json=\"%@\"",path]] isolatedHomeURL:home timeout:10 outputLimit:16*1024*1024 error:error] : nil;
    [fm removeItemAtURL:home error:nil];
    if (!result) return NO;
    NSData *output = result[@"stdout"];
    if (![self isValidCatalogData:output]) return CCFail(error, @"Target CLI rejected model catalog schema.");
    NSArray *expected = [NSJSONSerialization JSONObjectWithData:catalogData options:0 error:nil][@"models"];
    NSArray *actual = [NSJSONSerialization JSONObjectWithData:output options:0 error:nil][@"models"];
    NSMutableDictionary *contexts = [NSMutableDictionary dictionary];
    for (NSDictionary *model in actual) contexts[model[@"slug"]] = model[@"context_window"] ?: NSNull.null;
    if (contexts.count != expected.count) return CCFail(error, @"Target CLI did not load the candidate catalog.");
    for (NSDictionary *model in expected) {
        if (![contexts[model[@"slug"]] isEqual:model[@"context_window"] ?: NSNull.null]) return CCFail(error, @"Target CLI changed candidate model identity or context.");
    }
    return CCExecutableUnchanged(executableURL, fingerprint, error);
}

@end

@implementation CCCatalogTemplateCache

+ (BOOL)replaceCatalogAtURL:(NSURL *)catalogURL
          withValidatedData:(NSData *)catalogData
                      error:(NSError **)error {
    if (![CCCodexCatalogProbe isValidCatalogData:catalogData]) {
        if (error) {
            *error = [NSError errorWithDomain:CCContextErrorDomain
                                         code:CCContextErrorInvalidCatalog
                                     userInfo:@{NSLocalizedDescriptionKey: @"The probed Codex catalog is invalid; the last valid cache was preserved."}];
        }
        return NO;
    }
    NSError *localError = nil;
    NSURL *directoryURL = [catalogURL URLByDeletingLastPathComponent];
    if (![[NSFileManager defaultManager] createDirectoryAtURL:directoryURL
                                  withIntermediateDirectories:YES
                                                   attributes:nil
                                                        error:&localError] ||
        ![catalogData writeToURL:catalogURL options:NSDataWritingAtomic error:&localError]) {
        if (error) {
            *error = localError;
        }
        return NO;
    }
    return YES;
}

@end

@implementation CCExecutableFingerprint

+ (NSString *)fingerprintForExecutableURL:(NSURL *)executableURL error:(NSError **)error {
    NSURL *resolvedURL = executableURL.URLByResolvingSymlinksInPath;
    NSError *localError = nil;
    NSDictionary<NSFileAttributeKey, id> *attributes = [[NSFileManager defaultManager]
        attributesOfItemAtPath:resolvedURL.path
                         error:&localError];
    if (!attributes) {
        if (error) {
            *error = localError;
        }
        return nil;
    }
    NSNumber *size = attributes[NSFileSize] ?: @0;
    NSDate *modificationDate = attributes[NSFileModificationDate] ?: [NSDate dateWithTimeIntervalSince1970:0];
    return [NSString stringWithFormat:@"%@|%@|%.9f|%@|%@",
                                      resolvedURL.path,
                                      size,
                                      modificationDate.timeIntervalSince1970,
                                      attributes[NSFileSystemFileNumber] ?: @0,
                                      attributes[NSFileCreationDate] ?: @""];
}

@end

@implementation CCFileContentFingerprint
+ (NSString *)fingerprintForFileURL:(NSURL *)fileURL error:(NSError **)error {
    return CCFileVersion(fileURL, error);
}
@end

@implementation CCContextSelection

+ (NSSet<NSString *> *)allExtensibleSlugsFromOptions:(NSArray<CCModelContextOption *> *)options {
    NSMutableSet<NSString *> *slugs = [NSMutableSet set];
    for (CCModelContextOption *option in options) {
        if (option.canExtend) {
            [slugs addObject:option.slug];
        }
    }
    return [slugs copy];
}

+ (NSSet<NSString *> *)slugsByTogglingSlug:(NSString *)slug
                            inExtendedSlugs:(NSSet<NSString *> *)extendedSlugs {
    NSMutableSet<NSString *> *updated = [extendedSlugs mutableCopy];
    if ([updated containsObject:slug]) {
        [updated removeObject:slug];
    } else {
        [updated addObject:slug];
    }
    return [updated copy];
}

@end
