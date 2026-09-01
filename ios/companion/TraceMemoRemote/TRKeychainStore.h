#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface TRKeychainStore : NSObject
+ (nullable NSString *)stringForKey:(NSString *)key;
+ (BOOL)setString:(NSString *)value forKey:(NSString *)key;
+ (BOOL)deleteValueForKey:(NSString *)key;
@end

NS_ASSUME_NONNULL_END
