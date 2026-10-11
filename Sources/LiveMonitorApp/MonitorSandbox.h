#ifndef CC_MONITOR_SANDBOX_H
#define CC_MONITOR_SANDBOX_H
#import <Foundation/Foundation.h>
#import <stdlib.h>

// Restricts our Python collection chain, not the GUI parent or Codex itself.
// No profile files, persistent settings, shell expansion, or unsafe fallback.
static inline NSString *CCMonitorSandboxPath(NSString *path) {
    if (![path isKindOfClass:NSString.class] || !path.isAbsolutePath || path.length > 4096 ||
        [path rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound) return nil;
    NSString *standard = path.stringByStandardizingPath;
    // Foundation normalizes /private/var back to /var on macOS. Seatbelt
    // matches the kernel path, so use POSIX realpath for the parent instead.
    // Keep the final component unresolved: it must never grant a symlink's
    // history/keychain target a read exception.
    char *resolved = realpath(standard.stringByDeletingLastPathComponent.fileSystemRepresentation, NULL);
    if (!resolved) return nil;
    NSString *parent = [NSFileManager.defaultManager stringWithFileSystemRepresentation:resolved length:strlen(resolved)];
    free(resolved);
    return [parent stringByAppendingPathComponent:standard.lastPathComponent];
}

static inline NSString *CCMonitorSandboxLiteral(NSString *path) {
    NSString *value = [path stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"];
    value = [value stringByReplacingOccurrencesOfString:@"\"" withString:@"\\\""];
    return [NSString stringWithFormat:@"\"%@\"",value];
}

#endif
