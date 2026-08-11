import CryptoKit
import Darwin
import Foundation

enum OperatorValidationError: LocalizedError, Equatable {
    case invalid(String)

    var errorDescription: String? {
        switch self {
        case let .invalid(message):
            message
        }
    }
}

enum OperatorAction: String, CaseIterable, Equatable {
    case verifyRepository
    case buildApp
    case fullSystemProof
    case openBuiltApplication

    var title: String {
        switch self {
        case .verifyRepository:
            "Verify Repository"
        case .buildApp:
            "Build App"
        case .fullSystemProof:
            "Full System Proof"
        case .openBuiltApplication:
            "Open Built App"
        }
    }

    var coreLMArguments: [String]? {
        switch self {
        case .verifyRepository:
            ["verify"]
        case .buildApp:
            ["macos", "build"]
        case .fullSystemProof:
            ["macos", "proof"]
        case .openBuiltApplication:
            nil
        }
    }

    var launcherToken: String {
        switch self {
        case .verifyRepository:
            "verify"
        case .buildApp:
            "build"
        case .fullSystemProof:
            "proof"
        case .openBuiltApplication:
            "app-check"
        }
    }

    var runningDescription: String {
        switch self {
        case .verifyRepository:
            "Running the exact repository verification gate."
        case .buildApp:
            "Building and validating the canonical local application."
        case .fullSystemProof:
            "Running the complete fresh-runtime Qwen proof and replay."
        case .openBuiltApplication:
            "Revalidating the canonical application before opening it."
        }
    }
}

enum OperatorOutcome: Equatable {
    case repositoryVerified
    case applicationBuilt
    case proofPass
    case proofVerifiedMetricFail
    case applicationOpened

    var publicMessage: String {
        switch self {
        case .repositoryVerified:
            "Repository verification completed successfully."
        case .applicationBuilt:
            "Canonical local application build completed successfully."
        case .proofPass:
            "END-TO-END PROOF PASS"
        case .proofVerifiedMetricFail:
            "END-TO-END PROOF VERIFIED — METRIC FAIL"
        case .applicationOpened:
            "Opened the revalidated dist/CoreLMBenchmark.app."
        }
    }
}

enum OperatorState: Equatable {
    case idle
    case running(OperatorAction)
    case succeeded(OperatorAction, OperatorOutcome)
    case failed(OperatorAction, String)

    var isRunning: Bool {
        if case .running = self {
            return true
        }
        return false
    }
}

enum OperatorProofTerminalState: Equatable {
    case none
    case proofPass
    case metricFail
    case ambiguous
}

struct OperatorTerminalObservation: Equatable {
    let proof: OperatorProofTerminalState
}

struct OperatorLaunchConfiguration {
    let project: OperatorProject
    let commandAuthority: OperatorCommandAuthority

    init(arguments: [String]) throws {
        let payload = Array(arguments.dropFirst())
        guard payload.count == 6,
              payload[0] == "--project-root",
              payload[2] == "--command-launcher",
              payload[4] == "--group-file" else {
            throw OperatorValidationError.invalid(
                "Core LM Operator accepts only its exact launcher authority."
            )
        }
        let project = try OperatorProject(rootPath: payload[1])
        self.project = project
        commandAuthority = try OperatorCommandAuthority(
            launcherPath: payload[3],
            groupFilePath: payload[5],
            project: project
        )
    }
}

struct OperatorProject: Equatable {
    static let maximumControlFileBytes = 32 * 1024 * 1024
    static let controlFilePaths = [
        "corelm",
        "Package.swift",
        "scripts/verify-python.sh",
        "platforms/macos/scripts/build-app.sh",
        "platforms/macos/scripts/run-proof.sh",
        "platforms/macos/scripts/package-app.sh",
        "security/verify_app_bundle.sh",
        "security/generate_build_provenance.py",
        "security/generate_app_proof_core.py",
        "security/verify_git_checkout.py"
    ]

    let root: URL
    let dispatcher: URL
    let verifier: URL
    let controlSHA256: [String: String]

    init(rootPath: String) throws {
        let declared = try OperatorSecurePath.canonicalExistingURL(
            rootPath,
            label: "operator project root"
        )
        try OperatorSecurePath.requireDirectory(
            declared,
            label: "operator project root"
        )
        try OperatorSecurePath.requireDirectory(
            declared.appendingPathComponent("platforms/macos"),
            label: "platforms/macos"
        )

        var hashes: [String: String] = [:]
        for relative in Self.controlFilePaths {
            let candidate = declared.appendingPathComponent(relative)
            let executable = relative.hasSuffix(".sh") || relative == "corelm"
            hashes[relative] = try OperatorSecurePath.regularFileSHA256(
                candidate,
                label: "operator control file \(relative)",
                executable: executable,
                maximumBytes: Self.maximumControlFileBytes
            )
        }
        root = declared
        dispatcher = declared.appendingPathComponent("corelm")
        verifier = declared.appendingPathComponent(
            "security/verify_app_bundle.sh"
        )
        controlSHA256 = hashes
    }

    var dispatcherSHA256: String {
        controlSHA256["corelm"] ?? ""
    }

    var verifierSHA256: String {
        controlSHA256["security/verify_app_bundle.sh"] ?? ""
    }

    func revalidateControlSurface() throws {
        for relative in Self.controlFilePaths {
            let expected = controlSHA256[relative]
            let executable = relative.hasSuffix(".sh") || relative == "corelm"
            let actual = try OperatorSecurePath.regularFileSHA256(
                root.appendingPathComponent(relative),
                label: "operator control file \(relative)",
                executable: executable,
                maximumBytes: Self.maximumControlFileBytes
            )
            guard actual == expected else {
                throw OperatorValidationError.invalid(
                    "Operator control file changed during this session: \(relative)."
                )
            }
        }
    }

    func validatedBuiltApplication() throws -> URL {
        let dist = root.appendingPathComponent("dist", isDirectory: true)
        let app = dist.appendingPathComponent(
            "CoreLMBenchmark.app", isDirectory: true
        )
        try OperatorSecurePath.requireDirectory(
            dist,
            label: "canonical dist directory"
        )
        try OperatorSecurePath.requireDirectory(
            app,
            label: "canonical built application"
        )
        let contents = app.appendingPathComponent(
            "Contents", isDirectory: true
        )
        let macOS = contents.appendingPathComponent(
            "MacOS", isDirectory: true
        )
        try OperatorSecurePath.requireDirectory(
            contents,
            label: "canonical built application Contents directory"
        )
        try OperatorSecurePath.requireDirectory(
            macOS,
            label: "canonical built application MacOS directory"
        )
        _ = try OperatorSecurePath.regularFileSHA256(
            macOS.appendingPathComponent("CoreLMBenchmarkApp"),
            label: "canonical built application executable",
            executable: true,
            maximumBytes: 512 * 1024 * 1024
        )
        _ = try OperatorSecurePath.regularFileSHA256(
            contents.appendingPathComponent("Info.plist"),
            label: "canonical built application Info.plist",
            executable: false,
            maximumBytes: 1024 * 1024
        )
        return app
    }
}

struct OperatorCommandAuthority: Equatable {
    static let launcherMaximumBytes = 32 * 1024 * 1024

    let launcher: URL
    let launcherSHA256: String
    let controlDirectory: URL
    let groupFile: URL

    init(
        launcherPath: String,
        groupFilePath: String,
        project: OperatorProject
    ) throws {
        let launcher = try OperatorSecurePath.canonicalExistingURL(
            launcherPath,
            label: "operator command launcher"
        )
        let launcherDigest = try OperatorSecurePath.regularFileSHA256(
            launcher,
            label: "operator command launcher",
            executable: true,
            maximumBytes: Self.launcherMaximumBytes
        )
        let groupFile = try OperatorSecurePath.canonicalAbsentURL(
            groupFilePath,
            label: "operator process-group marker"
        )
        guard groupFile.lastPathComponent == "active-command-pgid" else {
            throw OperatorValidationError.invalid(
                "Operator process-group marker has an unexpected name."
            )
        }
        let controlDirectory = groupFile.deletingLastPathComponent()
        try OperatorSecurePath.requireDirectory(
            controlDirectory,
            label: "operator process-group control directory",
            exactMode: 0o700
        )
        guard !OperatorSecurePath.isDescendant(
            controlDirectory,
            of: project.root
        ) else {
            throw OperatorValidationError.invalid(
                "Operator process control must remain outside the checkout."
            )
        }
        self.launcher = launcher
        launcherSHA256 = launcherDigest
        self.controlDirectory = controlDirectory
        self.groupFile = groupFile
    }

    func prepareForSpawn() throws {
        let actual = try OperatorSecurePath.regularFileSHA256(
            launcher,
            label: "operator command launcher",
            executable: true,
            maximumBytes: Self.launcherMaximumBytes
        )
        guard actual == launcherSHA256 else {
            throw OperatorValidationError.invalid(
                "Operator command launcher changed during this session."
            )
        }
        try OperatorSecurePath.requireDirectory(
            controlDirectory,
            label: "operator process-group control directory",
            exactMode: 0o700
        )
        guard !FileManager.default.fileExists(atPath: groupFile.path) else {
            throw OperatorValidationError.invalid(
                "Operator process-group marker already exists."
            )
        }
    }

    func revalidateLauncher() throws {
        let actual = try OperatorSecurePath.regularFileSHA256(
            launcher,
            label: "operator command launcher",
            executable: true,
            maximumBytes: Self.launcherMaximumBytes
        )
        guard actual == launcherSHA256 else {
            throw OperatorValidationError.invalid(
                "Operator command launcher changed while a command ran."
            )
        }
    }
}

enum OperatorTerminalClassifier {
    static func outcome(
        action: OperatorAction,
        exitStatus: Int32,
        observation: OperatorTerminalObservation,
        builtApplicationAvailable: Bool
    ) throws -> OperatorOutcome {
        guard exitStatus == 0 else {
            throw OperatorValidationError.invalid(
                "\(action.title) exited with status \(exitStatus)."
            )
        }
        switch action {
        case .verifyRepository:
            guard observation.proof == .none else {
                throw OperatorValidationError.invalid(
                    "Repository verification emitted an unexpected proof terminal."
                )
            }
            return .repositoryVerified
        case .buildApp:
            guard observation.proof == .none,
                  builtApplicationAvailable else {
                throw OperatorValidationError.invalid(
                    "Build command did not retain its reverified canonical application."
                )
            }
            return .applicationBuilt
        case .fullSystemProof:
            guard builtApplicationAvailable else {
                throw OperatorValidationError.invalid(
                    "Proof command did not retain its reverified canonical application."
                )
            }
            switch observation.proof {
            case .proofPass:
                return .proofPass
            case .metricFail:
                return .proofVerifiedMetricFail
            case .none, .ambiguous:
                throw OperatorValidationError.invalid(
                    "Proof command did not emit exactly one canonical terminal outcome."
                )
            }
        case .openBuiltApplication:
            guard observation.proof == .none,
                  builtApplicationAvailable else {
                throw OperatorValidationError.invalid(
                    "Application revalidation did not retain the canonical bundle."
                )
            }
            return .applicationOpened
        }
    }
}

enum OperatorSecurePath {
    static func canonicalExistingURL(
        _ path: String,
        label: String
    ) throws -> URL {
        guard path.hasPrefix("/"), !path.utf8.contains(0) else {
            throw OperatorValidationError.invalid(
                "\(label) must be an absolute canonical path."
            )
        }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        guard url.path == path,
              url.resolvingSymlinksInPath().standardizedFileURL == url else {
            throw OperatorValidationError.invalid(
                "\(label) must be canonical and contain no symlink."
            )
        }
        return url
    }

    static func canonicalAbsentURL(
        _ path: String,
        label: String
    ) throws -> URL {
        guard path.hasPrefix("/"), !path.utf8.contains(0) else {
            throw OperatorValidationError.invalid(
                "\(label) must be an absolute canonical path."
            )
        }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        guard url.path == path else {
            throw OperatorValidationError.invalid(
                "\(label) must be canonical."
            )
        }
        let parent = url.deletingLastPathComponent()
        guard parent.resolvingSymlinksInPath().standardizedFileURL == parent,
              !FileManager.default.fileExists(atPath: url.path) else {
            throw OperatorValidationError.invalid(
                "\(label) parent must be canonical and the target must be absent."
            )
        }
        return url
    }

    static func requireDirectory(
        _ url: URL,
        label: String,
        exactMode: mode_t? = nil
    ) throws {
        guard url.resolvingSymlinksInPath().standardizedFileURL
                == url.standardizedFileURL else {
            throw OperatorValidationError.invalid(
                "\(label) must not contain a symlink."
            )
        }
        var status = stat()
        guard url.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFDIR,
              status.st_uid == getuid(),
              (status.st_mode & 0o022) == 0,
              exactMode == nil || (status.st_mode & 0o777) == exactMode else {
            throw OperatorValidationError.invalid(
                "\(label) must be an owner-controlled non-symlink directory."
            )
        }
    }

    static func regularFileSHA256(
        _ url: URL,
        label: String,
        executable: Bool,
        maximumBytes: Int
    ) throws -> String {
        var status = stat()
        guard url.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG,
              status.st_uid == getuid(),
              (status.st_mode & 0o022) == 0,
              !executable || access(url.path, X_OK) == 0,
              status.st_size > 0,
              status.st_size <= maximumBytes else {
            throw OperatorValidationError.invalid(
                "\(label) must be an owner-controlled regular non-symlink file."
            )
        }
        let data = try Data(contentsOf: url, options: [.mappedIfSafe])
        guard data.count == status.st_size else {
            throw OperatorValidationError.invalid(
                "\(label) changed while it was read."
            )
        }
        return SHA256.hash(data: data).map {
            String(format: "%02x", $0)
        }.joined()
    }

    static func isDescendant(_ candidate: URL, of root: URL) -> Bool {
        let candidatePath = candidate.standardizedFileURL.path + "/"
        let rootPath = root.standardizedFileURL.path + "/"
        return candidatePath.hasPrefix(rootPath)
    }
}
