#import <Foundation/Foundation.h>
#import "TRAPIClient.h"

NS_ASSUME_NONNULL_BEGIN

FOUNDATION_EXPORT NSNotificationName const TRAppStateDidChangeNotification;

@interface TRAppState : NSObject
+ (instancetype)shared;
@property (nonatomic, copy) NSString *host;
@property (nonatomic, assign) NSInteger port;
@property (nonatomic, copy, nullable) NSString *token;
@property (nonatomic, copy) NSDictionary *status;
@property (nonatomic, copy) NSDictionary *config;
@property (nonatomic, copy) NSArray<NSString *> *logs;
@property (nonatomic, copy) NSString *lastError;

- (TRAPIClient *)client;
- (void)pairWithCode:(NSString *)code completion:(void (^)(NSError * _Nullable error))completion;
- (void)refreshAll;
- (void)refreshStatus;
- (void)refreshLogs;
- (void)refreshConfig;
- (void)serviceAction:(NSString *)action completion:(void (^)(NSError * _Nullable error))completion;
- (void)updateConfig:(NSDictionary *)values completion:(void (^)(NSError * _Nullable error))completion;
- (void)disconnect;
@end

NS_ASSUME_NONNULL_END
