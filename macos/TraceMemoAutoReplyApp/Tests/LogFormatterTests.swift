import XCTest
@testable import TraceMemoAutoReply

final class LogFormatterTests: XCTestCase {
    func testInfoOnStderrRemainsOrdinaryLog() {
        let result = LogFormatter.merge(
            stdout: "",
            stderr: "2026-08-26 10:00:00,000 INFO 状态：运行中"
        )

        XCTAssertEqual(result, ["2026-08-26 10:00:00,000 INFO 状态：运行中"])
    }

    func testWarningAndErrorReceiveDistinctMarkers() {
        let result = LogFormatter.merge(
            stdout: "",
            stderr: "2026-08-26 WARNING 等待重试\n2026-08-26 ERROR 发送失败"
        )

        XCTAssertEqual(
            result,
            [
                "[警告] 2026-08-26 WARNING 等待重试",
                "[错误] 2026-08-26 ERROR 发送失败",
            ]
        )
    }

    func testUnstructuredStderrStillReceivesErrorMarker() {
        XCTAssertEqual(
            LogFormatter.merge(stdout: "", stderr: "进程异常退出"),
            ["[错误] 进程异常退出"]
        )
    }
}
