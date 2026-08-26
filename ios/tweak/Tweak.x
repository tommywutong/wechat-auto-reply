// iOS 微信自动回复插件（Logos / Theos）
//
// 这是「真·插件」：把 dylib 注入微信进程，直接 hook 它的收发消息方法。
// 功能最完整、延迟最低，但需要越狱机，或对 IPA 重签名后注入
// （见 ios/tweak/README.md）。App Store 原版微信上装不了。
//
// ⚠️ 版本适配：下面这些私有类和方法名来自微信 iOS 8.0.x 的运行时符号。
// 微信每次大版本更新都可能改签名。换版本前务必用 Frida 或 class-dump
// 重新确认，方法见 README「适配新版本」一节。签名对不上时 hook 会
// 静默失效——%hook 找不到类不会崩，只是什么都不发生。

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

// ---------------------------------------------------------------- 微信私有接口

@interface MMServiceCenter : NSObject
+ (instancetype)defaultCenter;
- (id)getService:(Class)serviceClass;
@end

@interface CMessageWrap : NSObject
@property(nonatomic, strong) NSString *m_nsFromUsr;   // 发送方 wxid
@property(nonatomic, strong) NSString *m_nsToUsr;     // 接收方 wxid
@property(nonatomic, strong) NSString *m_nsContent;   // 正文
@property(nonatomic, assign) unsigned int m_uiMessageType;  // 1 = 纯文本
@property(nonatomic, assign) unsigned int m_uiCreateTime;
@end

@interface CContact : NSObject
@property(nonatomic, strong) NSString *m_nsNickName;
@property(nonatomic, strong) NSString *m_nsUsrName;
- (BOOL)isBrandContact;   // 公众号
- (BOOL)isChatroom;       // 群聊
@end

@interface CContactMgr : NSObject
- (CContact *)getContactByName:(NSString *)name;
- (CContact *)getSelfContact;
@end

@interface CMessageMgr : NSObject
- (void)SendTextMessage:(NSString *)fromUsr toUsr:(NSString *)toUsr msgText:(NSString *)text;
@end

// ---------------------------------------------------------------- 配置

// 规则服务地址。装到手机上后改这里，或用 preferences bundle 做成设置项。
static NSString *const kEngineURL = @"http://127.0.0.1:8848/reply";
static NSString *const kEngineToken = @"CHANGE_ME";

// 这一端在驱动哪个微信号。跑多个号时必须各填各的，限流和去重按它隔离；
// 留空则回退成 platform（按平台隔离）。
static NSString *const kAccount = @"";

// 全局开关，出问题时能快速停掉
static BOOL gEnabled = YES;

// ---------------------------------------------------------------- 工具

static CMessageMgr *MessageManager(void) {
    return [[objc_getClass("MMServiceCenter") defaultCenter]
        getService:objc_getClass("CMessageMgr")];
}

static CContactMgr *ContactManager(void) {
    return [[objc_getClass("MMServiceCenter") defaultCenter]
        getService:objc_getClass("CContactMgr")];
}

static NSString *DisplayNameForUser(NSString *wxid) {
    CContact *contact = [ContactManager() getContactByName:wxid];
    NSString *nick = contact.m_nsNickName;
    return nick.length > 0 ? nick : wxid;
}

static BOOL IsGroupChat(NSString *wxid) {
    // 微信群的 wxid 一律以 @chatroom 结尾，比查 contact 更可靠也更快
    return [wxid hasSuffix:@"@chatroom"];
}

/// 异步问规则服务：这条消息回不回、回什么。
/// 必须异步——这个 hook 跑在微信的消息线程上，同步网络请求会卡死 UI。
static void AskEngine(NSString *chatId,
                      NSString *chatName,
                      NSString *text,
                      BOOL isGroup,
                      BOOL mentionedMe,
                      void (^completion)(NSString *reply, double delay)) {
    NSURL *url = [NSURL URLWithString:kEngineURL];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    request.HTTPMethod = @"POST";
    request.timeoutInterval = 10;
    [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    [request setValue:[NSString stringWithFormat:@"Bearer %@", kEngineToken]
        forHTTPHeaderField:@"Authorization"];

    NSDictionary *payload = @{
        @"chat_id": chatId ?: @"",
        @"chat_name": chatName ?: @"",
        @"text": text ?: @"",
        @"sender_name": chatName ?: @"",
        @"is_group": @(isGroup),
        @"mentioned_me": @(mentionedMe),
        @"platform": @"ios",
        @"account": kAccount,
    };

    NSError *encodeError = nil;
    request.HTTPBody = [NSJSONSerialization dataWithJSONObject:payload
                                                       options:0
                                                         error:&encodeError];
    if (encodeError) {
        NSLog(@"[WXAutoReply] 请求编码失败: %@", encodeError);
        return;
    }

    NSURLSessionDataTask *task = [[NSURLSession sharedSession]
        dataTaskWithRequest:request
          completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
            if (error || !data) {
                NSLog(@"[WXAutoReply] 规则服务不可达，本条跳过: %@", error);
                return;
            }
            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data
                                                                 options:0
                                                                   error:nil];
            if (![json isKindOfClass:NSDictionary.class]) return;
            if (![json[@"should_reply"] boolValue]) {
                NSLog(@"[WXAutoReply] 不回复：%@", json[@"reason"]);
                return;
            }
            completion(json[@"text"], [json[@"delay_seconds"] doubleValue]);
          }];
    [task resume];
}

// ---------------------------------------------------------------- Hook

%hook CMessageMgr

// 微信收到新消息时会走这里。fromUsr 是会话 wxid（群聊就是群 id）。
- (void)AsyncOnAddMsg:(NSString *)fromUsr MsgWrap:(CMessageWrap *)msgWrap {
    %orig;  // 先放行原逻辑，保证消息正常入库和显示

    if (!gEnabled) return;
    if (!msgWrap || !fromUsr) return;

    // 只处理纯文本（type 1）。图片、语音、红包一律不碰。
    if (msgWrap.m_uiMessageType != 1) return;

    NSString *content = msgWrap.m_nsContent;
    if (content.length == 0) return;

    BOOL isGroup = IsGroupChat(fromUsr);

    // 群消息的 m_nsContent 形如 "wxid_xxx:\n真正的内容"，要剥掉前缀
    NSString *body = content;
    if (isGroup) {
        NSRange sep = [content rangeOfString:@":\n"];
        if (sep.location != NSNotFound) {
            body = [content substringFromIndex:sep.location + sep.length];
        }
    }

    // 不回自己发的消息，否则会和自己无限对话
    CContact *me = [ContactManager() getSelfContact];
    if ([fromUsr isEqualToString:me.m_nsUsrName]) return;

    // 公众号、服务通知一律不回
    CContact *peer = [ContactManager() getContactByName:fromUsr];
    if ([peer respondsToSelector:@selector(isBrandContact)] && [peer isBrandContact]) return;

    BOOL mentionedMe = NO;
    if (isGroup && me.m_nsNickName.length > 0) {
        mentionedMe = [body containsString:
            [NSString stringWithFormat:@"@%@", me.m_nsNickName]];
    }

    NSString *chatName = DisplayNameForUser(fromUsr);
    NSString *chatId = [NSString stringWithFormat:@"ios:%@", fromUsr];

    AskEngine(chatId, chatName, body, isGroup, mentionedMe, ^(NSString *reply, double delay) {
        if (reply.length == 0) return;
        // 延迟发送，避免秒回。规则服务已经算好了随机延迟。
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            NSLog(@"[WXAutoReply] -> %@: %@", chatName, reply);
            [MessageManager() SendTextMessage:me.m_nsUsrName toUsr:fromUsr msgText:reply];
        });
    });
}

%end

// ---------------------------------------------------------------- 入口

%ctor {
    @autoreleasepool {
        // 只在微信进程里生效，别去 hook 别的 App
        NSString *bundleId = NSBundle.mainBundle.bundleIdentifier;
        if (![bundleId isEqualToString:@"com.tencent.xin"]) return;

        NSNumber *flag = [NSUserDefaults.standardUserDefaults
            objectForKey:@"WXAutoReplyEnabled"];
        gEnabled = flag ? flag.boolValue : YES;

        NSLog(@"[WXAutoReply] 已加载，enabled=%d，引擎 %@", gEnabled, kEngineURL);
        %init;
    }
}
