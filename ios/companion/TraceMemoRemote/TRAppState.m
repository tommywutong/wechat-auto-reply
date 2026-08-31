#import "TRAppState.h"
#import "TRKeychainStore.h"

NSNotificationName const TRAppStateDidChangeNotification = @"TRAppStateDidChangeNotification";

@interface TRAppState ()
@property (nonatomic, strong) TRAPIClient *api;
@end

@implementation TRAppState

+ (instancetype)shared {
    static TRAppState *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ instance = [TRAppState new]; });
    return instance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _host = [[NSUserDefaults standardUserDefaults] stringForKey:@"macHost"] ?: @"";
        _port = [[NSUserDefaults standardUserDefaults] integerForKey:@"macPort"] ?: 8850;
        if (_port == 0) _port = 8850;
        _token = [TRKeychainStore stringForKey:@"control-token"];
        _status = @{};
        _config = @{};
        _logs = @[];
        _lastError = @"";
        [self rebuildClient];
    }
    return self;
}

- (void)setHost:(NSString *)host { _host = [host copy]; [self persistConnection]; [self rebuildClient]; }
- (void)setPort:(NSInteger)port { _port = port; [self persistConnection]; [self rebuildClient]; }
- (void)setToken:(NSString *)token { _token = [token copy]; [self rebuildClient]; }

- (void)persistConnection {
    [[NSUserDefaults standardUserDefaults] setObject:self.host forKey:@"macHost"];
    [[NSUserDefaults standardUserDefaults] setInteger:self.port forKey:@"macPort"];
}

- (void)rebuildClient {
    _api = [[TRAPIClient alloc] initWithHost:self.host port:self.port token:self.token ?: @""];
}

- (TRAPIClient *)client { return self.api; }

- (void)notifyChanged { [[NSNotificationCenter defaultCenter] postNotificationName:TRAppStateDidChangeNotification object:self]; }

- (void)pairWithCode:(NSString *)code completion:(void (^)(NSError * _Nullable))completion {
    [self.client pairWithCode:code completion:^(NSDictionary *payload, NSError *error) {
        if (error) { self.lastError = error.localizedDescription; completion(error); return; }
        NSString *token = [payload[@"token"] isKindOfClass:NSString.class] ? payload[@"token"] : nil;
        if (token.length == 0 || ![TRKeychainStore setString:token forKey:@"control-token"]) {
            NSError *saveError = [NSError errorWithDomain:@"com.wxauto.TraceMemoRemote" code:2 userInfo:@{NSLocalizedDescriptionKey: @"配对成功，但无法保存控制凭据"}];
            self.lastError = saveError.localizedDescription;
            completion(saveError);
            return;
        }
        self.token = token;
        self.lastError = @"";
        [self notifyChanged];
        completion(nil);
    }];
}

- (void)refreshAll { [self refreshStatus]; [self refreshLogs]; [self refreshConfig]; }

- (void)refreshStatus {
    if (self.token.length == 0 || self.host.length == 0) return;
    [self.client fetchStatus:^(NSDictionary *payload, NSError *error) {
        if (error) self.lastError = error.localizedDescription;
        else { self.status = payload ?: @{}; self.lastError = @""; }
        [self notifyChanged];
    }];
}

- (void)refreshLogs {
    if (self.token.length == 0 || self.host.length == 0) return;
    [self.client fetchLogs:180 completion:^(NSDictionary *payload, NSError *error) {
        if (error) self.lastError = error.localizedDescription;
        else if ([payload[@"lines"] isKindOfClass:NSArray.class]) { self.logs = payload[@"lines"]; self.lastError = @""; }
        [self notifyChanged];
    }];
}

- (void)refreshConfig {
    if (self.token.length == 0 || self.host.length == 0) return;
    [self.client fetchConfig:^(NSDictionary *payload, NSError *error) {
        if (error) self.lastError = error.localizedDescription;
        else { self.config = payload ?: @{}; self.lastError = @""; }
        [self notifyChanged];
    }];
}

- (void)serviceAction:(NSString *)action completion:(void (^)(NSError * _Nullable))completion {
    [self.client serviceAction:action completion:^(NSDictionary *payload, NSError *error) {
        if (!error) self.status = payload ?: @{};
        else self.lastError = error.localizedDescription;
        [self notifyChanged];
        completion(error);
    }];
}

- (void)updateConfig:(NSDictionary *)values completion:(void (^)(NSError * _Nullable))completion {
    [self.client updateConfig:values completion:^(NSDictionary *payload, NSError *error) {
        if (!error) self.config = payload ?: @{};
        else self.lastError = error.localizedDescription;
        [self notifyChanged];
        completion(error);
    }];
}

- (void)disconnect {
    [TRKeychainStore deleteValueForKey:@"control-token"];
    self.token = nil;
    self.status = @{};
    self.config = @{};
    self.logs = @[];
    [self notifyChanged];
}

@end
