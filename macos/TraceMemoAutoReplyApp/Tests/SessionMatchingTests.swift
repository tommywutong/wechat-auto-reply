import XCTest
@testable import TraceMemoAutoReply

final class SessionMatchingTests: XCTestCase {
    func testDisplayNameNormalizationHandlesPunctuationAndMemberCount() {
        XCTAssertEqual(normalizeSessionName("real."), normalizeSessionName("real"))
        XCTAssertEqual(normalizeSessionName("项目组（35）"), normalizeSessionName("项目组"))
        XCTAssertEqual(normalizeSessionName("  Loky  "), "loky")
    }

    func testRecentCatalogLimitsCombinedPrivateAndGroupSessionsAndSearchesAll() {
        let recent = (0..<35).map { index in
            TraceMemoSession(
                talker: "wxid-\(index)",
                name: "会话 \(index)",
                aliases: [],
                isGroup: index % 2 == 0,
                isOfficialAccount: false,
                isFolded: false,
                isMuted: false,
                recentRank: index
            )
        }
        let official = TraceMemoSession(
            talker: "gh-official",
            name: "公众号",
            aliases: [],
            isGroup: false,
            isOfficialAccount: true,
            isFolded: false,
            isMuted: false,
            recentRank: 0
        )

        let latest = SessionCatalog.filter(recent + [official], query: "", kind: "all")
        XCTAssertEqual(latest.count, 30)
        XCTAssertFalse(latest.contains { $0.isOfficialAccount })
        XCTAssertEqual(latest.last?.talker, "wxid-29")

        let searched = SessionCatalog.filter(recent + [official], query: "会话 34", kind: "all")
        XCTAssertEqual(searched.map(\.talker), ["wxid-34"])
    }

    func testRepositoryDiscoveryAcceptsProjectBeforePersonalConfigExists() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(
            at: directory.appendingPathComponent("scripts"),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: directory.appendingPathComponent("core"),
            withIntermediateDirectories: true
        )
        FileManager.default.createFile(
            atPath: directory.appendingPathComponent("scripts/run-tracememo-autoreply.sh").path,
            contents: Data()
        )
        FileManager.default.createFile(
            atPath: directory.appendingPathComponent("core/config.ai.example.yaml").path,
            contents: Data()
        )

        XCTAssertTrue(AppPaths.isRepository(directory))
    }

    @MainActor
    func testAllowedSessionFallbackDoesNotDoubleCountLegacyNames() {
        let model = AppModel()
        model.config.allowTalkers = ["wxid-a", "wxid-b"]
        model.config.allowContacts = ["甲", "乙"]

        XCTAssertEqual(model.allowedSessionCount, 2)
    }
}
