#import "TRSceneDelegate.h"
#import "TRRootViewController.h"

@implementation TRSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    UIWindowScene *windowScene = (UIWindowScene *)scene;
    self.window = [[UIWindow alloc] initWithWindowScene:windowScene];
    UINavigationController *navigationController = [[UINavigationController alloc] initWithRootViewController:[TRRootViewController new]];
    navigationController.navigationBar.prefersLargeTitles = YES;
    self.window.rootViewController = navigationController;
    [self.window makeKeyAndVisible];
}
@end
