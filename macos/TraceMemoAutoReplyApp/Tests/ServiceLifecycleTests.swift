import XCTest
@testable import TraceMemoAutoReply

final class ServiceLifecycleTests: XCTestCase {
    func testBundleIsRunningOnlyWhenBothServicesRun() {
        let state = ServiceBundleState(engine: .running, autoreply: .running)

        XCTAssertEqual(state.overall, .running)
        XCTAssertTrue(state.allRunning)
        XCTAssertTrue(state.anyRunning)
    }

    func testBundleReportsPartialWhenOnlyOneServiceRuns() {
        let state = ServiceBundleState(engine: .running, autoreply: .stopped)

        XCTAssertEqual(state.overall, .partial)
        XCTAssertFalse(state.allRunning)
        XCTAssertTrue(state.anyRunning)
    }

    func testBundleDistinguishesStoppedAndMissingServices() {
        XCTAssertEqual(
            ServiceBundleState(engine: .stopped, autoreply: .stopped).overall,
            .stopped
        )
        XCTAssertEqual(
            ServiceBundleState(engine: .notInstalled, autoreply: .notInstalled).overall,
            .notInstalled
        )
        XCTAssertTrue(
            ServiceBundleState(engine: .stopped, autoreply: .notInstalled).allInactive
        )
        XCTAssertFalse(
            ServiceBundleState(engine: .unknown("检查失败"), autoreply: .stopped).allInactive
        )
    }

    func testServiceOrderProtectsPollerDependencies() {
        XCTAssertEqual(
            ServiceController.labels(for: .start),
            [AppPaths.engineServiceLabel, AppPaths.serviceLabel]
        )
        XCTAssertEqual(
            ServiceController.labels(for: .restart),
            [AppPaths.engineServiceLabel, AppPaths.serviceLabel]
        )
        XCTAssertEqual(
            ServiceController.labels(for: .stop),
            [AppPaths.serviceLabel, AppPaths.engineServiceLabel]
        )
        XCTAssertEqual(
            ServiceController.operations(for: .restart),
            [
                ServiceOperation(action: .stop, label: AppPaths.serviceLabel),
                ServiceOperation(action: .stop, label: AppPaths.engineServiceLabel),
                ServiceOperation(action: .start, label: AppPaths.engineServiceLabel),
                ServiceOperation(action: .start, label: AppPaths.serviceLabel),
            ]
        )
    }
}
