import XCTest
@testable import TraceMemoAutoReply

final class SettingsTests: XCTestCase {
    func testGrokStylePresetIsAcceptedBySettingsValidation() {
        var config = SafeConfig()
        config.personaStylePreset = "grok4_1"

        XCTAssertNil(config.validationError())
    }

    func testUnknownStylePresetIsRejectedBySettingsValidation() {
        var config = SafeConfig()
        config.personaStylePreset = "unknown"

        XCTAssertEqual(config.validationError(), "回复风格预设无效，请重新选择。")
    }

    func testOlderConfigPayloadDefaultsToCustomStyle() throws {
        let encoded = try JSONEncoder().encode(SafeConfig())
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        )
        object.removeValue(forKey: "personaStylePreset")
        let oldPayload = try JSONSerialization.data(withJSONObject: object)

        let decoded = try ConfigBridge.decode(oldPayload)

        XCTAssertEqual(decoded.personaStylePreset, "")
    }
}
