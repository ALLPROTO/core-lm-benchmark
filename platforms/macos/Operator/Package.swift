// swift-tools-version: 5.9
import Foundation
import PackageDescription

let developerDirectory = ProcessInfo.processInfo.environment["DEVELOPER_DIR"]
    ?? "/Library/Developer/CommandLineTools"
let developerFrameworks =
    "\(developerDirectory)/Library/Developer/Frameworks"
let developerLibraries =
    "\(developerDirectory)/Library/Developer/usr/lib"
let standaloneTestingFramework =
    "\(developerFrameworks)/Testing.framework"
let usesStandaloneTestingFramework = FileManager.default.fileExists(
    atPath: standaloneTestingFramework
)
let testingSwiftSettings: [SwiftSetting] =
    usesStandaloneTestingFramework
    ? [.unsafeFlags(["-F", developerFrameworks])]
    : []
let testingLinkerSettings: [LinkerSetting] =
    usesStandaloneTestingFramework
    ? [
        .unsafeFlags([
            "-F", developerFrameworks,
            "-Xlinker", "-rpath",
            "-Xlinker", developerFrameworks,
            "-Xlinker", "-rpath",
            "-Xlinker", developerLibraries
        ]),
        .linkedFramework("Testing")
    ]
    : []

let package = Package(
    name: "CoreLMOperator",
    platforms: [.macOS(.v14)],
    products: [
        .executable(
            name: "CoreLMOperator",
            targets: ["CoreLMOperator"]
        ),
        .executable(
            name: "CoreLMOperatorCommandLauncher",
            targets: ["CoreLMOperatorCommandLauncher"]
        )
    ],
    targets: [
        .executableTarget(
            name: "CoreLMOperator",
            path: "Sources"
        ),
        .executableTarget(
            name: "CoreLMOperatorCommandLauncher",
            path: "CommandLauncher"
        ),
        .testTarget(
            name: "CoreLMOperatorTests",
            dependencies: [
                "CoreLMOperator",
                "CoreLMOperatorCommandLauncher"
            ],
            path: "Tests",
            swiftSettings: testingSwiftSettings,
            linkerSettings: testingLinkerSettings
        )
    ]
)
