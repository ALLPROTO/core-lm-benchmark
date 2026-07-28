// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CoreLMBenchmark",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "CoreLMBenchmarkApp", targets: ["CoreLMBenchmarkApp"])],
    targets: [
        .executableTarget(name: "CoreLMBenchmarkApp", path: "App/Sources")
    ]
)
