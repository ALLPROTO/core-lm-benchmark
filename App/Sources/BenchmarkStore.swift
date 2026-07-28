import AppKit
import Foundation
import UniformTypeIdentifiers

@MainActor
final class BenchmarkStore: ObservableObject {
    @Published var settings = RunSettings()
    @Published var result: BenchmarkResult?
    @Published var savedRuns: [BenchmarkResult] = []
    @Published var isRunning = false
    @Published var progress = 0.0
    @Published var log = ["Benchmark dashboard ready."]
    @Published var errorMessage: String?

    private var process: Process?
    let scenarios = ["zero", "gaussian_bounded", "uniform_bounded", "impulse", "repeating_structured"]

    var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    var resultsDirectory: URL {
        if Bundle.main.bundleURL.pathExtension == "app" {
            let support = FileManager.default.urls(
                for: .applicationSupportDirectory, in: .userDomainMask
            ).first!
            return support
                .appendingPathComponent("CoreLMBenchmark", isDirectory: true)
                .appendingPathComponent("benchmark-results", isDirectory: true)
        }
        return projectDirectory.appendingPathComponent(
            "benchmark-results", isDirectory: true
        )
    }

    var pythonExecutable: URL {
        if let configured = ProcessInfo.processInfo.environment["PYTHON_BIN"],
           !configured.isEmpty {
            return URL(fileURLWithPath: configured)
        }
        let home = FileManager.default.homeDirectoryForCurrentUser
        let candidates = [
            home.appendingPathComponent(".pyenv/shims/python3"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/local/bin/python3")
        ]
        if let available = candidates.first(where: {
            FileManager.default.isExecutableFile(atPath: $0.path)
        }) {
            return available
        }
        return URL(fileURLWithPath: "/usr/bin/env")
    }

    var benchmarkScript: URL {
        if let resources = Bundle.main.resourceURL {
            let bundled = resources.appendingPathComponent(
                "BenchmarkCore/corelm_benchmark.py"
            )
            if FileManager.default.fileExists(atPath: bundled.path) {
                return bundled
            }
        }
        return projectDirectory.appendingPathComponent("BenchmarkCore/corelm_benchmark.py")
    }

    func moduleState() -> ModuleState {
        isRunning ? .running : (result == nil ? .ready : .complete)
    }

    func run() {
        guard !isRunning else { return }
        isRunning = true
        progress = 0.05
        errorMessage = nil
        log.append("Starting deterministic \(settings.scenario) run.")

        let task = Process()
        process = task
        task.executableURL = pythonExecutable
        task.currentDirectoryURL = benchmarkScript.deletingLastPathComponent()
        var arguments = [
            benchmarkScript.path,
            "--dimension", "\(settings.dimension)",
            "--steps", "\(settings.steps)",
            "--seed", "\(settings.seed)",
            "--scenario", settings.scenario,
            "--pca-components", "\(min(settings.pcaComponents, settings.dimension))",
            "--top-k", "\(min(settings.topK, settings.dimension))",
            "--qmax", "\(settings.qmax)",
            "--keyframe-interval", "\(settings.keyframeInterval)",
            "--minimum-compression-ratio", "\(settings.minimumCompressionRatio)",
            "--maximum-normalized-rmse", "\(settings.maximumNormalizedRMSE)",
            "--minimum-cosine-similarity", "\(settings.minimumCosineSimilarity)",
            "--maximum-energy-drift", "\(settings.maximumEnergyDrift)",
            "--output", resultsDirectory.path
        ]
        if pythonExecutable.path == "/usr/bin/env" {
            arguments.insert("python3", at: 0)
        }
        task.arguments = arguments
        let stdout = Pipe()
        let stderr = Pipe()
        task.standardOutput = stdout
        task.standardError = stderr
        task.terminationHandler = { [weak self] completed in
            let output = stdout.fileHandleForReading.readDataToEndOfFile()
            let error = stderr.fileHandleForReading.readDataToEndOfFile()
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.isRunning = false
                self.process = nil
                if completed.terminationStatus == 0 {
                    self.progress = 1
                    self.log.append(String(data: output, encoding: .utf8) ?? "Run complete.")
                    self.reloadSavedRuns()
                    self.result = self.savedRuns.first
                } else {
                    self.progress = 0
                    let message = String(data: error, encoding: .utf8) ?? "Benchmark failed."
                    self.errorMessage = message
                    self.log.append(message)
                }
            }
        }
        do {
            try FileManager.default.createDirectory(at: resultsDirectory, withIntermediateDirectories: true)
            try task.run()
            progress = 0.25
        } catch {
            isRunning = false
            process = nil
            errorMessage = error.localizedDescription
        }
    }

    func stop() {
        process?.terminate()
        log.append("Stop requested.")
    }

    func repeatRun() {
        guard result != nil else { return }
        run()
    }

    func reloadSavedRuns() {
        let files = (try? FileManager.default.contentsOfDirectory(
            at: resultsDirectory, includingPropertiesForKeys: nil
        )) ?? []
        let aggregateURL = resultsDirectory.appendingPathComponent("aggregate.json")
        var authoritativeRunIds: Set<String> = []
        if let data = try? Data(contentsOf: aggregateURL),
           let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let runIds = object["runIds"] as? [String] {
            authoritativeRunIds = Set(runIds)
        }
        savedRuns = files
            .filter { $0.pathExtension == "json" && $0.lastPathComponent != "aggregate.json" }
            .filter {
                authoritativeRunIds.isEmpty
                    || authoritativeRunIds.contains($0.deletingPathExtension().lastPathComponent)
            }
            .compactMap { try? JSONDecoder().decode(BenchmarkResult.self, from: Data(contentsOf: $0)) }
            .sorted { $0.createdAt > $1.createdAt }
    }

    func select(_ run: BenchmarkResult) {
        result = run
        settings.steps = run.configuration.steps
        settings.dimension = run.configuration.dimension
        settings.seed = run.configuration.seed
        settings.scenario = run.configuration.inputScenario
        settings.pcaComponents = run.configuration.pcaComponents ?? 8
        settings.topK = run.configuration.topK ?? 16
        settings.qmax = run.configuration.qmax ?? 127
        settings.keyframeInterval = run.configuration.keyframeInterval ?? 0
        if let thresholds = run.configuration.thresholds {
            settings.minimumCompressionRatio = thresholds.minimumCompressionRatio
            settings.maximumNormalizedRMSE = thresholds.maximumNormalizedRMSE
            settings.minimumCosineSimilarity = thresholds.minimumCosineSimilarity
            settings.maximumEnergyDrift = thresholds.maximumMeanEnergyRelativeDrift
        }
        log.append("Opened run \(run.runId).")
    }

    func openResult() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            select(try JSONDecoder().decode(BenchmarkResult.self, from: Data(contentsOf: url)))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveMarkdownReport() {
        guard let result else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = "\(result.runId).md"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let rows = result.methods.map {
            "| \($0.name) | \($0.payloadBytes) | \(String(format: "%.3f", $0.compressionRatio))× | "
            + "\(String(format: "%.6f", $0.normalizedRMSE)) | "
            + "\(String(format: "%.6f", $0.cosineSimilarity)) |"
        }.joined(separator: "\n")
        let report = """
        # Core LM Benchmark — \(result.runId)

        Verdict: **\(result.verdict.rawValue)**

        | Method | Payload bytes | Ratio | NRMSE | Cosine |
        |---|---:|---:|---:|---:|
        \(rows)

        Invariant violations: \(result.invariants.violations)
        Deterministic replay: \(result.invariants.deterministicReplay)
        """
        do {
            try report.write(to: url, atomically: true, encoding: .utf8)
            log.append("Saved report to \(url.path).")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func smokeRunIfRequested() async {
        guard CommandLine.arguments.contains("--smoke-run") else { return }
        try? await Task.sleep(for: .milliseconds(300))
        let visibleWindows = NSApplication.shared.windows.filter {
            $0.isVisible && $0.contentView != nil
        }
        let windowReady = visibleWindows.contains {
            $0.frame.width >= 1000 && $0.frame.height >= 650
        }
        settings.dimension = 32
        settings.steps = 200
        settings.seed = 7
        settings.scenario = "zero"
        settings.pcaComponents = 8
        settings.topK = 4
        settings.keyframeInterval = 0
        run()
        let deadline = Date().addingTimeInterval(20)
        while isRunning && Date() < deadline {
            try? await Task.sleep(for: .milliseconds(100))
        }
        let passed = !isRunning
            && errorMessage == nil
            && windowReady
            && result?.configuration.dimension == 32
            && result?.verdict == .pass
            && result?.invariants.deterministicReplay == true
        log.append(passed ? "SMOKE PASS" : "SMOKE FAIL")
        let summary: [String: Any] = [
            "status": passed ? "PASS" : "FAIL",
            "visibleWindows": visibleWindows.count,
            "windowReady": windowReady,
            "benchmarkRunId": result?.runId ?? "",
            "benchmarkVerdict": result?.verdict.rawValue ?? "",
            "deterministicReplay": result?.invariants.deterministicReplay ?? false,
            "error": errorMessage ?? ""
        ]
        if let data = try? JSONSerialization.data(
            withJSONObject: summary, options: [.prettyPrinted, .sortedKeys]
        ), let text = String(data: data, encoding: .utf8) {
            print(text)
        }
        fflush(stdout)
        exit(passed ? EXIT_SUCCESS : EXIT_FAILURE)
    }
}
