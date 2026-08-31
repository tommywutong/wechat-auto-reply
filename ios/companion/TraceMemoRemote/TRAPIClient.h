#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef void (^TRAPICompletion)(NSDictionary * _Nullable payload, NSError * _Nullable error);

@interface TRAPIClient : NSObject

@property (nonatomic, copy, readonly) NSString *host;
@property (nonatomic, assign, readonly) NSInteger port;
@property (nonatomic, copy, readonly) NSString *token;

- (instancetype)initWithHost:(NSString *)host port:(NSInteger)port token:(NSString *)token;
- (void)pairWithCode:(NSString *)code completion:(TRAPICompletion)completion;
- (void)fetchStatus:(TRAPICompletion)completion;
- (void)fetchLogs:(NSInteger)limit completion:(TRAPICompletion)completion;
- (void)fetchConfig:(TRAPICompletion)completion;
- (void)updateConfig:(NSDictionary *)values completion:(TRAPICompletion)completion;
- (void)serviceAction:(NSString *)action completion:(TRAPICompletion)completion;

@end

NS_ASSUME_NONNULL_END
