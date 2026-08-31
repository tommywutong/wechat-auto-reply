#import "TRKeychainStore.h"
#import <Security/Security.h>

static NSString * const TRKeychainService = @"com.wxauto.TraceMemoRemote";

@implementation TRKeychainStore

+ (NSMutableDictionary *)queryForKey:(NSString *)key {
    return [@{ (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
               (__bridge id)kSecAttrService: TRKeychainService,
               (__bridge id)kSecAttrAccount: key } mutableCopy];
}

+ (NSString *)stringForKey:(NSString *)key {
    NSMutableDictionary *query = [self queryForKey:key];
    query[(__bridge id)kSecReturnData] = @YES;
    query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
    CFTypeRef result = NULL;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
    if (status != errSecSuccess || !result) return nil;
    NSData *data = CFBridgingRelease(result);
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}

+ (BOOL)setString:(NSString *)value forKey:(NSString *)key {
    NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];
    NSMutableDictionary *query = [self queryForKey:key];
    NSDictionary *attributes = @{ (__bridge id)kSecValueData: data };
    OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)attributes);
    if (status == errSecItemNotFound) {
        query[(__bridge id)kSecValueData] = data;
        status = SecItemAdd((__bridge CFDictionaryRef)query, NULL);
    }
    return status == errSecSuccess;
}

+ (BOOL)deleteValueForKey:(NSString *)key {
    return SecItemDelete((__bridge CFDictionaryRef)[self queryForKey:key]) == errSecSuccess;
}

@end
