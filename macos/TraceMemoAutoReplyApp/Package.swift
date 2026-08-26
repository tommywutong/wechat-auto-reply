// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TraceMemoAutoReplyApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "TraceMemoAutoReply", targets: ["TraceMemoAutoReply"])
    ],
    targets: [
        .executableTarget(
            name: "TraceMemoAutoReply",
            path: "Sources"
        ),
        .testTarget(
            name: "TraceMemoAutoReplyTests",
            dependencies: ["TraceMemoAutoReply"],
            path: "Tests"
        )
    ]
)
