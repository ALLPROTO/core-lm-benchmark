import AppKit
import CoreFoundation
import Darwin
import Dispatch
import Foundation
import UniformTypeIdentifiers

private struct ValidatedPythonRuntime {
    let executableURL: URL
    let sha256: String
}

enum PortfolioCaptureRequest: Equatable {
    case none
    case preflight
    case live
    case result(runIdentifier: String, readyFilePath: String)
    case invalid

    init(arguments: [String]) {
        let payload = Array(arguments.dropFirst())
        let captureCount = arguments.filter {
            $0 == "--portfolio-capture"
        }.count
        let preflightCount = arguments.filter {
            $0 == "--portfolio-capture-preflight"
        }.count
        let liveCount = arguments.filter {
            $0 == "--portfolio-capture-live"
        }.count
        let resultFlagIndices = arguments.indices.filter {
            arguments[$0] == "--portfolio-result-id"
        }
        let readyFlagIndices = arguments.indices.filter {
            arguments[$0] == "--portfolio-ready-file"
        }
        let conflicts = [
            "--automated-compression-proof",
            "--app-launch-check",
            "--proof-challenge"
        ].contains { arguments.contains($0) }
        let mentionsCapture = captureCount > 0
            || preflightCount > 0
            || liveCount > 0
            || !resultFlagIndices.isEmpty
            || !readyFlagIndices.isEmpty

        guard mentionsCapture else {
            self = .none
            return
        }
        guard !conflicts else {
            self = .invalid
            return
        }
        if preflightCount == 1,
           captureCount == 0,
           liveCount == 0,
           resultFlagIndices.isEmpty,
           readyFlagIndices.isEmpty,
           payload == ["--portfolio-capture-preflight"] {
            self = .preflight
            return
        }
        if liveCount == 1,
           captureCount == 0,
           preflightCount == 0,
           resultFlagIndices.isEmpty,
           readyFlagIndices.isEmpty,
           payload == ["--portfolio-capture-live"] {
            self = .live
            return
        }
        guard preflightCount == 0,
              liveCount == 0,
              captureCount == 1,
              resultFlagIndices.count == 1,
              readyFlagIndices.count == 1,
              payload.count == 5,
              payload[0] == "--portfolio-capture",
              payload[1] == "--portfolio-result-id",
              payload[3] == "--portfolio-ready-file" else {
            self = .invalid
            return
        }
        let flagIndex = resultFlagIndices[0]
        guard flagIndex + 1 < arguments.count else {
            self = .invalid
            return
        }
        let identifier = arguments[flagIndex + 1]
        guard let uuid = UUID(uuidString: identifier),
              uuid.uuidString.lowercased() == identifier else {
            self = .invalid
            return
        }
        let readyFilePath = payload[4]
        let readyFileURL = URL(fileURLWithPath: readyFilePath)
        guard readyFilePath.hasPrefix("/"),
              readyFilePath != "/",
              readyFilePath.utf8.count <= 4_096,
              !readyFilePath.utf8.contains(0),
              readyFileURL.standardizedFileURL.path == readyFilePath,
              readyFileURL.lastPathComponent != ".",
              readyFileURL.lastPathComponent != "..",
              !readyFileURL.lastPathComponent.isEmpty else {
            self = .invalid
            return
        }
        self = .result(
            runIdentifier: identifier,
            readyFilePath: readyFilePath
        )
    }

    var isCaptureMode: Bool {
        self != .none
    }

    var isPreflight: Bool {
        self == .preflight
    }

    var isLive: Bool {
        self == .live
    }
}

struct PortfolioCaptureSnapshot: Equatable {
    let sourceTag: String
    let sourceCommit: String
    let sourceTree: String
    let challengeSHA256: String
    let runIdentifier: String
    let resultSHA256: String
    let metricVerdict: String
    let compressionRatioVsBF16: Double
    let deltaNLLNatPerToken: Double
    let top1Agreement: Double
    let moduleState: String
    let heavyReplayState: String
    let verifierState: String
    let structuralVerdict: String
    let replayVerdict: String
    let terminalVerdict: String
    let resultFileSHA256: String
    let receiptFileSHA256: String
    let buildProvenanceSHA256: String
    let applicationExecutableSHA256: String
}

private struct PortfolioCaptureReportBytes {
    let structural: Data?
    let replay: Data?
    let terminal: Data?
}

enum ProcessGroupSupervisor {
    private static func isSafeGroupID(_ groupID: pid_t) -> Bool {
        groupID > 1 && groupID != getpgrp()
    }

    static func groupExists(_ groupID: pid_t) -> Bool {
        guard isSafeGroupID(groupID) else { return false }
        errno = 0
        if kill(-groupID, 0) == 0 {
            return true
        }
        return errno == EPERM
    }

    @discardableResult
    static func signal(_ signal: Int32, groupID: pid_t) -> Bool {
        guard isSafeGroupID(groupID) else { return false }
        return kill(-groupID, signal) == 0
    }

    @discardableResult
    static func forceKillIfPresent(_ groupID: pid_t) -> Bool {
        guard groupExists(groupID) else { return false }
        return signal(SIGKILL, groupID: groupID)
    }
}

@MainActor
final class BenchmarkStore: ObservableObject {
    @Published var isRunning = false
    @Published var progress = 0.0
    @Published private(set) var log = ["Core LM Benchmark ready."]
    @Published var errorMessage: String?
    @Published var realLLMSettings = RealLLMRunSettings()
    @Published var realLLMResult: RealLLMResult?
    @Published var realLLMVerified = false
    @Published var realLLMVerificationMessage = "No proof run"
    @Published var realLLMResultURL: URL?
    @Published private(set) var portfolioCaptureSnapshot:
        PortfolioCaptureSnapshot?
    @Published private(set) var portfolioCaptureStatusCode: String

    private var process: Process?
    private var activeProcessGroupID: pid_t?
    private var realLLMPowerActivity: NSObjectProtocol?
    private var realLLMTimeoutTask: Task<Void, Never>?
    private var memoryPressureSource: DispatchSourceMemoryPressure?
    private var forcedRealLLMFailure: String?
    private var realLLMStartedAt: Date?
    private var activeRealLLMPythonSHA256: String?
    private var activeRealLLMScriptURL: URL?
    private var portfolioReadinessPublishing = false
    private var portfolioReadinessPublished = false
    private(set) var lastRealLLMWorkerPID: Int32?
    let portfolioCaptureRequest: PortfolioCaptureRequest
    private let commandLineArguments: [String]
    private let proofChallengeRequested: Bool
    private let proofChallengeNonce: String?
    static let realLLMHardTimeoutSeconds: UInt64 = 300
    static let mpsHighWatermarkRatio = "0.85"
    static let mpsLowWatermarkRatio = "0.75"

    init(commandLineArguments: [String] = CommandLine.arguments) {
        self.commandLineArguments = commandLineArguments
        portfolioCaptureRequest = PortfolioCaptureRequest(
            arguments: commandLineArguments
        )
        proofChallengeRequested = commandLineArguments.contains(
            "--proof-challenge"
        )
        if let index = commandLineArguments.firstIndex(
            of: "--proof-challenge"
        ), index + 1 < commandLineArguments.count,
           SecurityValidation.isLowercaseSHA256(
               commandLineArguments[index + 1]
           ) {
            proofChallengeNonce = commandLineArguments[index + 1]
        } else {
            proofChallengeNonce = nil
        }
        switch portfolioCaptureRequest {
        case .preflight:
            portfolioCaptureStatusCode = "AUTOMATED CAPTURE PREFLIGHT"
        case .live:
            portfolioCaptureStatusCode = "AUTOMATED VALIDATION IN PROGRESS"
        case .result:
            portfolioCaptureStatusCode = "CAPTURE_RESULT_LOADING"
        case .invalid:
            portfolioCaptureStatusCode = "CAPTURE_ARGUMENTS_INVALID"
        case .none:
            portfolioCaptureStatusCode = "CAPTURE_DISABLED"
        }
    }

    var portfolioCaptureRequested: Bool {
        portfolioCaptureRequest.isCaptureMode
    }

    var portfolioCaptureIsPreflight: Bool {
        portfolioCaptureRequest.isPreflight
    }

    var portfolioCaptureIsLive: Bool {
        portfolioCaptureRequest.isLive
    }
    var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    var realLLMResultsDirectory: URL {
        let support = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first!
        return support
            .appendingPathComponent("CoreLMBenchmark", isDirectory: true)
            .appendingPathComponent("real-llm-results", isDirectory: true)
    }

    static func realLLMWorkerEnvironment(
        cache: URL,
        supervisionFile: URL? = nil
    ) -> [String: String] {
        var additions = [
                "HF_HOME": cache.path,
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "HF_HUB_DISABLE_PROGRESS_BARS": "1",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "PYTORCH_MPS_HIGH_WATERMARK_RATIO": mpsHighWatermarkRatio,
                "PYTORCH_MPS_LOW_WATERMARK_RATIO": mpsLowWatermarkRatio,
                "OMP_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2",
                "MKL_NUM_THREADS": "2",
                "VECLIB_MAXIMUM_THREADS": "2",
                "NUMEXPR_NUM_THREADS": "2"
        ]
        if let supervisionFile {
            additions["CORELM_WORKER_GROUP_FILE"] = supervisionFile.path
        }
        return SecurityValidation.sanitizedChildEnvironment(
            additions: additions
        )
    }

    private func resolvePackagedPythonRuntime()
        throws -> ValidatedPythonRuntime
    {
        guard Bundle.main.bundleURL.pathExtension == "app" else {
            throw SecurityValidationError.invalid(
                "A packaged Python runtime was requested outside an app bundle."
            )
        }
        try SecurityValidation.validateBundleSignature(Bundle.main.bundleURL)
        guard let resources = Bundle.main.resourceURL else {
            throw SecurityValidationError.invalid(
                "The signed application resources are unavailable."
            )
        }
        let manifest = try SecurityValidation.validateRegularFileInside(
            resources.appendingPathComponent(
                "python-runtime-manifest.json"
            ),
            root: resources
        )
        let identity = try SecurityValidation.pythonRuntimeIdentity(
            from: manifest
        )
        let python = try SecurityValidation.validateExecutable(
            identity.declaredURL,
            expectedSHA256: identity.executableSHA256
        )
        guard python.resolvingSymlinksInPath().standardizedFileURL
                == identity.resolvedURL else {
            throw SecurityValidationError.invalid(
                "Python executable resolution differs from the signed manifest."
            )
        }
        try SecurityValidation.validatePythonRuntimeManifest(
            at: manifest,
            expectedPythonURL: python
        )
        return ValidatedPythonRuntime(
            executableURL: python,
            sha256: identity.executableSHA256
        )
    }

    private func executableDigest(_ url: URL) throws -> String {
        let resolved = url.resolvingSymlinksInPath().standardizedFileURL
        return SecurityValidation.sha256Hex(
            try SecurityValidation.readRegularFile(
                at: resolved,
                maximumBytes: 256 * 1024 * 1024,
                requireCurrentOwner: false
            )
        )
    }

    private func resolveRealLLMPythonExecutable()
        throws -> ValidatedPythonRuntime
    {
        if Bundle.main.bundleURL.pathExtension == "app" {
            return try resolvePackagedPythonRuntime()
        }
        #if DEBUG
        if let configured = ProcessInfo.processInfo.environment["CORELM_REAL_LLM_PYTHON"],
           !configured.isEmpty {
            let validated = try SecurityValidation.validateExecutable(
                URL(fileURLWithPath: configured),
                expectedSHA256: nil
            )
            return ValidatedPythonRuntime(
                executableURL: validated,
                sha256: try executableDigest(validated)
            )
        }
        #endif
        let candidate = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(
                ".cache/corelm/macos/runtime/bin/python"
            )
        let validated = try SecurityValidation.validateExecutable(
            candidate,
            expectedSHA256: nil
        )
        return ValidatedPythonRuntime(
            executableURL: validated,
            sha256: try executableDigest(validated)
        )
    }

    private func resolveRealLLMCacheDirectory() throws -> URL {
        #if DEBUG
        if let configured = ProcessInfo.processInfo.environment["HF_HOME"],
           !configured.isEmpty {
            let url = URL(fileURLWithPath: configured).standardizedFileURL
            try SecurityValidation.validateDirectory(
                url,
                requireCurrentOwner: true
            )
            return url
        }
        #endif
        let url = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cache/corelm/macos/model-assets", isDirectory: true)
            .standardizedFileURL
        try SecurityValidation.validateDirectory(
            url,
            requireCurrentOwner: true
        )
        return url
    }

    private func resolveRealLLMScript() throws -> URL {
        if let resources = Bundle.main.resourceURL {
            let bundled = resources.appendingPathComponent(
                "RealLLM/app_proof_runner.py"
            )
            if Bundle.main.bundleURL.pathExtension == "app" {
                try SecurityValidation.validateBundleSignature(
                    Bundle.main.bundleURL
                )
                return try SecurityValidation.validateRegularFileInside(
                    bundled,
                    root: resources
                )
            }
        }
        #if DEBUG
        let source = projectDirectory.appendingPathComponent(
            "RealLLM/app_proof_runner.py"
        )
        return try SecurityValidation.validateRegularFileInside(
            source,
            root: projectDirectory
        )
        #else
        throw SecurityValidationError.invalid(
            "The signed bundled compression runner is unavailable."
        )
        #endif
    }

    func realLLMModuleState() -> ModuleState {
        isRunning ? .running : (realLLMResult == nil ? .ready : .complete)
    }

    static func publicResultLabel(for url: URL) -> String? {
        guard url.isFileURL,
              url.lastPathComponent == "validation-064-071.json" else {
            return nil
        }
        let runIdentifier = url.deletingLastPathComponent().lastPathComponent
        guard let uuid = UUID(uuidString: runIdentifier),
              uuid.uuidString.lowercased() == runIdentifier else {
            return nil
        }
        return "\(runIdentifier)/\(url.lastPathComponent)"
    }

    static func sanitizedPublicMessage(_ message: String) -> String {
        var sanitized = message.replacingOccurrences(of: "\u{0}", with: "")
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        if !home.isEmpty {
            sanitized = sanitized.replacingOccurrences(
                of: home,
                with: "<home>"
            )
        }
        for pattern in [
            #"(?:/Users|/home)/[^/\s]+"#,
            #"[A-Za-z]:\\Users\\[^\\\s]+"#
        ] {
            sanitized = sanitized.replacingOccurrences(
                of: pattern,
                with: "<home>",
                options: .regularExpression
            )
        }
        for pattern in [
            #"gh[pousr]_[A-Za-z0-9_]{20,}"#,
            #"github_pat_[A-Za-z0-9_]{20,}"#,
            #"hf_[A-Za-z0-9]{20,}"#,
            #"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"#
        ] {
            sanitized = sanitized.replacingOccurrences(
                of: pattern,
                with: "[REDACTED_CREDENTIAL]",
                options: .regularExpression
            )
        }
        let hostname = ProcessInfo.processInfo.hostName
        if hostname.count >= 3 {
            sanitized = sanitized.replacingOccurrences(
                of: hostname,
                with: "<host>"
            )
        }
        return sanitized
    }

    private static func captureFailure(_ code: String)
        -> SecurityValidationError
    {
        .invalid(code)
    }

    private static func exactCaptureObject(
        _ value: Any?,
        keys: Set<String>,
        code: String
    ) throws -> [String: Any] {
        guard let object = value as? [String: Any],
              Set(object.keys) == keys else {
            throw captureFailure(code)
        }
        return object
    }

    private static func captureString(
        _ value: Any?,
        maximumUTF8Bytes: Int = 4_096
    ) -> String? {
        guard let value = value as? String,
              !value.isEmpty,
              value.utf8.count <= maximumUTF8Bytes,
              value.unicodeScalars.allSatisfy({
                  $0.value >= 0x20 && $0.value != 0x7f
              }) else {
            return nil
        }
        return value
    }

    private static func captureInteger(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID() else {
            return nil
        }
        let double = number.doubleValue
        guard double.isFinite,
              double.rounded(.towardZero) == double,
              double >= Double(Int.min),
              double <= Double(Int.max) else {
            return nil
        }
        return Int(double)
    }

    private static func captureNumber(_ value: Any?) -> Double? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(),
              number.doubleValue.isFinite else {
            return nil
        }
        return number.doubleValue
    }

    private static func captureNumbersEqual(
        _ value: Any?,
        _ expected: Double
    ) -> Bool {
        guard expected.isFinite,
              let observed = captureNumber(value) else {
            return false
        }
        return abs(observed - expected)
            <= max(1e-12, abs(expected) * 1e-12)
    }

    private static func isLowercaseGitObjectID(_ value: String) -> Bool {
        [40, 64].contains(value.utf8.count)
            && value.utf8.allSatisfy {
                (48...57).contains($0) || (97...102).contains($0)
            }
    }

    private static func isSafeCaptureTag(_ value: String) -> Bool {
        value.utf8.count <= 200
            && value.range(
                of: "^[A-Za-z0-9][A-Za-z0-9._/+@-]{0,199}$",
                options: .regularExpression
            ) != nil
    }

    private static func canonicalCaptureJSON(
        _ value: Any,
        prettyPrinted: Bool,
        trailingNewline: Bool
    ) throws -> Data {
        var options: JSONSerialization.WritingOptions = [
            .sortedKeys, .withoutEscapingSlashes
        ]
        if prettyPrinted {
            options.insert(.prettyPrinted)
        }
        var data = try JSONSerialization.data(
            withJSONObject: value,
            options: options
        )
        if trailingNewline {
            data.append(0x0a)
        }
        return data
    }

    static func validatedPortfolioReadyFileURL(
        path: String
    ) throws -> URL {
        let readyFile = URL(fileURLWithPath: path)
        guard path.hasPrefix("/"),
              path != "/",
              path.utf8.count <= 4_096,
              !path.utf8.contains(0),
              readyFile.standardizedFileURL.path == path else {
            throw captureFailure("CAPTURE_READY_PATH_INVALID")
        }
        let parent = readyFile.deletingLastPathComponent()
            .standardizedFileURL
        guard parent.path != "/",
              parent.resolvingSymlinksInPath().standardizedFileURL.path
                == parent.path else {
            throw captureFailure("CAPTURE_READY_PARENT_INVALID")
        }
        try SecurityValidation.validateDirectory(
            parent, requireCurrentOwner: true
        )
        var parentStatus = stat()
        guard parent.path.withCString({
            lstat($0, &parentStatus)
        }) == 0,
        (parentStatus.st_mode & S_IFMT) == S_IFDIR,
        parentStatus.st_uid == getuid(),
        (parentStatus.st_mode & mode_t(0o7777)) == mode_t(0o700)
        else {
            throw captureFailure("CAPTURE_READY_PARENT_PERMISSIONS_INVALID")
        }
        var targetStatus = stat()
        let targetResult = readyFile.path.withCString {
            lstat($0, &targetStatus)
        }
        let targetErrno = errno
        guard targetResult != 0, targetErrno == ENOENT else {
            throw captureFailure("CAPTURE_READY_TARGET_NOT_ABSENT")
        }
        return readyFile
    }

    static func portfolioMetricDecimal(_ value: Double) -> String {
        String(
            format: "%.6f",
            locale: Locale(identifier: "en_US_POSIX"),
            value
        )
    }

    static func writePortfolioCaptureReadiness(
        at readyFile: URL,
        runIdentifier: String,
        resultFileSHA256: String,
        receiptFileSHA256: String,
        applicationExecutableSHA256: String,
        metricVerdict: String,
        compressionRatioVsBF16: Double,
        deltaNLLNatPerToken: Double,
        top1Agreement: Double
    ) throws {
        guard let uuid = UUID(uuidString: runIdentifier),
              uuid.uuidString.lowercased() == runIdentifier,
              SecurityValidation.isLowercaseSHA256(resultFileSHA256),
              SecurityValidation.isLowercaseSHA256(receiptFileSHA256),
              SecurityValidation.isLowercaseSHA256(
                  applicationExecutableSHA256
              ),
              ["PASS", "FAIL"].contains(metricVerdict),
              compressionRatioVsBF16.isFinite,
              compressionRatioVsBF16 > 0,
              compressionRatioVsBF16 <= 64,
              deltaNLLNatPerToken.isFinite,
              (-1...1).contains(deltaNLLNatPerToken),
              top1Agreement.isFinite,
              (0...1).contains(top1Agreement) else {
            throw captureFailure("CAPTURE_READY_BINDING_INVALID")
        }
        let validatedTarget = try validatedPortfolioReadyFileURL(
            path: readyFile.path
        )
        guard validatedTarget.path == readyFile.path else {
            throw captureFailure("CAPTURE_READY_PATH_CHANGED")
        }
        let parent = validatedTarget.deletingLastPathComponent()
        let targetName = validatedTarget.lastPathComponent
        let parentDescriptor = parent.path.withCString {
            Darwin.open(
                $0,
                O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW
            )
        }
        guard parentDescriptor >= 0 else {
            throw captureFailure("CAPTURE_READY_PARENT_OPEN_FAILED")
        }
        defer {
            _ = Darwin.close(parentDescriptor)
        }
        var parentDescriptorStatus = stat()
        var parentPathStatus = stat()
        guard fstat(parentDescriptor, &parentDescriptorStatus) == 0,
              parent.path.withCString({
                  lstat($0, &parentPathStatus)
              }) == 0,
              (parentDescriptorStatus.st_mode & S_IFMT) == S_IFDIR,
              parentDescriptorStatus.st_uid == getuid(),
              (parentDescriptorStatus.st_mode & mode_t(0o7777))
                == mode_t(0o700),
              parentDescriptorStatus.st_dev == parentPathStatus.st_dev,
              parentDescriptorStatus.st_ino == parentPathStatus.st_ino,
              parent.resolvingSymlinksInPath().standardizedFileURL.path
                == parent.path else {
            throw captureFailure("CAPTURE_READY_PARENT_CHANGED")
        }
        var existingTargetStatus = stat()
        let existingTargetResult = targetName.withCString {
            fstatat(
                parentDescriptor,
                $0,
                &existingTargetStatus,
                AT_SYMLINK_NOFOLLOW
            )
        }
        let existingTargetErrno = errno
        guard existingTargetResult != 0,
              existingTargetErrno == ENOENT else {
            throw captureFailure("CAPTURE_READY_TARGET_NOT_ABSENT")
        }
        let payload: [String: Any] = [
            "application_executable_sha256":
                applicationExecutableSHA256,
            "compression_ratio_vs_bf16": portfolioMetricDecimal(
                compressionRatioVsBF16
            ),
            "delta_nll_nat_per_token": portfolioMetricDecimal(
                deltaNLLNatPerToken
            ),
            "metric_verdict": metricVerdict,
            "module_states": [
                "compression": "COMPLETE",
                "heavy_replay": "PASS",
                "kv_cache": "COMPLETE",
                "primary_evidence": "COMPLETE",
                "qwen_model": "COMPLETE"
            ],
            "receipt_sha256": receiptFileSHA256,
            "result_sha256": resultFileSHA256,
            "run_identifier": runIdentifier,
            "schema_version": 1,
            "status": "CAPTURE_RESULT_READY",
            "top1_agreement": portfolioMetricDecimal(top1Agreement),
            "verifier_state": "PASS"
        ]
        let data = try canonicalCaptureJSON(
            payload,
            prettyPrinted: false,
            trailingNewline: true
        )
        let temporaryName =
            ".corelm-ready-\(UUID().uuidString.lowercased()).tmp"
        guard temporaryName != targetName else {
            throw captureFailure("CAPTURE_READY_TEMP_NAME_INVALID")
        }
        var descriptor = temporaryName.withCString {
            Darwin.openat(
                parentDescriptor,
                $0,
                O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                mode_t(0o600)
            )
        }
        guard descriptor >= 0 else {
            throw captureFailure("CAPTURE_READY_TEMP_CREATE_FAILED")
        }
        var temporaryExists = true
        defer {
            if descriptor >= 0 {
                _ = Darwin.close(descriptor)
            }
            if temporaryExists {
                _ = temporaryName.withCString {
                    Darwin.unlinkat(parentDescriptor, $0, 0)
                }
            }
        }
        try data.withUnsafeBytes { rawBuffer in
            guard let baseAddress = rawBuffer.baseAddress else {
                throw captureFailure("CAPTURE_READY_PAYLOAD_INVALID")
            }
            var offset = 0
            while offset < data.count {
                let written = Darwin.write(
                    descriptor,
                    baseAddress.advanced(by: offset),
                    data.count - offset
                )
                if written < 0, errno == EINTR {
                    continue
                }
                guard written > 0 else {
                    throw captureFailure("CAPTURE_READY_WRITE_FAILED")
                }
                offset += written
            }
        }
        guard fchmod(descriptor, mode_t(0o600)) == 0,
              fsync(descriptor) == 0 else {
            throw captureFailure("CAPTURE_READY_SYNC_FAILED")
        }
        var fileStatus = stat()
        guard fstat(descriptor, &fileStatus) == 0,
              (fileStatus.st_mode & S_IFMT) == S_IFREG,
              (fileStatus.st_mode & mode_t(0o7777)) == mode_t(0o600),
              fileStatus.st_uid == getuid(),
              fileStatus.st_nlink == 1,
              fileStatus.st_size == off_t(data.count) else {
            throw captureFailure("CAPTURE_READY_TEMP_INVALID")
        }
        guard Darwin.close(descriptor) == 0 else {
            descriptor = -1
            throw captureFailure("CAPTURE_READY_CLOSE_FAILED")
        }
        descriptor = -1

        var publishTargetStatus = stat()
        let publishTargetResult = targetName.withCString {
            fstatat(
                parentDescriptor,
                $0,
                &publishTargetStatus,
                AT_SYMLINK_NOFOLLOW
            )
        }
        let publishTargetErrno = errno
        guard publishTargetResult != 0,
              publishTargetErrno == ENOENT else {
            throw captureFailure("CAPTURE_READY_TARGET_NOT_ABSENT")
        }
        let renameFlags = UInt32(RENAME_EXCL | RENAME_NOFOLLOW_ANY)
        let renameResult = temporaryName.withCString { source in
            targetName.withCString { target in
                renameatx_np(
                    parentDescriptor,
                    source,
                    parentDescriptor,
                    target,
                    renameFlags
                )
            }
        }
        guard renameResult == 0 else {
            throw captureFailure("CAPTURE_READY_PUBLISH_FAILED")
        }
        temporaryExists = false
    }

    private static func canonicalCaptureObject(
        from data: Data,
        prettyPrinted: Bool,
        trailingNewline: Bool,
        maximumBytes: Int,
        code: String,
        requireCanonicalBytes: Bool = true
    ) throws -> [String: Any] {
        guard !data.isEmpty, data.count <= maximumBytes,
              String(data: data, encoding: .utf8) != nil,
              let object = try JSONSerialization.jsonObject(
                  with: data,
                  options: [.fragmentsAllowed]
              ) as? [String: Any] else {
            throw captureFailure(code)
        }
        if requireCanonicalBytes,
           try canonicalCaptureJSON(
               object,
               prettyPrinted: prettyPrinted,
               trailingNewline: trailingNewline
           ) != data {
            throw captureFailure(code)
        }
        return object
    }

    private static func captureTimestamp(_ value: Any?) -> Date? {
        guard let text = captureString(value, maximumUTF8Bytes: 64) else {
            return nil
        }
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: text) {
            return date
        }
        formatter.formatOptions = [
            .withInternetDateTime, .withFractionalSeconds
        ]
        return formatter.date(from: text)
    }

    private static func validateCapturePrimaryEvidence(
        _ value: Any?,
        expected: RealLLMPrimaryEvidenceReference
    ) throws {
        let primary = try exactCaptureObject(
            value,
            keys: [
                "schemaVersion", "path", "manifestSHA256",
                "manifestBytes", "containerCount", "containerBytes",
                "blocks", "predictionTokens"
            ],
            code: "CAPTURE_RECEIPT_PRIMARY_INVALID"
        )
        guard primary["schemaVersion"] as? String
                == expected.schemaVersion,
              primary["path"] as? String == expected.path,
              primary["manifestSHA256"] as? String
                == expected.manifestSHA256,
              captureInteger(primary["manifestBytes"])
                == expected.manifestBytes,
              captureInteger(primary["containerCount"])
                == expected.containerCount,
              captureInteger(primary["containerBytes"])
                == expected.containerBytes,
              captureInteger(primary["blocks"]) == expected.blocks,
              captureInteger(primary["predictionTokens"])
                == expected.predictionTokens else {
            throw captureFailure("CAPTURE_RECEIPT_PRIMARY_MISMATCH")
        }
    }

    private static func validateCaptureReports(
        _ reports: PortfolioCaptureReportBytes,
        sourceCommit: String,
        sourceTree: String,
        metricVerdict: String,
        receiptFileSHA256: String,
        resultFileSHA256: String
    ) throws -> (
        structural: String,
        replay: String,
        terminal: String
    ) {
        let retainedCount = [
            reports.structural, reports.replay, reports.terminal
        ].compactMap { $0 }.count
        if retainedCount == 0 {
            return (
                structural: "NOT RETAINED",
                replay: "NOT RETAINED",
                terminal: "NOT RETAINED"
            )
        }
        guard retainedCount == 3,
              let structuralData = reports.structural,
              let replayData = reports.replay,
              let terminalData = reports.terminal else {
            throw captureFailure("CAPTURE_REPORT_SET_INCOMPLETE")
        }

        let structural = try canonicalCaptureObject(
            from: structuralData,
            prettyPrinted: false,
            trailingNewline: true,
            maximumBytes: 64 * 1_024,
            code: "CAPTURE_STRUCTURAL_REPORT_INVALID"
        )
        let structuralSource = try exactCaptureObject(
            structural["source"],
            keys: ["commit", "tree"],
            code: "CAPTURE_STRUCTURAL_SOURCE_INVALID"
        )
        guard Set(structural.keys) == [
            "metric_verdict", "receipt_sha256", "report_kind",
            "result_sha256", "schema_version", "source",
            "synthetic_data", "verdict", "workload_classification"
        ],
              captureInteger(structural["schema_version"]) == 1,
              structural["report_kind"] as? String == "structural_verifier",
              structural["verdict"] as? String == "PASS",
              structural["metric_verdict"] as? String == metricVerdict,
              structural["receipt_sha256"] as? String
                == receiptFileSHA256,
              structural["result_sha256"] as? String
                == resultFileSHA256,
              structural["workload_classification"] as? String
                == "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION",
              structural["synthetic_data"] as? Bool == false,
              structuralSource["commit"] as? String == sourceCommit,
              structuralSource["tree"] as? String == sourceTree else {
            throw captureFailure("CAPTURE_STRUCTURAL_REPORT_MISMATCH")
        }

        let replay = try canonicalCaptureObject(
            from: replayData,
            prettyPrinted: false,
            trailingNewline: true,
            maximumBytes: 64 * 1_024,
            code: "CAPTURE_REPLAY_REPORT_INVALID",
            requireCanonicalBytes: false
        )
        let replaySource = try exactCaptureObject(
            replay["source"],
            keys: ["commit", "tree"],
            code: "CAPTURE_REPLAY_SOURCE_INVALID"
        )
        let model = try exactCaptureObject(
            replay["model"],
            keys: ["repository", "revision"],
            code: "CAPTURE_REPLAY_MODEL_INVALID"
        )
        let replayEvidence = try exactCaptureObject(
            replay["replay"],
            keys: [
                "decisions", "lossAbsoluteTolerance",
                "lossRelativeTolerance",
                "maximumAllowedBaselineDifference",
                "maximumAllowedCandidateDifference",
                "maximumBaselineLossDifference",
                "maximumCandidateLossDifference",
                "perDecisionEvidenceSHA256",
                "primaryManifestSHA256", "tokenMetricsSHA256"
            ],
            code: "CAPTURE_REPLAY_EVIDENCE_INVALID"
        )
        let maximumAllowedBaseline = captureNumber(
            replayEvidence["maximumAllowedBaselineDifference"]
        )
        let maximumAllowedCandidate = captureNumber(
            replayEvidence["maximumAllowedCandidateDifference"]
        )
        let maximumBaseline = captureNumber(
            replayEvidence["maximumBaselineLossDifference"]
        )
        let maximumCandidate = captureNumber(
            replayEvidence["maximumCandidateLossDifference"]
        )
        let replayVerdict =
            "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS"
        let replayDigestsValid = [
            "perDecisionEvidenceSHA256",
            "primaryManifestSHA256", "tokenMetricsSHA256"
        ].allSatisfy { key in
            guard let digest = replayEvidence[key] as? String else {
                return false
            }
            return SecurityValidation.isLowercaseSHA256(digest)
        }
        guard Set(replay.keys) == [
            "execution_scope", "metric_verdict", "model",
            "receipt_sha256", "replay", "report_kind",
            "result_sha256", "schema_version", "source",
            "synthetic_data", "verdict", "workload_classification"
        ],
              captureInteger(replay["schema_version"]) == 1,
              replay["report_kind"] as? String == "fresh_model_replay",
              replay["verdict"] as? String == replayVerdict,
              replay["metric_verdict"] as? String == metricVerdict,
              replay["receipt_sha256"] as? String
                == receiptFileSHA256,
              replay["result_sha256"] as? String == resultFileSHA256,
              replay["workload_classification"] as? String
                == "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION",
              replay["synthetic_data"] as? Bool == false,
              replay["execution_scope"] as? String
                == "AUTHOR_RECORDED_NOT_INDEPENDENTLY_REEXECUTED_BY_RELEASE_VERIFIER",
              replaySource["commit"] as? String == sourceCommit,
              replaySource["tree"] as? String == sourceTree,
              model["repository"] as? String == "Qwen/Qwen2.5-0.5B",
              model["revision"] as? String
                == "060db6499f32faf8b98477b0a26969ef7d8b9987",
              captureInteger(replayEvidence["decisions"]) == 1_024,
              captureNumbersEqual(
                  replayEvidence["lossAbsoluteTolerance"], 2e-5
              ),
              captureNumbersEqual(
                  replayEvidence["lossRelativeTolerance"], 2e-6
              ),
              let maximumAllowedBaseline,
              let maximumAllowedCandidate,
              let maximumBaseline,
              let maximumCandidate,
              maximumAllowedBaseline >= 0,
              maximumAllowedCandidate >= 0,
              maximumBaseline >= 0,
              maximumCandidate >= 0,
              maximumBaseline <= maximumAllowedBaseline,
              maximumCandidate <= maximumAllowedCandidate,
              replayDigestsValid else {
            throw captureFailure("CAPTURE_REPLAY_REPORT_MISMATCH")
        }

        let passTerminal = "END-TO-END PROOF PASS\n"
        let failTerminal =
            "END-TO-END PROOF VERIFIED — METRIC FAIL\n"
        let expectedTerminal = metricVerdict == "PASS"
            ? passTerminal : failTerminal
        guard terminalData == Data(expectedTerminal.utf8) else {
            throw captureFailure("CAPTURE_TERMINAL_REPORT_MISMATCH")
        }
        return (
            structural: "PASS",
            replay: replayVerdict,
            terminal: String(expectedTerminal.dropLast())
        )
    }

    static func validatedPortfolioCaptureSnapshot(
        result: RealLLMResult,
        resultFileSHA256: String,
        receiptData: Data,
        receiptFileSHA256: String,
        runIdentifier: String,
        structuralReportData: Data? = nil,
        replayReportData: Data? = nil,
        terminalReportData: Data? = nil
    ) throws -> PortfolioCaptureSnapshot {
        guard let uuid = UUID(uuidString: runIdentifier),
              uuid.uuidString.lowercased() == runIdentifier,
              SecurityValidation.isLowercaseSHA256(resultFileSHA256),
              SecurityValidation.isLowercaseSHA256(receiptFileSHA256),
              SecurityValidation.isLowercaseSHA256(result.resultSHA256),
              let aggregate = result.aggregate else {
            throw captureFailure("CAPTURE_RESULT_IDENTITY_INVALID")
        }
        let receipt = try canonicalCaptureObject(
            from: receiptData,
            prettyPrinted: true,
            trailingNewline: false,
            maximumBytes: 64 * 1_024,
            code: "CAPTURE_RECEIPT_INVALID"
        )
        guard Set(receipt.keys) == [
            "application", "buildProvenance", "challengeNonce",
            "createdAt", "error", "primaryEvidence", "protocol",
            "result", "schemaVersion", "startedAt", "worker"
        ],
              receipt["schemaVersion"] as? String
                == "corelm-macos-app-real-llm-run-v5",
              receipt["error"] is NSNull,
              let startedAt = captureTimestamp(receipt["startedAt"]),
              let resultCreatedAt = captureTimestamp(result.createdAt),
              let receiptCreatedAt = captureTimestamp(receipt["createdAt"]),
              startedAt <= resultCreatedAt,
              resultCreatedAt <= receiptCreatedAt else {
            throw captureFailure("CAPTURE_RECEIPT_CONTRACT_INVALID")
        }

        let challenge = receipt["challengeNonce"] as? String ?? ""
        guard SecurityValidation.isLowercaseSHA256(challenge) else {
            throw captureFailure("CAPTURE_CHALLENGE_INVALID")
        }
        let resultReceipt = try exactCaptureObject(
            receipt["result"],
            keys: [
                "compressionRatioVsBF16", "deltaNLLNatPerToken",
                "metricVerdict", "path", "resultFileSHA256",
                "resultRole", "resultSHA256",
                "swiftStructuralVerification", "top1Agreement"
            ],
            code: "CAPTURE_RESULT_RECEIPT_INVALID"
        )
        let metricVerdict = aggregate.pass ? "PASS" : "FAIL"
        guard aggregate.compressionRatioVsBF16.isFinite,
              aggregate.compressionRatioVsBF16 > 0,
              aggregate.compressionRatioVsBF16 <= 64,
              aggregate.deltaNLLNatPerToken.isFinite,
              (-1...1).contains(aggregate.deltaNLLNatPerToken),
              aggregate.top1Agreement.isFinite,
              (0...1).contains(aggregate.top1Agreement),
              resultReceipt["path"] as? String
                == "validation-064-071.json",
              resultReceipt["resultFileSHA256"] as? String
                == resultFileSHA256,
              resultReceipt["resultSHA256"] as? String
                == result.resultSHA256,
              resultReceipt["resultRole"] as? String
                == "PUBLIC_VALIDATION_REGRESSION",
              resultReceipt["metricVerdict"] as? String
                == metricVerdict,
              resultReceipt["swiftStructuralVerification"] as? String
                == "PASS",
              captureNumbersEqual(
                  resultReceipt["compressionRatioVsBF16"],
                  aggregate.compressionRatioVsBF16
              ),
              captureNumbersEqual(
                  resultReceipt["deltaNLLNatPerToken"],
                  aggregate.deltaNLLNatPerToken
              ),
              captureNumbersEqual(
                  resultReceipt["top1Agreement"], aggregate.top1Agreement
              ) else {
            throw captureFailure("CAPTURE_RESULT_RECEIPT_MISMATCH")
        }

        guard let primary = result.primaryEvidence else {
            throw captureFailure("CAPTURE_PRIMARY_EVIDENCE_MISSING")
        }
        try validateCapturePrimaryEvidence(
            receipt["primaryEvidence"], expected: primary
        )

        let application = try exactCaptureObject(
            receipt["application"],
            keys: [
                "bundleIdentifier", "bundleName", "executableSHA256",
                "processIdentifier", "version"
            ],
            code: "CAPTURE_APPLICATION_RECEIPT_INVALID"
        )
        guard application["bundleIdentifier"] as? String
                == "com.corelm.benchmark",
              application["bundleName"] as? String
                == "CoreLMBenchmark.app",
              let appDigest = application["executableSHA256"] as? String,
              SecurityValidation.isLowercaseSHA256(appDigest),
              let appPID = captureInteger(
                  application["processIdentifier"]
              ), appPID > 0,
              captureString(
                  application["version"], maximumUTF8Bytes: 64
              ) != nil else {
            throw captureFailure("CAPTURE_APPLICATION_RECEIPT_MISMATCH")
        }

        let worker = try exactCaptureObject(
            receipt["worker"],
            keys: [
                "processIdentifier", "python",
                "pythonExecutableSHA256", "runtimeManifestSHA256",
                "script", "scriptSHA256", "terminationStatus"
            ],
            code: "CAPTURE_WORKER_RECEIPT_INVALID"
        )
        let workerDigestsValid = [
            "pythonExecutableSHA256", "runtimeManifestSHA256",
            "scriptSHA256"
        ].allSatisfy { key in
            guard let digest = worker[key] as? String else {
                return false
            }
            return SecurityValidation.isLowercaseSHA256(digest)
        }
        guard let workerPID = captureInteger(worker["processIdentifier"]),
              workerPID > 0,
              worker["python"] as? String == "signed-runtime-manifest",
              worker["script"] as? String
                == "Resources/RealLLM/app_proof_runner.py",
              captureInteger(worker["terminationStatus"]) == 0,
              workerDigestsValid else {
            throw captureFailure("CAPTURE_WORKER_RECEIPT_MISMATCH")
        }

        let protocolReceipt = try exactCaptureObject(
            receipt["protocol"],
            keys: [
                "candidateIndex", "device", "hfHome", "offlineRequested",
                "sanitizedChildEnvironment", "validationBlocks",
                "validationStartBlock"
            ],
            code: "CAPTURE_PROTOCOL_RECEIPT_INVALID"
        )
        guard captureInteger(protocolReceipt["candidateIndex"]) == 32,
              protocolReceipt["device"] as? String == "mps",
              protocolReceipt["hfHome"] as? String == "configured",
              protocolReceipt["offlineRequested"] as? Bool == true,
              protocolReceipt["sanitizedChildEnvironment"] as? Bool
                == true,
              captureInteger(protocolReceipt["validationStartBlock"])
                == CompressionProofRunPolicy.registeredStartBlock,
              captureInteger(protocolReceipt["validationBlocks"])
                == CompressionProofRunPolicy.registeredBlockCount else {
            throw captureFailure("CAPTURE_PROTOCOL_RECEIPT_MISMATCH")
        }

        let build = try exactCaptureObject(
            receipt["buildProvenance"],
            keys: ["document", "path", "sha256"],
            code: "CAPTURE_BUILD_RECEIPT_INVALID"
        )
        let document = try exactCaptureObject(
            build["document"],
            keys: ["schemaVersion", "source", "toolchain"],
            code: "CAPTURE_BUILD_DOCUMENT_INVALID"
        )
        let source = try exactCaptureObject(
            document["source"],
            keys: [
                "archiveManifestSHA256", "commit", "dirty", "exactTag",
                "mode", "remote", "tree"
            ],
            code: "CAPTURE_SOURCE_IDENTITY_INVALID"
        )
        let buildDigest = build["sha256"] as? String ?? ""
        let buildCanonical = try canonicalCaptureJSON(
            document,
            prettyPrinted: false,
            trailingNewline: true
        )
        let sourceTag = source["exactTag"] as? String ?? ""
        let sourceCommit = source["commit"] as? String ?? ""
        let sourceTree = source["tree"] as? String ?? ""
        guard build["path"] as? String
                == "Resources/build-provenance.json",
              SecurityValidation.isLowercaseSHA256(buildDigest),
              SecurityValidation.sha256Hex(buildCanonical) == buildDigest,
              document["schemaVersion"] as? String
                == "corelm-build-provenance-v1",
              document["toolchain"] is [String: Any],
              source["archiveManifestSHA256"] is NSNull,
              source["mode"] as? String == "git",
              source["dirty"] as? Bool == false,
              isSafeCaptureTag(sourceTag),
              isLowercaseGitObjectID(sourceCommit),
              isLowercaseGitObjectID(sourceTree),
              captureString(source["remote"], maximumUTF8Bytes: 2_048)
                != nil else {
            throw captureFailure("CAPTURE_SOURCE_IDENTITY_MISMATCH")
        }

        let reportVerdicts = try validateCaptureReports(
            PortfolioCaptureReportBytes(
                structural: structuralReportData,
                replay: replayReportData,
                terminal: terminalReportData
            ),
            sourceCommit: sourceCommit,
            sourceTree: sourceTree,
            metricVerdict: metricVerdict,
            receiptFileSHA256: receiptFileSHA256,
            resultFileSHA256: resultFileSHA256
        )
        guard reportVerdicts.structural == "PASS",
              reportVerdicts.replay
                == "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS",
              reportVerdicts.terminal != "NOT RETAINED" else {
            throw captureFailure("CAPTURE_PROOF_REPORTS_REQUIRED")
        }
        return PortfolioCaptureSnapshot(
            sourceTag: sourceTag,
            sourceCommit: sourceCommit,
            sourceTree: sourceTree,
            challengeSHA256: SecurityValidation.sha256Hex(
                Data(challenge.utf8)
            ),
            runIdentifier: runIdentifier,
            resultSHA256: result.resultSHA256,
            metricVerdict: metricVerdict,
            compressionRatioVsBF16: aggregate.compressionRatioVsBF16,
            deltaNLLNatPerToken: aggregate.deltaNLLNatPerToken,
            top1Agreement: aggregate.top1Agreement,
            moduleState: "COMPLETE",
            heavyReplayState: "PASS",
            verifierState: "PASS",
            structuralVerdict: reportVerdicts.structural,
            replayVerdict: reportVerdicts.replay,
            terminalVerdict: reportVerdicts.terminal,
            resultFileSHA256: resultFileSHA256,
            receiptFileSHA256: receiptFileSHA256,
            buildProvenanceSHA256: buildDigest,
            applicationExecutableSHA256: appDigest
        )
    }

    func runRealLLM() {
        guard !isRunning else { return }
        guard !proofChallengeRequested || proofChallengeNonce != nil else {
            errorMessage = "The external proof challenge is malformed."
            return
        }
        let requested = CompressionProofRunPolicy.effectiveSettings(
            requested: realLLMSettings
        )
        realLLMSettings = requested
        guard (64...512).contains(requested.validationStartBlock) else {
            errorMessage = "Compression proof runs must start at validation block 64 or later."
            return
        }
        guard (1...32).contains(requested.validationBlocks) else {
            errorMessage = "Compression proof block count must be between 1 and 32."
            return
        }
        let finalBlock: Int
        let python: URL
        let pythonSHA256: String
        let script: URL
        let cache: URL
        let runDirectory = realLLMResultsDirectory.appendingPathComponent(
            UUID().uuidString.lowercased(), isDirectory: true
        )
        let pythonCacheDirectory: URL
        beginRealLLMPowerActivity()
        do {
            let endExclusive = try SecurityValidation.checkedAdd(
                requested.validationStartBlock,
                requested.validationBlocks
            )
            finalBlock = try SecurityValidation.checkedAdd(endExclusive, -1)
            let runtime = try resolveRealLLMPythonExecutable()
            python = runtime.executableURL
            pythonSHA256 = runtime.sha256
            script = try resolveRealLLMScript()
            cache = try resolveRealLLMCacheDirectory()
            try preparePrivateResultsDirectory(realLLMResultsDirectory)
            try SecurityValidation.ensurePrivateDirectory(runDirectory)
            pythonCacheDirectory = runDirectory.appendingPathComponent(
                "python-cache", isDirectory: true
            )
            try SecurityValidation.ensurePrivateDirectory(
                pythonCacheDirectory
            )
        } catch {
            endRealLLMPowerActivity()
            setError(error.localizedDescription)
            return
        }
        let outputURL = runDirectory.appendingPathComponent(
            String(
                format: "validation-%03d-%03d.json",
                requested.validationStartBlock,
                finalBlock
            )
        )
        do {
            try SecurityValidation.requirePathAbsentInValidatedDirectory(
                outputURL
            )
        } catch {
            endRealLLMPowerActivity()
            setError(error.localizedDescription)
            return
        }

        isRunning = true
        progress = 0.02
        errorMessage = nil
        realLLMResult = nil
        realLLMVerified = false
        realLLMVerificationMessage = "Loading pinned model and dataset…"
        realLLMResultURL = outputURL
        realLLMStartedAt = Date()
        lastRealLLMWorkerPID = nil
        activeRealLLMPythonSHA256 = pythonSHA256
        activeRealLLMScriptURL = script
        forcedRealLLMFailure = nil
        appendLog(
            "Launching Qwen2.5-0.5B on MPS: validation blocks "
                + "\(requested.validationStartBlock)–\(finalBlock)."
        )

        let task = Process()
        process = task
        task.qualityOfService = .utility
        task.executableURL = python
        task.currentDirectoryURL = script
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        task.arguments = [
            "-I", "-B", "-u", "-X",
            "pycache_prefix=\(pythonCacheDirectory.path)",
            script.path,
            "--output", outputURL.path,
            "--device", "mps",
            "--validation-start-block",
            "\(requested.validationStartBlock)",
            "--validation-blocks", "\(requested.validationBlocks)",
            "--candidate-index", "\(requested.candidateIndex)",
            "--primary-evidence-directory",
            runDirectory.appendingPathComponent(
                "primary-evidence", isDirectory: true
            ).path,
            "--local-files-only"
        ]

        task.environment = Self.realLLMWorkerEnvironment(
            cache: cache,
            supervisionFile: runDirectory.appendingPathComponent(
                ".worker-process-group"
            )
        )

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        task.standardOutput = stdoutPipe
        task.standardError = stderrPipe
        let stderrBuffer = BoundedOutputBuffer()
        let stdoutHandle = stdoutPipe.fileHandleForReading
        let stderrHandle = stderrPipe.fileHandleForReading

        stdoutHandle.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else {
                handle.readabilityHandler = nil
                return
            }
            guard let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in
                self?.consumeRealLLMOutput(
                    text, totalBlocks: requested.validationBlocks
                )
            }
        }
        stderrHandle.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else {
                handle.readabilityHandler = nil
                return
            }
            stderrBuffer.append(data)
            guard let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in
                let lines = text
                    .replacingOccurrences(of: "\r", with: "\n")
                    .split(separator: "\n")
                    .map(String.init)
                for line in lines where !line.contains("Loading weights:") {
                    self?.appendLog(line)
                }
            }
        }

        task.terminationHandler = { [weak self] completed in
            stdoutHandle.readabilityHandler = nil
            stderrHandle.readabilityHandler = nil
            stderrBuffer.append(stderrHandle.readDataToEndOfFile())
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.finishRealLLMRun(
                    task: completed,
                    outputURL: outputURL,
                    settings: requested,
                    workerErrorDetail: stderrBuffer.text(fallback: "")
                )
            }
        }

        do {
            try task.run()
            do {
                try confirmWorkerProcessGroup(for: task)
            } catch {
                task.terminationHandler = nil
                stdoutHandle.readabilityHandler = nil
                stderrHandle.readabilityHandler = nil
                if task.isRunning {
                    _ = kill(task.processIdentifier, SIGKILL)
                    task.waitUntilExit()
                }
                throw error
            }
            startRealLLMSafetyWatchdog(for: task)
            lastRealLLMWorkerPID = task.processIdentifier
            progress = 0.08
            appendLog(
                "App spawned compression worker PID \(task.processIdentifier)."
            )
        } catch {
            stdoutHandle.readabilityHandler = nil
            stderrHandle.readabilityHandler = nil
            endRealLLMPowerActivity()
            isRunning = false
            process = nil
            activeProcessGroupID = nil
            stopRealLLMSafetyWatchdog()
            setError(error.localizedDescription)
            realLLMVerificationMessage = "Launch failed"
            writeRealLLMReceipt(
                outputURL: outputURL,
                settings: requested,
                terminationStatus: nil,
                error: error.localizedDescription
            )
        }
    }

    private func consumeRealLLMOutput(_ text: String, totalBlocks: Int) {
        let lines = text
            .replacingOccurrences(of: "\r", with: "\n")
            .split(separator: "\n")
            .map(String.init)
        for line in lines {
            if line.hasPrefix("validation block ") {
                let fields = line.split(separator: " ")
                if fields.count >= 3 {
                    let progressParts = fields[2].split(separator: "/")
                    if progressParts.count == 2,
                       let completed = Double(progressParts[0]),
                       let total = Double(progressParts[1]),
                       total > 0 {
                        progress = min(0.92, 0.10 + 0.80 * completed / total)
                    }
                }
                appendLog(line)
            } else if line.contains("complete")
                        || line.hasPrefix("Result SHA-256:")
                        || line.hasPrefix("- schedule=") {
                appendLog(line)
            }
        }
        if totalBlocks > 0 && progress < 0.10 {
            progress = 0.10
        }
    }

    private func finishRealLLMRun(
        task: Process,
        outputURL: URL,
        settings: RealLLMRunSettings,
        workerErrorDetail: String
    ) {
        guard process === task else { return }
        stopRealLLMSafetyWatchdog()
        defer { endRealLLMPowerActivity() }
        isRunning = false
        process = nil
        activeProcessGroupID = nil
        guard task.terminationStatus == 0 else {
            progress = 0
            let message = forcedRealLLMFailure
                ?? Self.workerFailureMessage(
                    status: task.terminationStatus,
                    detail: workerErrorDetail
                )
            forcedRealLLMFailure = nil
            setError(message)
            realLLMVerificationMessage = "Execution failed"
            appendLog(message)
            writeRealLLMReceipt(
                outputURL: outputURL,
                settings: settings,
                terminationStatus: task.terminationStatus,
                error: message
            )
            return
        }
        forcedRealLLMFailure = nil

        do {
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600],
                ofItemAtPath: outputURL.path
            )
            let data = try SecurityValidation.readRegularFile(
                at: outputURL,
                maximumBytes: SecurityValidation.maximumRealLLMResultBytes
            )
            let canonicalDigest =
                try SecurityValidation.verifiedCanonicalResultDigest(
                    from: data
                )
            let decoded = try JSONDecoder().decode(
                RealLLMResult.self,
                from: data
            )
            guard decoded.resultSHA256 == canonicalDigest else {
                throw SecurityValidationError.invalid(
                    "Decoded result digest differs from canonical verification."
                )
            }
            try verifyRealLLMResult(decoded, expected: settings)
            try verifyPrimaryEvidence(decoded, outputURL: outputURL)
            realLLMResult = decoded
            realLLMVerified = true
            realLLMVerificationMessage = "Swift structural verification PASS"
            progress = 1
            if let aggregate = decoded.aggregate {
                appendLog(
                    String(
                        format: "Compression proof %@ — %.3f×, ΔNLL %+.6f, top-1 %.4f.",
                        aggregate.pass ? "PASS" : "FAIL",
                        aggregate.compressionRatioVsBF16,
                        aggregate.deltaNLLNatPerToken,
                        aggregate.top1Agreement
                    )
                )
            }
            writeRealLLMReceipt(
                outputURL: outputURL,
                settings: settings,
                terminationStatus: task.terminationStatus,
                error: nil
            )
        } catch {
            progress = 0
            realLLMVerified = false
            realLLMVerificationMessage = "Verification failed"
            setError(error.localizedDescription)
            appendLog(
                "Compression verification failed: \(error.localizedDescription)"
            )
            writeRealLLMReceipt(
                outputURL: outputURL,
                settings: settings,
                terminationStatus: task.terminationStatus,
                error: error.localizedDescription
            )
        }
    }

    static func workerFailureMessage(status: Int32, detail: String) -> String {
        let lastLine = detail
            .replacingOccurrences(of: "\r", with: "\n")
            .split(separator: "\n")
            .map(String.init)
            .last(where: { !$0.contains("Loading weights:") })
        guard let lastLine, !lastLine.isEmpty else {
            return "Compression worker exited with status \(status)."
        }
        let redacted = lastLine.replacingOccurrences(
            of: FileManager.default.homeDirectoryForCurrentUser.path,
            with: "<home>"
        )
        let bounded = String(
            redacted.prefix(SecurityValidation.maximumLogEntryCharacters / 2)
        )
        return "Compression worker exited with status \(status): \(bounded)"
    }

    func verifyRealLLMResult(
        _ result: RealLLMResult,
        expected: RealLLMRunSettings
    ) throws {
        func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
            if !condition() {
                throw NSError(
                    domain: "CoreLMBenchmark.RealLLMVerification",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: message]
                )
            }
        }
        func close(_ left: Double, _ right: Double) -> Bool {
            left.isFinite
                && right.isFinite
                && abs(left - right)
                    <= max(1e-12, 1e-12 * max(abs(left), abs(right)))
        }
        func cacheClose(_ left: Double, _ right: Double) -> Bool {
            left.isFinite
                && right.isFinite
                && abs(left - right)
                    <= max(1e-7, 1e-10 * max(abs(left), abs(right)))
        }
        func lessThanOrClose(_ left: Double, _ right: Double) -> Bool {
            left.isFinite
                && right.isFinite
                && left <= right
                    + max(1e-12, 1e-12 * max(abs(left), abs(right)))
        }
        func finiteSum(
            _ values: [Double],
            label: String
        ) throws -> Double {
            var total = 0.0
            for value in values {
                try require(
                    value.isFinite && abs(value) <= 1e18,
                    "\(label) contains an invalid value."
                )
                total += value
                try require(total.isFinite, "\(label) overflowed.")
            }
            return total
        }
        func checkedIntegerSum(
            _ values: [Int]
        ) throws -> Int {
            var total = 0
            for value in values {
                total = try SecurityValidation.checkedAdd(total, value)
            }
            return total
        }
        func canonicalJSON<T: Encodable>(_ value: T) throws -> Data {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            return try encoder.encode(value)
        }
        func zlibCompressBound(_ sourceBytes: Int) throws -> Int {
            try require(sourceBytes >= 0, "A zlib source size is negative.")
            var bound = sourceBytes
            bound = try SecurityValidation.checkedAdd(
                bound,
                sourceBytes >> 12
            )
            bound = try SecurityValidation.checkedAdd(
                bound,
                sourceBytes >> 14
            )
            bound = try SecurityValidation.checkedAdd(
                bound,
                sourceBytes >> 25
            )
            return try SecurityValidation.checkedAdd(bound, 13)
        }

        try require(
            (64...512).contains(expected.validationStartBlock)
                && (1...32).contains(expected.validationBlocks),
            "Saved validation range is outside the app limits."
        )
        let endExclusive = try SecurityValidation.checkedAdd(
            expected.validationStartBlock,
            expected.validationBlocks
        )
        try require(
            [
                "corelm-voidtoken-v5-validation-development-v2",
                "corelm-voidtoken-v5-validation-development-v3"
            ].contains(result.schemaVersion),
            "Unexpected proof result schema."
        )
        try require(
            result.status == "validation-only-development",
            "Unexpected proof result status."
        )
        try require(!result.testDataOpened, "The exploratory app run opened test data.")
        try require(
            result.protocolInfo.modelRepository == "Qwen/Qwen2.5-0.5B",
            "Unexpected model repository."
        )
        try require(
            result.protocolInfo.modelRevision
                == "060db6499f32faf8b98477b0a26969ef7d8b9987",
            "Unexpected model revision."
        )
        try require(
            result.protocolInfo.modelWeightsSHA256
                == "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
            "Unexpected model weights digest."
        )
        try require(
            result.protocolInfo.datasetRepository == "Salesforce/wikitext"
                && result.protocolInfo.datasetRevision
                    == "b08601e04326c79dfdd32d625aee71d232d685c3",
            "Unexpected dataset identity."
        )
        try require(
            result.protocolInfo.split == "validation",
            "Unexpected dataset split."
        )
        try require(
            result.protocolInfo.validationStartBlock
                == expected.validationStartBlock
                && result.protocolInfo.validationBlocks
                    == expected.validationBlocks,
            "The recorded validation range differs from the app request."
        )
        try require(
            result.protocolInfo.evaluatedCandidateIndices
                == [expected.candidateIndex],
            "The app result does not use the frozen compression profile."
        )
        try require(
            result.environment.device == "mps"
                && result.environment.machine == "arm64",
            "The run did not report Apple MPS on arm64."
        )
        let pythonVersion = result.environment.python.split(
            separator: ".", omittingEmptySubsequences: false
        )
        try require(
            pythonVersion.count == 3
                && pythonVersion[0] == "3"
                && pythonVersion[1] == "12"
                && !pythonVersion[2].isEmpty
                && pythonVersion[2].allSatisfy(\.isNumber)
                && result.environment.torch == "2.13.0"
                && result.environment.transformers == "5.14.1"
                && result.environment.numpy == "2.5.1"
                && result.environment.pyarrow == "23.0.1",
            "The compression proof dependency versions are not pinned."
        )
        try require(
            result.environment.hfHome == "configured",
            "The worker did not confirm a configured Hugging Face cache."
        )
        try require(
            result.records.count == expected.validationBlocks
                && result.baselines.count == expected.validationBlocks,
            "The result does not contain the requested number of blocks."
        )
        try require(
            SecurityValidation.isLowercaseSHA256(result.resultSHA256)
                && SecurityValidation.isLowercaseSHA256(
                    result.selectedTokenIdsSHA256
                ),
            "A top-level canonical digest is malformed."
        )
        guard let aggregate = result.aggregate else {
            throw NSError(
                domain: "CoreLMBenchmark.RealLLMVerification",
                code: 2,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "The result must contain exactly one aggregate."
                ]
            )
        }
        try require(
            aggregate.configuration.backend == "voidtoken-v5"
                && aggregate.configurationId == "4c7be8c836aa7257"
                && aggregate.configuration.bitsByLayer
                    == [
                        9, 8, 8, 8, 8, 8, 8, 8,
                        9, 8, 8, 8, 8, 8, 8, 8,
                        8, 8, 8, 8, 8, 8, 8, 8
                    ]
                && aggregate.configuration.groupSize == 128
                && aggregate.configuration.transformBlockSize == 128
                && aggregate.configuration.scaleCompression == "zlib-9"
                && aggregate.configuration.codeCompression == "zlib-9"
                && aggregate.configuration.signMode == "none"
                && aggregate.configuration.schedule
                    == "group-kl-top-2-9bit-rest-8bit",
            "The result configuration does not match the frozen compression profile."
        )

        let expectedIndices = Array(
            expected.validationStartBlock..<endExclusive
        )
        try require(
            result.records.map(\.blockIndex) == expectedIndices
                && result.baselines.map(\.blockIndex) == expectedIndices,
            "Block indices are not exact and contiguous."
        )
        for (record, baseline) in zip(result.records, result.baselines) {
            try require(
                record.predictionTokens == 128
                    && baseline.predictionTokens == 128,
                "A record has unexpected model dimensions."
            )
            try require(
                record.configurationId == aggregate.configurationId
                    && record.payloadBytes > 0
                    && record.encodedFileBytes >= record.payloadBytes
                    && record.encodedFileBytes <= 4_706_304,
                "A record has invalid payload sizes or configuration identity."
            )
            let canonicalManifest = try canonicalJSON(record.containerManifest)
            let canonicalManifestSHA256 =
                SecurityValidation.sha256Hex(canonicalManifest)
            try require(
                record.containerManifest.count == 24
                    && SecurityValidation.isLowercaseSHA256(
                        record.containerManifestSHA256
                    )
                    && canonicalManifestSHA256
                        == record.containerManifestSHA256,
                "The canonical 24-layer container manifest is invalid."
            )
            var manifestPayloadBytes = 0
            var manifestContainerBytes = 0
            var manifestContainerDigests = Set<String>()
            for (expectedLayerIndex, entry) in
                record.containerManifest.enumerated() {
                let metadata = entry.metadata
                let expectedBits = [0, 8].contains(expectedLayerIndex) ? 9 : 8
                let expectedPackedBytes = expectedBits == 9 ? 110_304 : 98_048
                let metadataPayloadBytes =
                    try SecurityValidation.checkedAdd(
                        metadata.storedScaleBytes,
                        metadata.storedCodeBytes
                    )
                try require(
                    entry.layerIndex == expectedLayerIndex
                        && metadata.layerIndex == expectedLayerIndex
                        && metadata.bits == expectedBits
                        && metadata.bitsByColumnGroup == nil
                        && metadata.packedBytesByColumnGroup == nil
                        && metadata.shape == [383, 256]
                        && metadata.groupSize == 128
                        && metadata.groupsPerRow == 2
                        && metadata.transformBlockSize == 128
                        && metadata.codeCount == 383 * 256
                        && metadata.scaleCount == 383 * 2
                        && metadata.scaleBytes == 383 * 2 * 2
                        && metadata.packedBytes == expectedPackedBytes
                        && metadata.payloadBytes == entry.payloadBytes
                        && metadata.payloadBytes == metadataPayloadBytes
                        && metadata.storedScaleBytes > 0
                        && metadata.storedCodeBytes > 0,
                    "A layer manifest has inconsistent codec dimensions."
                )
                try require(
                    metadata.format == "voidtoken-rotated-entropy-v5"
                        && metadata.dtype == "float32"
                        && metadata.scaleDtype == "float16-le"
                        && metadata.quantization == "symmetric-max-abs-v1"
                        && metadata.codeMapping == "zigzag-symmetric-v1"
                        && metadata.transform
                            == "normalized-walsh-hadamard-v1"
                        && metadata.signDerivation
                            == "shake256-layer-column-v1"
                        && metadata.signMode == "none"
                        && metadata.scaleCompression == "zlib-9"
                        && metadata.codeCompression == "zlib-9"
                        && metadata.packing
                            == (
                                expectedBits <= 8
                                    ? "lsb-first-v1"
                                    : "byte-low-plus-lsb-high-fields-v1"
                            ),
                    "A layer manifest declares a foreign codec layout."
                )
                let containerDigestInserted = manifestContainerDigests.insert(
                    entry.containerSHA256
                ).inserted
                try require(
                    SecurityValidation.isLowercaseSHA256(metadata.inputSha256)
                        && SecurityValidation.isLowercaseSHA256(
                            metadata.payloadSha256
                        )
                        && SecurityValidation.isLowercaseSHA256(
                            metadata.reconstructionSha256
                        )
                        && SecurityValidation.isLowercaseSHA256(
                            entry.containerSHA256
                        )
                        && containerDigestInserted,
                    "A layer manifest digest is invalid or duplicated."
                )
                let maximumStoredScaleBytes = try zlibCompressBound(
                    metadata.scaleBytes
                )
                let maximumStoredCodeBytes = try zlibCompressBound(
                    metadata.packedBytes
                )
                try require(
                    metadata.storedScaleBytes
                        <= maximumStoredScaleBytes
                        && metadata.storedCodeBytes
                            <= maximumStoredCodeBytes,
                    "A layer manifest declares an impossible zlib stream."
                )
                let expectedContainerBytes =
                    try SecurityValidation.checkedAdd(
                        try SecurityValidation.checkedAdd(
                            8,
                            canonicalJSON(metadata).count
                        ),
                        entry.payloadBytes
                    )
                try require(
                    entry.payloadBytes > 0
                        && entry.containerBytes == expectedContainerBytes,
                    "A layer container byte count is not reconstructible."
                )
                manifestPayloadBytes = try SecurityValidation.checkedAdd(
                    manifestPayloadBytes,
                    entry.payloadBytes
                )
                manifestContainerBytes = try SecurityValidation.checkedAdd(
                    manifestContainerBytes,
                    entry.containerBytes
                )
            }
            try require(
                manifestPayloadBytes == record.payloadBytes
                    && manifestContainerBytes == record.encodedFileBytes,
                "Per-layer container sums differ from the record totals."
            )
            try require(
                baseline.layers == 24
                    && baseline.kvHeads == 2
                    && baseline.headDimension == 64
                    && baseline.trajectoryShapePerLayer == [383, 256],
                "A baseline has unexpected Qwen cache dimensions."
            )
            let firstScalarProduct =
                baseline.layers.multipliedReportingOverflow(
                    by: baseline.trajectoryShapePerLayer[0]
                )
            let scalarProduct =
                firstScalarProduct.partialValue.multipliedReportingOverflow(
                    by: baseline.trajectoryShapePerLayer[1]
                )
            let denseByteProduct =
                scalarProduct.partialValue.multipliedReportingOverflow(by: 2)
            try require(
                !firstScalarProduct.overflow
                    && !scalarProduct.overflow
                    && !denseByteProduct.overflow
                    && baseline.denseBF16Bytes
                        == denseByteProduct.partialValue
                    && record.denseBF16Bytes
                        == denseByteProduct.partialValue,
                "A cache scalar count is inconsistent with its dense bytes."
            )
            let cacheScalarCount = scalarProduct.partialValue
            try require(
                SecurityValidation.isLowercaseSHA256(record.tokenIdsSHA256)
                    && SecurityValidation.isLowercaseSHA256(
                        record.canonicalCacheBF16SHA256
                    )
                    && SecurityValidation.isLowercaseSHA256(
                        record.payloadSHA256
                    )
                    && record.tokenIdsSHA256 == baseline.tokenIdsSHA256
                    && record.canonicalCacheBF16SHA256
                        == baseline.canonicalCacheBF16SHA256,
                "A record or baseline digest is malformed or inconsistent."
            )
            try require(
                baseline.exactRebuildMaxAbsLogitDifference == 0
                    && baseline.layoutRebuildMaxAbsLogitDifference == 0
                    && baseline.exactRebuildTop1Identical
                    && baseline.layoutRebuildTop1Identical,
                "Structural cache replay is not exact."
            )
            let nativeBF16AgreementCount =
                baseline.nativeBF16Top1Agreement
                * Double(baseline.predictionTokens)
            try require(
                baseline.nativeBF16Top1Agreement.isFinite
                    && (0.0...1.0).contains(
                        baseline.nativeBF16Top1Agreement
                    )
                    && close(
                        nativeBF16AgreementCount,
                        nativeBF16AgreementCount.rounded()
                    ),
                "Native BF16 top-1 agreement is not k/128."
            )
            try require(
                close(
                    record.deltaNLLNatPerToken,
                    record.candidateNLLNatPerToken
                        - record.baselineNLLNatPerToken
                ),
                "A per-block ΔNLL value is inconsistent."
            )
            try require(
                record.baselineNLLNatPerToken >= 0
                    && record.candidateNLLNatPerToken >= 0
                    && record.baselineNLLNatPerToken <= 100
                    && record.candidateNLLNatPerToken <= 100
                    && record.meanKLDivergenceNat >= -1e-12
                    && record.meanKLDivergenceNat <= 100
                    && close(
                        record.baselineNLLNatPerToken,
                        baseline.canonicalBF16NLLNatPerToken
                    )
                    && close(
                        record.perplexityRatio,
                        exp(record.deltaNLLNatPerToken)
                    ),
                "A per-block likelihood metric is invalid."
            )
            try require(
                record.top1AgreementCount >= 0
                    && record.top1AgreementCount <= record.predictionTokens
                    && close(
                        record.top1Agreement,
                        Double(record.top1AgreementCount)
                            / Double(record.predictionTokens)
                ),
                "A per-block top-1 value is inconsistent."
            )
            try require(
                record.cacheReferenceSumSquares.isFinite
                    && record.cacheCandidateSumSquares.isFinite
                    && record.cacheDifferenceSumSquares.isFinite
                    && record.cacheDotProduct.isFinite
                    && record.cacheMaximumAbsoluteError.isFinite
                    && record.cacheReferenceSumSquares >= 0
                    && record.cacheCandidateSumSquares >= 0
                    && record.cacheDifferenceSumSquares >= 0
                    && record.cacheMaximumAbsoluteError >= 0
                    && record.cacheReferenceSumSquares <= 1e18
                    && record.cacheCandidateSumSquares <= 1e18
                    && record.cacheDifferenceSumSquares <= 1e18
                    && abs(record.cacheDotProduct) <= 1e18
                    && record.cacheMaximumAbsoluteError <= 1e9,
                "A per-block cache metric is invalid."
            )
            let cacheDifferenceIdentity =
                record.cacheReferenceSumSquares
                + record.cacheCandidateSumSquares
                - (2 * record.cacheDotProduct)
            try require(
                cacheClose(
                    record.cacheDifferenceSumSquares,
                    cacheDifferenceIdentity
                ),
                "A per-block cache accumulator identity is inconsistent."
            )
            let cacheNormProduct =
                sqrt(record.cacheReferenceSumSquares)
                * sqrt(record.cacheCandidateSumSquares)
            try require(
                lessThanOrClose(
                    abs(record.cacheDotProduct),
                    cacheNormProduct
                ),
                "A per-block cache violates Cauchy-Schwarz."
            )
            let maximumErrorSquared =
                record.cacheMaximumAbsoluteError
                * record.cacheMaximumAbsoluteError
            try require(
                lessThanOrClose(
                    maximumErrorSquared,
                    record.cacheDifferenceSumSquares
                )
                    && lessThanOrClose(
                        record.cacheDifferenceSumSquares,
                        Double(cacheScalarCount) * maximumErrorSquared
                    ),
                "A per-block cache violates maximum-error bounds."
            )
        }

        let predictionTokens = try checkedIntegerSum(
            result.records.map(\.predictionTokens)
        )
        let denseBytes = try checkedIntegerSum(
            result.records.map(\.denseBF16Bytes)
        )
        let encodedBytes = try checkedIntegerSum(
            result.records.map(\.encodedFileBytes)
        )
        let agreementCount = try checkedIntegerSum(
            result.records.map(\.top1AgreementCount)
        )
        try require(
            predictionTokens > 0 && denseBytes > 0 && encodedBytes > 0,
            "Aggregate denominators must be positive."
        )
        let weightedBaselineNLL = result.records.reduce(0.0) {
            $0 + $1.baselineNLLNatPerToken * Double($1.predictionTokens)
        } / Double(predictionTokens)
        let weightedCandidateNLL = result.records.reduce(0.0) {
            $0 + $1.candidateNLLNatPerToken * Double($1.predictionTokens)
        } / Double(predictionTokens)
        let weightedKL = result.records.reduce(0.0) {
            $0 + $1.meanKLDivergenceNat * Double($1.predictionTokens)
        } / Double(predictionTokens)
        let recomputedDeltaNLL = weightedCandidateNLL - weightedBaselineNLL
        let recomputedRatio = Double(denseBytes) / Double(encodedBytes)
        let recomputedTop1 = Double(agreementCount) / Double(predictionTokens)
        let payloadsUnique = Set(result.records.map(\.payloadSHA256)).count
            == result.records.count
        let referenceSum = try finiteSum(
            result.records.map(\.cacheReferenceSumSquares),
            label: "Reference cache sum"
        )
        let candidateSum = try finiteSum(
            result.records.map(\.cacheCandidateSumSquares),
            label: "Candidate cache sum"
        )
        let differenceSum = try finiteSum(
            result.records.map(\.cacheDifferenceSumSquares),
            label: "Cache difference sum"
        )
        let dotProduct = try finiteSum(
            result.records.map(\.cacheDotProduct),
            label: "Cache dot product"
        )
        let recomputedCacheNRMSE = sqrt(
            differenceSum / max(referenceSum, 1e-30)
        )
        let recomputedCacheCosine = dotProduct / max(
            sqrt(referenceSum * candidateSum),
            1e-30
        )
        try require(
            (-1.0...1.0).contains(recomputedCacheCosine),
            "Aggregate cache cosine is outside [-1, 1]."
        )
        let recomputedCacheMaximum = result.records
            .map(\.cacheMaximumAbsoluteError).max() ?? 0
        let recomputedPerplexityRatio = exp(recomputedDeltaNLL)

        try require(
            aggregate.blocks == result.records.count
                && aggregate.predictionTokens == predictionTokens
                && aggregate.denseBF16Bytes == denseBytes
                && aggregate.encodedFileBytes == encodedBytes,
            "Aggregate integer totals are inconsistent."
        )
        try require(
            close(aggregate.compressionRatioVsBF16, recomputedRatio)
                && close(
                    aggregate.baselineNLLNatPerToken,
                    weightedBaselineNLL
                )
                && close(
                    aggregate.candidateNLLNatPerToken,
                    weightedCandidateNLL
                )
                && close(aggregate.deltaNLLNatPerToken, recomputedDeltaNLL)
                && close(aggregate.top1Agreement, recomputedTop1)
                && close(aggregate.meanKLDivergenceNat, weightedKL)
                && close(
                    aggregate.perplexityRatio,
                    recomputedPerplexityRatio
                )
                && close(
                    aggregate.cacheNormalizedRMSE,
                    recomputedCacheNRMSE
                )
                && close(
                    aggregate.cacheCosineSimilarity,
                    recomputedCacheCosine
                )
                && close(
                    aggregate.cacheMaximumAbsoluteError,
                    recomputedCacheMaximum
                ),
            "Aggregate floating-point metrics are inconsistent."
        )
        try require(
            aggregate.allPayloadDigestsUnique && payloadsUnique,
            "Payload digest uniqueness is inconsistent."
        )

        let compressionGate = recomputedRatio >= 2
        let deltaNLLGate = recomputedDeltaNLL <= 0.01
        let top1Gate = recomputedTop1 >= 0.99
        try require(
            aggregate.gates.compression == compressionGate
                && aggregate.gates.deltaNLL == deltaNLLGate
                && aggregate.gates.top1Agreement == top1Gate
                && aggregate.pass
                    == (compressionGate && deltaNLLGate && top1Gate),
            "Recorded gates or verdict are inconsistent."
        )
    }

    private func writeRealLLMReceipt(
        outputURL: URL,
        settings: RealLLMRunSettings,
        terminationStatus: Int32?,
        error: String?
    ) {
        let aggregate = realLLMResult?.aggregate
        let scriptDigest = activeRealLLMScriptURL.flatMap {
            try? SecurityValidation.readRegularFile(
                at: $0,
                maximumBytes: 4 * 1024 * 1024,
                requireCurrentOwner: false
            )
        }.map(SecurityValidation.sha256Hex) ?? ""
        let resultFileDigest = (try? SecurityValidation.readRegularFile(
            at: outputURL,
            maximumBytes: SecurityValidation.maximumRealLLMResultBytes
        )).map(SecurityValidation.sha256Hex) ?? ""
        let runtimeManifestDigest = Bundle.main.resourceURL.flatMap {
            try? SecurityValidation.readRegularFile(
                at: $0.appendingPathComponent(
                    "python-runtime-manifest.json"
                ),
                maximumBytes:
                    SecurityValidation.maximumPythonRuntimeManifestBytes,
                requireCurrentOwner: false
            )
        }.map(SecurityValidation.sha256Hex) ?? ""
        let buildProvenanceData = Bundle.main.resourceURL.flatMap {
            try? SecurityValidation.readRegularFile(
                at: $0.appendingPathComponent("build-provenance.json"),
                maximumBytes: 1 * 1024 * 1024,
                requireCurrentOwner: false
            )
        }
        let buildProvenanceDigest = buildProvenanceData.map(
            SecurityValidation.sha256Hex
        ) ?? ""
        let buildProvenanceDocument: [String: Any] = buildProvenanceData
            .flatMap {
                try? JSONSerialization.jsonObject(
                    with: $0,
                    options: [.fragmentsAllowed]
                ) as? [String: Any]
            } ?? [:]
        let applicationExecutableDigest = Bundle.main.executableURL.flatMap {
            try? SecurityValidation.readRegularFile(
                at: $0,
                maximumBytes: 256 * 1024 * 1024,
                requireCurrentOwner: false
            )
        }.map(SecurityValidation.sha256Hex) ?? ""
        let successfulCurrentReceipt = error == nil
            && realLLMVerified
            && realLLMResult?.primaryEvidence != nil
            && aggregate != nil
        let failureReason = error
            ?? "Current result did not satisfy the retained-evidence receipt contract."
        let receiptError: Any = successfulCurrentReceipt
            ? NSNull() : failureReason
        var receipt: [String: Any] = [
            "schemaVersion": successfulCurrentReceipt
                ? "corelm-macos-app-real-llm-run-v5"
                : "corelm-macos-app-real-llm-failure-v1",
            "createdAt": ISO8601DateFormatter().string(from: Date()),
            "startedAt": realLLMStartedAt.map {
                ISO8601DateFormatter().string(from: $0)
            } ?? NSNull(),
            "application": [
                "bundleIdentifier": Bundle.main.bundleIdentifier ?? "",
                "bundleName": Bundle.main.bundleURL.lastPathComponent,
                "executableSHA256": applicationExecutableDigest,
                "version": Bundle.main.object(
                    forInfoDictionaryKey: "CFBundleShortVersionString"
                ) as? String ?? "",
                "processIdentifier": ProcessInfo.processInfo.processIdentifier
            ],
            "worker": [
                "processIdentifier": lastRealLLMWorkerPID ?? 0,
                "python": "signed-runtime-manifest",
                "pythonExecutableSHA256":
                    activeRealLLMPythonSHA256 ?? "",
                "runtimeManifestSHA256": runtimeManifestDigest,
                "script":
                    "Resources/RealLLM/app_proof_runner.py",
                "scriptSHA256": scriptDigest,
                "terminationStatus": terminationStatus ?? -1
            ],
            "protocol": [
                "device": "mps",
                "validationStartBlock": settings.validationStartBlock,
                "validationBlocks": settings.validationBlocks,
                "candidateIndex": settings.candidateIndex,
                "offlineRequested": true,
                "sanitizedChildEnvironment": true,
                "hfHome": "configured"
            ],
            "error": receiptError
        ]
        if successfulCurrentReceipt {
            receipt["result"] = [
                "path": outputURL.lastPathComponent,
                "resultFileSHA256": resultFileDigest,
                "resultSHA256": realLLMResult?.resultSHA256 ?? "",
                "compressionRatioVsBF16":
                    aggregate?.compressionRatioVsBF16 ?? 0,
                "deltaNLLNatPerToken":
                    aggregate?.deltaNLLNatPerToken ?? 0,
                "top1Agreement": aggregate?.top1Agreement ?? 0,
                "resultRole": "PUBLIC_VALIDATION_REGRESSION",
                "metricVerdict": aggregate?.pass == true ? "PASS" : "FAIL",
                "swiftStructuralVerification":
                    realLLMVerified ? "PASS" : "FAIL"
            ]
            if let primary = realLLMResult?.primaryEvidence {
                receipt["primaryEvidence"] = [
                    "schemaVersion": primary.schemaVersion,
                    "path": primary.path,
                    "manifestSHA256": primary.manifestSHA256,
                    "manifestBytes": primary.manifestBytes,
                    "containerCount": primary.containerCount,
                    "containerBytes": primary.containerBytes,
                    "blocks": primary.blocks,
                    "predictionTokens": primary.predictionTokens
                ]
                receipt["buildProvenance"] = [
                    "path": "Resources/build-provenance.json",
                    "sha256": buildProvenanceDigest,
                    "document": buildProvenanceDocument
                ]
            }
        } else {
            receipt["failure"] = [
                "intendedResult": outputURL.lastPathComponent,
                "resultFileSHA256": resultFileDigest,
                "resultPresent": !resultFileDigest.isEmpty,
                "swiftStructuralVerification":
                    realLLMVerified ? "PASS" : "FAIL"
            ]
        }
        if let proofChallengeNonce {
            receipt["challengeNonce"] = proofChallengeNonce
        }
        do {
            let data = try JSONSerialization.data(
                withJSONObject: receipt,
                options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
            )
            let receiptURL = outputURL
                .deletingLastPathComponent()
                .appendingPathComponent("app-run-receipt.json")
            try data.write(to: receiptURL, options: .atomic)
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600],
                ofItemAtPath: receiptURL.path
            )
        } catch {
            appendLog(
                "Could not write app receipt: \(error.localizedDescription)"
            )
        }
    }

    func revealRealLLMResult() {
        guard let realLLMResultURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([realLLMResultURL])
    }

    func stop() {
        guard let task = process else { return }
        forcedRealLLMFailure = "Compression proof stopped by the user."
        terminate(task: task, force: false)
        appendLog("Stop requested.")
    }

    func terminateForApplicationExit() {
        stopRealLLMSafetyWatchdog()
        endRealLLMPowerActivity()
        guard let task = process else { return }
        terminate(task: task, force: true)
    }

    private func beginRealLLMPowerActivity() {
        guard realLLMPowerActivity == nil else { return }
        realLLMPowerActivity = ProcessInfo.processInfo.beginActivity(
            options: [.idleSystemSleepDisabled],
            reason: "Running the Core LM compression proof on MPS"
        )
    }

    private func endRealLLMPowerActivity() {
        guard let activity = realLLMPowerActivity else { return }
        ProcessInfo.processInfo.endActivity(activity)
        realLLMPowerActivity = nil
    }

    private func confirmWorkerProcessGroup(for task: Process) throws {
        let identifier = pid_t(task.processIdentifier)
        // The production Python runner calls setpgid(0, 0) itself before it
        // imports numpy, Torch, or Transformers.  A parent-side setpgid after
        // Process.run races the child's exec and can fail with EACCES, so only
        // the child creates the group and this side confirms the invariant.
        for _ in 0..<200 {
            errno = 0
            let observed = getpgid(identifier)
            if observed == identifier {
                activeProcessGroupID = identifier
                return
            }
            if observed == -1 && errno == ESRCH {
                break
            }
            usleep(5_000)
        }
        activeProcessGroupID = nil
        throw SecurityValidationError.invalid(
            "Compression worker did not establish an independent process group."
        )
    }

    private func startRealLLMSafetyWatchdog(for task: Process) {
        stopRealLLMSafetyWatchdog()

        let pressureSource = DispatchSource.makeMemoryPressureSource(
            eventMask: .critical,
            queue: DispatchQueue(
                label: "com.corelm.benchmark.memory-pressure",
                qos: .utility
            )
        )
        pressureSource.setEventHandler { [weak self, weak task] in
            Task { @MainActor [weak self, weak task] in
                guard let self, let task else { return }
                self.abortRealLLMRun(
                    task: task,
                    reason: "Compression proof stopped at critical system memory pressure."
                )
            }
        }
        pressureSource.resume()
        memoryPressureSource = pressureSource

        realLLMTimeoutTask = Task { @MainActor [weak self, weak task] in
            do {
                try await Task.sleep(
                    for: .seconds(Self.realLLMHardTimeoutSeconds)
                )
            } catch {
                return
            }
            guard let self, let task else { return }
            self.abortRealLLMRun(
                task: task,
                reason: "Compression proof exceeded the 300-second safety limit."
            )
        }
    }

    private func stopRealLLMSafetyWatchdog() {
        realLLMTimeoutTask?.cancel()
        realLLMTimeoutTask = nil
        memoryPressureSource?.cancel()
        memoryPressureSource = nil
    }

    private func abortRealLLMRun(task: Process, reason: String) {
        guard process === task, task.isRunning else { return }
        forcedRealLLMFailure = reason
        appendLog(reason)
        terminate(task: task, force: false)
    }

    private func terminate(task: Process, force: Bool) {
        let group = activeProcessGroupID
        if let group {
            _ = ProcessGroupSupervisor.signal(
                force ? SIGKILL : SIGTERM,
                groupID: group
            )
        } else if task.isRunning {
            if force {
                _ = kill(task.processIdentifier, SIGKILL)
            } else {
                task.terminate()
            }
        }
        guard !force else { return }
        Task { @MainActor [weak task] in
            try? await Task.sleep(for: .seconds(2))
            if let group {
                // The leader can exit on SIGTERM before this grace period
                // ends.  Escalate against the captured group, independent of
                // mutable store state or the leader's continued existence.
                _ = ProcessGroupSupervisor.forceKillIfPresent(group)
            } else if let task, task.isRunning {
                _ = kill(task.processIdentifier, SIGKILL)
            }
        }
    }

    private func appendLog(_ message: String) {
        let normalized = Self.sanitizedPublicMessage(message)
        let bounded = String(
            normalized.prefix(SecurityValidation.maximumLogEntryCharacters)
        )
        log.append(
            bounded.count < normalized.count
                ? bounded + "\n[log entry truncated]" : bounded
        )
        if log.count > SecurityValidation.maximumLogEntries {
            log.removeFirst(log.count - SecurityValidation.maximumLogEntries)
        }
    }

    private func setError(_ message: String) {
        let sanitized = Self.sanitizedPublicMessage(message)
        errorMessage = String(
            sanitized.prefix(SecurityValidation.maximumLogEntryCharacters)
        )
    }

    private func preparePrivateResultsDirectory(_ directory: URL) throws {
        let applicationDirectory = directory.deletingLastPathComponent()
        try SecurityValidation.ensurePrivateDirectory(applicationDirectory)
        try SecurityValidation.ensurePrivateDirectory(directory)
    }

    private func portfolioCaptureReportBytes(
        in runDirectory: URL
    ) throws -> PortfolioCaptureReportBytes {
        let reportsDirectory = runDirectory.appendingPathComponent(
            "proof-reports", isDirectory: true
        )
        var fileStatus = stat()
        let status = reportsDirectory.path.withCString {
            lstat($0, &fileStatus)
        }
        if status != 0 {
            guard errno == ENOENT else {
                throw Self.captureFailure(
                    "CAPTURE_REPORT_DIRECTORY_INVALID"
                )
            }
            return PortfolioCaptureReportBytes(
                structural: nil, replay: nil, terminal: nil
            )
        }
        try SecurityValidation.validateDirectory(
            reportsDirectory, requireCurrentOwner: true
        )
        let entries = try FileManager.default.contentsOfDirectory(
            at: reportsDirectory,
            includingPropertiesForKeys: nil,
            options: []
        )
        guard Set(entries.map(\.lastPathComponent)) == [
            "fresh-model-replay.json",
            "structural-verifier.json",
            "terminal.log"
        ] else {
            throw Self.captureFailure("CAPTURE_REPORT_TOPOLOGY_INVALID")
        }
        return try PortfolioCaptureReportBytes(
            structural: SecurityValidation.readRegularFile(
                at: reportsDirectory.appendingPathComponent(
                    "structural-verifier.json"
                ),
                maximumBytes: 64 * 1_024
            ),
            replay: SecurityValidation.readRegularFile(
                at: reportsDirectory.appendingPathComponent(
                    "fresh-model-replay.json"
                ),
                maximumBytes: 64 * 1_024
            ),
            terminal: SecurityValidation.readRegularFile(
                at: reportsDirectory.appendingPathComponent("terminal.log"),
                maximumBytes: 256
            )
        )
    }

    private func loadExactPortfolioCaptureResult(
        runIdentifier: String,
        readyFilePath: String
    ) {
        do {
            portfolioReadinessPublishing = false
            portfolioReadinessPublished = false
            _ = try Self.validatedPortfolioReadyFileURL(
                path: readyFilePath
            )
            guard let uuid = UUID(uuidString: runIdentifier),
                  uuid.uuidString.lowercased() == runIdentifier else {
                throw Self.captureFailure("CAPTURE_RESULT_ID_INVALID")
            }
            try SecurityValidation.validateDirectory(
                realLLMResultsDirectory, requireCurrentOwner: true
            )
            let runDirectory = realLLMResultsDirectory.appendingPathComponent(
                runIdentifier, isDirectory: true
            )
            try SecurityValidation.validateDirectory(
                runDirectory, requireCurrentOwner: true
            )
            guard runDirectory.lastPathComponent == runIdentifier else {
                throw Self.captureFailure("CAPTURE_RESULT_DIRECTORY_INVALID")
            }

            let resultURL = runDirectory.appendingPathComponent(
                "validation-064-071.json"
            )
            let resultData = try SecurityValidation.readRegularFile(
                at: resultURL,
                maximumBytes: SecurityValidation.maximumRealLLMResultBytes
            )
            let canonicalDigest = try SecurityValidation
                .verifiedCanonicalResultDigest(from: resultData)
            let decoded = try JSONDecoder().decode(
                RealLLMResult.self, from: resultData
            )
            guard decoded.schemaVersion
                    == "corelm-voidtoken-v5-validation-development-v3",
                  decoded.resultSHA256 == canonicalDigest,
                  decoded.protocolInfo.validationStartBlock
                    == CompressionProofRunPolicy.registeredStartBlock,
                  decoded.protocolInfo.validationBlocks
                    == CompressionProofRunPolicy.registeredBlockCount else {
                throw Self.captureFailure("CAPTURE_RESULT_CONTRACT_INVALID")
            }
            let settings = RealLLMRunSettings(
                validationStartBlock:
                    CompressionProofRunPolicy.registeredStartBlock,
                validationBlocks:
                    CompressionProofRunPolicy.registeredBlockCount
            )
            try verifyRealLLMResult(decoded, expected: settings)
            try verifyPrimaryEvidence(decoded, outputURL: resultURL)

            let receiptURL = runDirectory.appendingPathComponent(
                "app-run-receipt.json"
            )
            let receiptData = try SecurityValidation.readRegularFile(
                at: receiptURL, maximumBytes: 64 * 1_024
            )
            let reports = try portfolioCaptureReportBytes(in: runDirectory)
            let snapshot = try Self.validatedPortfolioCaptureSnapshot(
                result: decoded,
                resultFileSHA256: SecurityValidation.sha256Hex(resultData),
                receiptData: receiptData,
                receiptFileSHA256:
                    SecurityValidation.sha256Hex(receiptData),
                runIdentifier: runIdentifier,
                structuralReportData: reports.structural,
                replayReportData: reports.replay,
                terminalReportData: reports.terminal
            )

            guard Bundle.main.bundleURL.pathExtension == "app",
                  Bundle.main.bundleIdentifier == "com.corelm.benchmark",
                  let resources = Bundle.main.resourceURL,
                  let executable = Bundle.main.executableURL else {
                throw Self.captureFailure("CAPTURE_APP_BUNDLE_INVALID")
            }
            try SecurityValidation.validateBundleSignature(
                Bundle.main.bundleURL
            )
            let bundledProvenance = try SecurityValidation.readRegularFile(
                at: resources.appendingPathComponent(
                    "build-provenance.json"
                ),
                maximumBytes: 1 * 1_024 * 1_024,
                requireCurrentOwner: false
            )
            let executableData = try SecurityValidation.readRegularFile(
                at: executable,
                maximumBytes: 256 * 1_024 * 1_024,
                requireCurrentOwner: false
            )
            guard SecurityValidation.sha256Hex(bundledProvenance)
                    == snapshot.buildProvenanceSHA256,
                  SecurityValidation.sha256Hex(executableData)
                    == snapshot.applicationExecutableSHA256 else {
                throw Self.captureFailure("CAPTURE_APP_BINDING_MISMATCH")
            }

            realLLMSettings = settings
            realLLMResult = decoded
            realLLMResultURL = resultURL
            realLLMVerified = true
            realLLMVerificationMessage =
                "Swift structural verification PASS"
            progress = 1
            portfolioCaptureSnapshot = snapshot
            portfolioCaptureStatusCode = "CAPTURE_RESULT_READY"
        } catch {
            portfolioReadinessPublishing = false
            portfolioReadinessPublished = false
            realLLMResult = nil
            realLLMResultURL = nil
            realLLMVerified = false
            portfolioCaptureSnapshot = nil
            portfolioCaptureStatusCode = "CAPTURE_EVIDENCE_INVALID"
        }
    }

    func publishPortfolioCaptureReadinessFromRenderedView() async {
        guard !portfolioReadinessPublished,
              !portfolioReadinessPublishing,
              portfolioCaptureStatusCode == "CAPTURE_RESULT_READY",
              let snapshot = portfolioCaptureSnapshot,
              case let .result(runIdentifier, readyFilePath)
                = portfolioCaptureRequest,
              snapshot.runIdentifier == runIdentifier else {
            return
        }
        portfolioReadinessPublishing = true
        await Task.yield()
        guard portfolioCaptureStatusCode == "CAPTURE_RESULT_READY",
              portfolioCaptureSnapshot == snapshot else {
            portfolioReadinessPublishing = false
            return
        }
        do {
            try Self.writePortfolioCaptureReadiness(
                at: URL(fileURLWithPath: readyFilePath),
                runIdentifier: runIdentifier,
                resultFileSHA256: snapshot.resultFileSHA256,
                receiptFileSHA256: snapshot.receiptFileSHA256,
                applicationExecutableSHA256:
                    snapshot.applicationExecutableSHA256,
                metricVerdict: snapshot.metricVerdict,
                compressionRatioVsBF16:
                    snapshot.compressionRatioVsBF16,
                deltaNLLNatPerToken: snapshot.deltaNLLNatPerToken,
                top1Agreement: snapshot.top1Agreement
            )
            portfolioReadinessPublished = true
            portfolioReadinessPublishing = false
        } catch {
            portfolioReadinessPublishing = false
            portfolioReadinessPublished = false
            realLLMResult = nil
            realLLMResultURL = nil
            realLLMVerified = false
            portfolioCaptureSnapshot = nil
            portfolioCaptureStatusCode = "CAPTURE_EVIDENCE_INVALID"
        }
    }

    func reloadLatestRealLLMResult() {
        do {
            try preparePrivateResultsDirectory(realLLMResultsDirectory)
            let directories = try FileManager.default.contentsOfDirectory(
                at: realLLMResultsDirectory,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            )
            guard directories.count
                    <= SecurityValidation.maximumSavedResultFiles else {
                throw SecurityValidationError.invalid(
                    "Too many saved compression-proof run directories."
                )
            }
            var candidates: [(URL, Date)] = []
            for directory in directories {
                guard (try? SecurityValidation.validateDirectory(
                    directory,
                    requireCurrentOwner: true
                )) != nil else {
                    continue
                }
                let files = try FileManager.default.contentsOfDirectory(
                    at: directory,
                    includingPropertiesForKeys: [.contentModificationDateKey],
                    options: [.skipsHiddenFiles]
                )
                for file in files where file.pathExtension == "json"
                    && file.lastPathComponent != "app-run-receipt.json" {
                    let date = (try? file.resourceValues(
                        forKeys: [.contentModificationDateKey]
                    ).contentModificationDate) ?? .distantPast
                    candidates.append((file, date))
                }
                if candidates.count
                    > SecurityValidation.maximumSavedResultFiles {
                    throw SecurityValidationError.invalid(
                        "Too many saved compression-proof result files."
                    )
                }
            }
            for (candidate, _) in candidates.sorted(
                by: { $0.1 > $1.1 }
            ) {
                do {
                    let data = try SecurityValidation.readRegularFile(
                        at: candidate,
                        maximumBytes:
                            SecurityValidation.maximumRealLLMResultBytes
                    )
                    let canonicalDigest =
                        try SecurityValidation.verifiedCanonicalResultDigest(
                            from: data
                        )
                    let decoded = try JSONDecoder().decode(
                        RealLLMResult.self,
                        from: data
                    )
                    guard decoded.resultSHA256 == canonicalDigest else {
                        throw SecurityValidationError.invalid(
                            "Decoded and canonical result digests differ."
                        )
                    }
                    let loadedSettings = RealLLMRunSettings(
                        validationStartBlock:
                            decoded.protocolInfo.validationStartBlock,
                        validationBlocks:
                            decoded.protocolInfo.validationBlocks
                    )
                    let verificationSettings =
                        CompressionProofRunPolicy.effectiveSettings(
                            requested: loadedSettings
                        )
                    try verifyRealLLMResult(
                        decoded,
                        expected: verificationSettings
                    )
                    guard decoded.schemaVersion
                            == "corelm-voidtoken-v5-validation-development-v3"
                    else {
                        throw SecurityValidationError.invalid(
                            "Saved proof lacks retained primary evidence."
                        )
                    }
                    try verifyPrimaryEvidence(
                        decoded,
                        outputURL: candidate
                    )
                    realLLMSettings = verificationSettings
                    realLLMResult = decoded
                    realLLMResultURL = candidate
                    realLLMVerified = true
                    realLLMVerificationMessage =
                        "Swift structural verification PASS"
                    progress = 1
                    return
                } catch {
                    appendLog(
                        "Ignored invalid saved compression-proof result: "
                            + error.localizedDescription
                    )
                }
            }
        } catch {
            appendLog(
                "Could not reload saved compression-proof results: "
                    + error.localizedDescription
            )
        }
    }

    func automatedRunIfRequested() async {
        switch portfolioCaptureRequest {
        case .preflight:
            await prepareAutomatedRunWindow()
            return
        case .live:
            return
        case let .result(runIdentifier, readyFilePath):
            await prepareAutomatedRunWindow()
            loadExactPortfolioCaptureResult(
                runIdentifier: runIdentifier,
                readyFilePath: readyFilePath
            )
            return
        case .invalid:
            await prepareAutomatedRunWindow()
            return
        case .none:
            break
        }
        if commandLineArguments.contains("--automated-compression-proof") {
            await prepareAutomatedRunWindow()
            await runAutomatedCompressionProof()
            return
        }
        guard commandLineArguments.contains("--app-launch-check") else {
            return
        }
        await prepareAutomatedRunWindow()
        let visibleWindows = NSApplication.shared.windows.filter {
            $0.isVisible && $0.contentView != nil
        }
        let windowReady = visibleWindows.contains {
            $0.frame.width >= 1000 && $0.frame.height >= 650
        }
        let passed = errorMessage == nil && windowReady
        appendLog(passed ? "APP LAUNCH PASS" : "APP LAUNCH FAIL")
        let summary: [String: Any] = [
            "status": passed ? "PASS" : "FAIL",
            "visibleWindows": visibleWindows.count,
            "windowReady": windowReady,
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

    private func prepareAutomatedRunWindow() async {
        NSApplication.shared.activate(ignoringOtherApps: true)
        for _ in 0..<10 {
            for window in NSApplication.shared.windows
                where window.contentView != nil {
                window.makeKeyAndOrderFront(nil)
            }
            if NSApplication.shared.windows.contains(where: {
                $0.isVisible && $0.contentView != nil
                    && $0.frame.width >= 1000 && $0.frame.height >= 650
            }) {
                return
            }
            try? await Task.sleep(for: .milliseconds(100))
        }
    }

    private func runAutomatedCompressionProof() async {
        let visibleWindows = NSApplication.shared.windows.filter {
            $0.isVisible && $0.contentView != nil
        }
        let windowReady = visibleWindows.contains {
            $0.frame.width >= 1000 && $0.frame.height >= 650
        }
        realLLMSettings.validationStartBlock =
            CompressionProofRunPolicy.registeredStartBlock
        realLLMSettings.validationBlocks =
            CompressionProofRunPolicy.registeredBlockCount
        runRealLLM()

        let deadline = Date().addingTimeInterval(600)
        while isRunning && Date() < deadline {
            try? await Task.sleep(for: .milliseconds(200))
        }
        if isRunning {
            stop()
            endRealLLMPowerActivity()
            errorMessage = "Compression-proof app run timed out."
        }
        let aggregate = realLLMResult?.aggregate
        let completed = !isRunning
            && errorMessage == nil
            && windowReady
            && realLLMVerified
            && aggregate != nil
            && realLLMResult?.environment.device == "mps"
            && realLLMResult?.protocolInfo.modelRepository
                == "Qwen/Qwen2.5-0.5B"
        let summary: [String: Any] = [
            "status": completed ? "VERIFIED" : "FAIL",
            "executionOrigin": "CoreLMBenchmark.app",
            "bundleIdentifier": Bundle.main.bundleIdentifier ?? "",
            "appProcessIdentifier": ProcessInfo.processInfo.processIdentifier,
            "workerProcessIdentifier": lastRealLLMWorkerPID ?? 0,
            "visibleWindows": visibleWindows.count,
            "windowReady": windowReady,
            "model": realLLMResult?.protocolInfo.modelRepository ?? "",
            "modelRevision": realLLMResult?.protocolInfo.modelRevision ?? "",
            "device": realLLMResult?.environment.device ?? "",
            "validationStartBlock":
                realLLMResult?.protocolInfo.validationStartBlock ?? -1,
            "validationBlocks":
                realLLMResult?.protocolInfo.validationBlocks ?? -1,
            "compressionRatioVsBF16":
                aggregate?.compressionRatioVsBF16 ?? 0,
            "deltaNLLNatPerToken": aggregate?.deltaNLLNatPerToken ?? 0,
            "top1Agreement": aggregate?.top1Agreement ?? 0,
            "resultRole": "PUBLIC_VALIDATION_REGRESSION",
            "metricVerdict": aggregate?.pass == true ? "PASS" : "FAIL",
            "swiftStructuralVerification":
                realLLMVerified ? "PASS" : "FAIL",
            "resultSHA256": realLLMResult?.resultSHA256 ?? "",
            "resultIdentifier": realLLMResultURL.flatMap {
                Self.publicResultLabel(for: $0)
            } ?? "",
            "error": errorMessage ?? ""
        ]
        if let data = try? JSONSerialization.data(
            withJSONObject: summary, options: [.prettyPrinted, .sortedKeys]
        ), let text = String(data: data, encoding: .utf8) {
            print(text)
        }
        fflush(stdout)
        exit(completed ? EXIT_SUCCESS : EXIT_FAILURE)
    }
}
