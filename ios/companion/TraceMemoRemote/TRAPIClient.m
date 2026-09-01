#import "TRAPIClient.h"

@interface TRAPIClient ()
@property (nonatomic, copy, readwrite) NSString *host;
@property (nonatomic, assign, readwrite) NSInteger port;
@property (nonatomic, copy, readwrite) NSString *token;
@end

static NSString * const TRAPIErrorDomain = @"com.wxauto.TraceMemoRemote.api";

static BOOL TRIsPrivateIPv4(NSString *host) {
    NSArray<NSString *> *parts = [host componentsSeparatedByString:@"."];
    if (parts.count != 4) return NO;
    NSInteger octets[4];
    for (NSUInteger index = 0; index < parts.count; index++) {
        NSString *part = parts[index];
        if (part.length == 0 || part.length > 3 || [part rangeOfCharacterFromSet:[[NSCharacterSet decimalDigitCharacterSet] invertedSet]].location != NSNotFound) return NO;
        NSScanner *scanner = [NSScanner scannerWithString:part];
        NSInteger value = -1;
        if (![scanner scanInteger:&value] || !scanner.isAtEnd || value < 0 || value > 255) return NO;
        octets[index] = value;
    }
    return octets[0] == 10 ||
        (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
        (octets[0] == 192 && octets[1] == 168) ||
        (octets[0] == 169 && octets[1] == 254);
}

static BOOL TRIsAllowedHost(NSString *host) {
    NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789.-"];
    if ([host hasSuffix:@".local"] && host.length > 6 && [host rangeOfString:@".."].location == NSNotFound && [host rangeOfCharacterFromSet:[allowed invertedSet]].location == NSNotFound) {
        return YES;
    }
    return TRIsPrivateIPv4(host);
}

@implementation TRAPIClient

- (instancetype)initWithHost:(NSString *)host port:(NSInteger)port token:(NSString *)token {
    self = [super init];
    if (self) {
        _host = [host copy];
        _port = port;
        _token = [token copy];
    }
    return self;
}

- (NSURL *)URLForPath:(NSString *)path {
    NSString *safeHost = [self.host stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if ([safeHost hasPrefix:@"http://"] || [safeHost hasPrefix:@"https://"]) {
        safeHost = [safeHost componentsSeparatedByString:@"://"].lastObject;
    }
    safeHost = [[safeHost componentsSeparatedByString:@"/"] firstObject];
    safeHost = [safeHost lowercaseString];
    // 控制令牌只允许发到 Bonjour .local 或 RFC1918 链路地址，不能因输错地址发往公网。
    if (self.port < 1 || self.port > 65535 || !TRIsAllowedHost(safeHost)) {
        return nil;
    }
    NSString *urlString = [NSString stringWithFormat:@"http://%@:%ld%@", safeHost, (long)self.port, path];
    return [NSURL URLWithString:urlString];
}

- (void)request:(NSString *)method path:(NSString *)path body:(NSDictionary * _Nullable)body completion:(TRAPICompletion)completion {
    NSURL *url = [self URLForPath:path];
    if (!url) {
        completion(nil, [NSError errorWithDomain:TRAPIErrorDomain code:1 userInfo:@{NSLocalizedDescriptionKey: @"Mac 地址无效"}]);
        return;
    }
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:12];
    request.HTTPMethod = method;
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    if (self.token.length > 0) {
        [request setValue:[NSString stringWithFormat:@"Bearer %@", self.token] forHTTPHeaderField:@"Authorization"];
    }
    if (body) {
        request.HTTPBody = [NSJSONSerialization dataWithJSONObject:body options:0 error:nil];
        [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    }
    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error) {
            dispatch_async(dispatch_get_main_queue(), ^{ completion(nil, error); });
            return;
        }
        NSInteger status = [(NSHTTPURLResponse *)response statusCode];
        NSDictionary *payload = nil;
        if (data.length > 0) {
            id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if ([object isKindOfClass:NSDictionary.class]) payload = object;
        }
        if (status < 200 || status >= 300) {
            NSString *message = [payload[@"detail"] isKindOfClass:NSString.class] ? payload[@"detail"] : [NSString stringWithFormat:@"Mac 返回 HTTP %ld", (long)status];
            NSError *apiError = [NSError errorWithDomain:TRAPIErrorDomain code:status userInfo:@{NSLocalizedDescriptionKey: message}];
            dispatch_async(dispatch_get_main_queue(), ^{ completion(payload, apiError); });
            return;
        }
        dispatch_async(dispatch_get_main_queue(), ^{ completion(payload ?: @{}, nil); });
    }];
    [task resume];
}

- (void)fetchHealth:(TRAPICompletion)completion {
    [self request:@"GET" path:@"/health" body:nil completion:completion];
}

- (void)pairWithCode:(NSString *)code completion:(TRAPICompletion)completion {
    [self request:@"POST" path:@"/pair" body:@{ @"code": code ?: @"" } completion:completion];
}

- (void)fetchStatus:(TRAPICompletion)completion {
    [self request:@"GET" path:@"/status" body:nil completion:completion];
}

- (void)fetchLogs:(NSInteger)limit completion:(TRAPICompletion)completion {
    [self request:@"GET" path:[NSString stringWithFormat:@"/logs?limit=%ld", (long)MAX(1, MIN(limit, 500))] body:nil completion:completion];
}

- (void)fetchConfig:(TRAPICompletion)completion {
    [self request:@"GET" path:@"/config" body:nil completion:completion];
}

- (void)updateConfig:(NSDictionary *)values completion:(TRAPICompletion)completion {
    [self request:@"PUT" path:@"/config" body:@{ @"values": values ?: @{} } completion:completion];
}

- (void)serviceAction:(NSString *)action completion:(TRAPICompletion)completion {
    [self request:@"POST" path:[NSString stringWithFormat:@"/service/%@", action] body:nil completion:completion];
}

@end
