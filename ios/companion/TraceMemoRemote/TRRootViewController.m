#import "TRRootViewController.h"
#import "TRAppState.h"

@interface TRRootViewController () <UITextFieldDelegate>
@property (nonatomic, strong) TRAppState *state;
@property (nonatomic, strong) UIScrollView *scrollView;
@property (nonatomic, strong) UIStackView *stack;
@property (nonatomic, strong) UILabel *connectionLabel;
@property (nonatomic, strong) UILabel *engineLabel;
@property (nonatomic, strong) UILabel *replyLabel;
@property (nonatomic, strong) UILabel *traceMemoLabel;
@property (nonatomic, strong) UILabel *errorLabel;
@property (nonatomic, strong) UITextView *logsView;
@property (nonatomic, strong) UITextField *hostField;
@property (nonatomic, strong) UITextField *portField;
@property (nonatomic, strong) UITextField *pairingField;
@property (nonatomic, strong) UITextField *pollIntervalField;
@property (nonatomic, strong) UITextView *allowListView;
@property (nonatomic, strong) UITextView *toneView;
@property (nonatomic, strong) NSTimer *refreshTimer;
@property (nonatomic, strong) NSArray<UIButton *> *serviceButtons;
@property (nonatomic, strong) NSArray<UIButton *> *connectionButtons;
@property (nonatomic, strong) UIButton *saveSettingsButton;
@property (nonatomic, assign) BOOL requestInFlight;
@end

static UIColor *TRTint(void) { return [UIColor colorWithRed:0.08 green:0.48 blue:0.36 alpha:1.0]; }

@implementation TRRootViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.state = [TRAppState shared];
    self.view.backgroundColor = [UIColor systemGroupedBackgroundColor];
    self.title = @"TraceMemo 控制台";
    self.navigationItem.largeTitleDisplayMode = UINavigationItemLargeTitleDisplayModeAlways;
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemRefresh target:self action:@selector(refresh)];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(stateChanged) name:TRAppStateDidChangeNotification object:self.state];
    [self buildView];
    [self refreshUI];
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    [self refresh];
    [self.refreshTimer invalidate];
    self.refreshTimer = [NSTimer scheduledTimerWithTimeInterval:8.0 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
}

- (void)viewDidDisappear:(BOOL)animated {
    [super viewDidDisappear:animated];
    [self.refreshTimer invalidate];
    self.refreshTimer = nil;
}

- (void)dealloc {
    [[NSNotificationCenter defaultCenter] removeObserver:self];
}

- (void)buildView {
    self.scrollView = [UIScrollView new];
    self.scrollView.alwaysBounceVertical = YES;
    self.scrollView.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    [self.view addSubview:self.scrollView];
    self.scrollView.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [self.scrollView.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
        [self.scrollView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.scrollView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.scrollView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor]
    ]];

    self.stack = [[UIStackView alloc] initWithArrangedSubviews:@[]];
    self.stack.axis = UILayoutConstraintAxisVertical;
    self.stack.spacing = 16;
    self.stack.layoutMargins = UIEdgeInsetsMake(20, 20, 32, 20);
    self.stack.layoutMarginsRelativeArrangement = YES;
    [self.scrollView addSubview:self.stack];
    self.stack.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [self.stack.topAnchor constraintEqualToAnchor:self.scrollView.contentLayoutGuide.topAnchor],
        [self.stack.leadingAnchor constraintEqualToAnchor:self.scrollView.contentLayoutGuide.leadingAnchor],
        [self.stack.trailingAnchor constraintEqualToAnchor:self.scrollView.contentLayoutGuide.trailingAnchor],
        [self.stack.bottomAnchor constraintEqualToAnchor:self.scrollView.contentLayoutGuide.bottomAnchor],
        [self.stack.widthAnchor constraintEqualToAnchor:self.scrollView.frameLayoutGuide.widthAnchor]
    ]];

    UILabel *subtitle = [self label:@"iPhone 只负责控制 Mac，微信和 AI 仍在 Mac 本机运行。" font:[UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline] color:[UIColor secondaryLabelColor]];
    subtitle.numberOfLines = 0;
    [self.stack addArrangedSubview:subtitle];

    [self addSectionTitle:@"连接状态"];
    self.connectionLabel = [self label:@"未连接 Mac" font:[UIFont preferredFontForTextStyle:UIFontTextStyleHeadline] color:[UIColor labelColor]];
    self.connectionLabel.numberOfLines = 0;
    [self.stack addArrangedSubview:self.connectionLabel];
    [self buildConnectionForm];

    [self addSectionTitle:@"服务"];
    self.engineLabel = [self label:@"规则服务：未知" font:nil color:[UIColor labelColor]];
    self.replyLabel = [self label:@"自动回复：未知" font:nil color:[UIColor labelColor]];
    self.traceMemoLabel = [self label:@"控制服务：未知" font:nil color:[UIColor labelColor]];
    [self.stack addArrangedSubview:self.engineLabel];
    [self.stack addArrangedSubview:self.replyLabel];
    [self.stack addArrangedSubview:self.traceMemoLabel];
    UIStackView *serviceButtons = [[UIStackView alloc] initWithArrangedSubviews:@[
        [self button:@"启动" action:@selector(startService)],
        [self stopButton],
        [self button:@"重启" action:@selector(restartService)]
    ]];
    serviceButtons.axis = UILayoutConstraintAxisHorizontal;
    serviceButtons.spacing = 10;
    for (UIButton *button in serviceButtons.arrangedSubviews) [button.widthAnchor constraintGreaterThanOrEqualToConstant:86].active = YES;
    [self.stack addArrangedSubview:serviceButtons];
    self.serviceButtons = [serviceButtons.arrangedSubviews copy];

    [self addSectionTitle:@"自动回复设置"];
    [self.stack addArrangedSubview:[self label:@"轮询间隔（秒）" font:nil color:[UIColor secondaryLabelColor]]];
    self.pollIntervalField = [self field:@"5" keyboard:UIKeyboardTypeNumberPad];
    [self.stack addArrangedSubview:self.pollIntervalField];
    [self.stack addArrangedSubview:[self label:@"私信白名单，用逗号或换行分隔" font:nil color:[UIColor secondaryLabelColor]]];
    self.allowListView = [self textView:@"例如：Biscoffee, Loky" height:72];
    [self.stack addArrangedSubview:self.allowListView];
    [self.stack addArrangedSubview:[self label:@"回复风格补充说明" font:nil color:[UIColor secondaryLabelColor]]];
    self.toneView = [self textView:@"例如：简短、口语化，不主动承诺做不到的事情" height:92];
    [self.stack addArrangedSubview:self.toneView];
    self.saveSettingsButton = [self button:@"保存设置并重启服务" action:@selector(saveSettings)];
    [self.stack addArrangedSubview:self.saveSettingsButton];

    [self addSectionTitle:@"运行日志"];
    self.logsView = [self textView:@"暂无日志" height:220];
    self.logsView.editable = NO;
    self.logsView.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    self.logsView.accessibilityLabel = @"运行日志";
    [self.stack addArrangedSubview:self.logsView];
    self.errorLabel = [self label:@"" font:[UIFont preferredFontForTextStyle:UIFontTextStyleFootnote] color:[UIColor systemRedColor]];
    self.errorLabel.numberOfLines = 0;
    [self.stack addArrangedSubview:self.errorLabel];
}

- (void)buildConnectionForm {
    self.hostField = [self field:@"Mac 地址，例如 MacBook.local 或 192.168.1.8" keyboard:UIKeyboardTypeURL];
    self.hostField.text = self.state.host ?: @"";
    self.portField = [self field:@"端口，默认 8850" keyboard:UIKeyboardTypeNumberPad];
    self.portField.text = self.state.port > 0 ? [NSString stringWithFormat:@"%ld", (long)self.state.port] : @"8850";
    self.pairingField = [self field:@"配对码（Mac 端安装时显示）" keyboard:UIKeyboardTypeASCIICapable];
    [self.stack addArrangedSubview:self.hostField];
    [self.stack addArrangedSubview:self.portField];
    [self.stack addArrangedSubview:self.pairingField];
    UIButton *pair = [self button:@"连接并保存" action:@selector(pair)];
    [self.stack addArrangedSubview:pair];
    UIButton *disconnect = [self button:@"断开当前 Mac" action:@selector(disconnect)];
    disconnect.tintColor = [UIColor systemRedColor];
    [self.stack addArrangedSubview:disconnect];
    self.connectionButtons = @[pair, disconnect];
}

- (void)addSectionTitle:(NSString *)title {
    UILabel *label = [self label:title font:[UIFont preferredFontForTextStyle:UIFontTextStyleTitle3] color:[UIColor labelColor]];
    label.accessibilityTraits = UIAccessibilityTraitHeader;
    [self.stack addArrangedSubview:label];
}

- (UILabel *)label:(NSString *)text font:(UIFont *)font color:(UIColor *)color {
    UILabel *label = [UILabel new];
    label.text = text;
    label.font = font ?: [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    label.textColor = color;
    return label;
}

- (UITextField *)field:(NSString *)placeholder keyboard:(UIKeyboardType)keyboard {
    UITextField *field = [UITextField new];
    field.placeholder = placeholder;
    field.borderStyle = UITextBorderStyleRoundedRect;
    field.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    field.keyboardType = keyboard;
    field.clearButtonMode = UITextFieldViewModeWhileEditing;
    [field.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    return field;
}

- (UITextView *)textView:(NSString *)placeholder height:(CGFloat)height {
    UITextView *view = [UITextView new];
    view.text = @"";
    view.backgroundColor = [UIColor secondarySystemGroupedBackgroundColor];
    view.layer.cornerRadius = 10;
    view.layer.borderWidth = 0.5;
    view.layer.borderColor = [UIColor separatorColor].CGColor;
    view.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    view.textContainerInset = UIEdgeInsetsMake(10, 8, 10, 8);
    view.accessibilityLabel = placeholder;
    [view.heightAnchor constraintEqualToConstant:height].active = YES;
    return view;
}

- (UIButton *)button:(NSString *)title action:(SEL)action {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    button.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    UIButtonConfiguration *configuration = [UIButtonConfiguration filledButtonConfiguration];
    configuration.baseBackgroundColor = TRTint();
    configuration.baseForegroundColor = UIColor.whiteColor;
    configuration.contentInsets = NSDirectionalEdgeInsetsMake(11, 14, 11, 14);
    button.configuration = configuration;
    button.layer.cornerRadius = 10;
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (UIButton *)stopButton {
    UIButton *button = [self button:@"停止" action:@selector(stopService)];
    button.configuration.baseBackgroundColor = [UIColor systemRedColor];
    return button;
}

- (void)refresh { [self.state refreshAll]; [self refreshUI]; }
- (void)stateChanged { [self refreshUI]; }

- (void)refreshUI {
    BOOL connected = self.state.token.length > 0 && self.state.host.length > 0;
    self.connectionLabel.text = connected ? [NSString stringWithFormat:@"已连接 %@:%ld", self.state.host, (long)self.state.port] : @"未连接 Mac，请输入地址和配对码";
    NSDictionary *services = self.state.status[@"services"];
    self.engineLabel.text = [NSString stringWithFormat:@"规则服务：%@", [self displayState:services[@"engine"]]];
    self.replyLabel.text = [NSString stringWithFormat:@"自动回复：%@", [self displayState:services[@"autoreply"]]];
    self.traceMemoLabel.text = [NSString stringWithFormat:@"控制服务：%@", connected ? @"已连接" : @"未连接"];
    NSDictionary *config = self.state.config;
    if (config.count > 0) {
        if (!self.pollIntervalField.isFirstResponder) self.pollIntervalField.text = [NSString stringWithFormat:@"%@", config[@"pollInterval"] ?: @"5"];
        NSArray *allow = [config[@"allowContacts"] isKindOfClass:NSArray.class] ? config[@"allowContacts"] : @[];
        if (!self.allowListView.isFirstResponder) self.allowListView.text = [allow componentsJoinedByString:@", "];
        if (!self.toneView.isFirstResponder) self.toneView.text = [config[@"personaTone"] isKindOfClass:NSString.class] ? config[@"personaTone"] : @"";
    }
    self.logsView.text = self.state.logs.count ? [self.state.logs componentsJoinedByString:@"\n"] : @"暂无日志";
    if (self.logsView.text.length > 0) [self.logsView scrollRangeToVisible:NSMakeRange(self.logsView.text.length - 1, 1)];
    self.errorLabel.text = self.state.lastError;
}

- (NSString *)displayState:(id)value {
    if ([value isEqual:@"running"]) return @"运行中";
    if ([value isEqual:@"stopped"]) return @"已停止";
    if ([value isEqual:@"not_installed"]) return @"未安装";
    return value ? [value description] : @"未知";
}

- (void)pair {
    if (self.requestInFlight) return;
    NSString *host = [self.hostField.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSInteger port = self.portField.text.integerValue;
    if (port == 0 && self.portField.text.length == 0) port = 8850;
    NSString *code = [self.pairingField.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (host.length == 0 || code.length == 0) { self.errorLabel.text = @"请填写 Mac 地址和配对码。"; return; }
    if (port < 1 || port > 65535) { self.errorLabel.text = @"端口必须在 1 到 65535 之间。"; return; }
    self.state.host = host;
    self.state.port = port;
    [self.view endEditing:YES];
    self.errorLabel.text = @"正在连接…";
    self.requestInFlight = YES;
    [self setControlsEnabled:NO];
    [self.state pairWithCode:code completion:^(NSError *error) {
        self.requestInFlight = NO;
        [self setControlsEnabled:YES];
        self.errorLabel.text = error.localizedDescription ?: @"已连接 Mac。";
        if (!error) { self.pairingField.text = @""; [self refresh]; }
    }];
}

- (void)disconnect {
    if (self.requestInFlight) return;
    [self.state disconnect];
    [self refreshUI];
}
- (void)startService { [self action:@"start"]; }
- (void)stopService {
    if (self.requestInFlight) return;
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"停止自动回复？"
                                                                       message:@"停止后，Mac 将不再轮询或发送新的自动回复。"
                                                                preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"停止服务" style:UIAlertActionStyleDestructive handler:^(__unused UIAlertAction *action) {
        [self action:@"stop"];
    }]];
    [self presentViewController:alert animated:YES completion:nil];
}
- (void)restartService { [self action:@"restart"]; }

- (void)action:(NSString *)action {
    if (self.requestInFlight) return;
    self.requestInFlight = YES;
    [self setControlsEnabled:NO];
    [self.state serviceAction:action completion:^(NSError *error) {
        self.requestInFlight = NO;
        [self setControlsEnabled:YES];
        self.errorLabel.text = error.localizedDescription ?: @"操作完成";
        [self refreshUI];
    }];
}

- (void)saveSettings {
    if (self.requestInFlight) return;
    NSInteger poll = MAX(5, MIN(self.pollIntervalField.text.integerValue ?: 5, 300));
    NSMutableArray *allow = [NSMutableArray array];
    for (NSString *part in [self.allowListView.text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        for (NSString *value in [part componentsSeparatedByString:@","]) {
            NSString *clean = [value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
            if (clean.length > 0 && ![allow containsObject:clean]) [allow addObject:clean];
        }
    }
    NSDictionary *values = @{
        @"pollInterval": @(poll),
        @"allowContacts": allow,
        @"personaTone": self.toneView.text ?: @""
    };
    [self.view endEditing:YES];
    self.errorLabel.text = @"正在保存并重启…";
    self.requestInFlight = YES;
    [self setControlsEnabled:NO];
    [self.state updateConfig:values completion:^(NSError *error) {
        self.requestInFlight = NO;
        [self setControlsEnabled:YES];
        self.errorLabel.text = error.localizedDescription ?: @"设置已保存，服务已重启。";
        [self refreshUI];
    }];
}

- (void)setControlsEnabled:(BOOL)enabled {
    self.hostField.enabled = enabled;
    self.portField.enabled = enabled;
    self.pairingField.enabled = enabled;
    self.pollIntervalField.enabled = enabled;
    self.allowListView.editable = enabled;
    self.toneView.editable = enabled;
    self.saveSettingsButton.enabled = enabled;
    for (UIButton *button in self.connectionButtons) button.enabled = enabled;
    for (UIButton *button in self.serviceButtons) button.enabled = enabled;
}

@end
