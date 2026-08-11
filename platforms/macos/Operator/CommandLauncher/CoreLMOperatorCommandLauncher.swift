import CryptoKit
import Darwin
import Foundation

private enum LauncherFailure: LocalizedError {
    case invalid(String)

    var errorDescription: String? {
        switch self {
        case let .invalid(message):
            message
        }
    }
}

private enum LauncherAction: String {
    case verify
    case build
    case proof
    case appCheck = "app-check"

    var dispatcherArguments: [String]? {
        switch self {
        case .verify:
            ["verify"]
        case .build:
            ["macos", "build"]
        case .proof:
            ["macos", "proof"]
        case .appCheck:
            nil
        }
    }

    var requiresPostCommandAppVerification: Bool {
        self == .build || self == .proof
    }
}

private struct LauncherConfiguration {
    let groupFile: URL
    let dispatcher: URL
    let dispatcherSHA256: String
    let verifier: URL
    let verifierSHA256: String
    let projectRoot: URL
    let application: URL
    let action: LauncherAction

    init(arguments: [String], environment: [String: String]) throws {
        let payload = Array(arguments.dropFirst())
        guard payload.count == 12,
              payload[0] == "--group-file",
              payload[2] == "--dispatcher",
              payload[4] == "--dispatcher-sha256",
              payload[6] == "--verifier",
              payload[8] == "--verifier-sha256",
              payload[10] == "--action",
              let action = LauncherAction(rawValue: payload[11]) else {
            throw LauncherFailure.invalid(
                "command launcher accepts only its exact fixed grammar"
            )
        }
        let allowedEnvironment = Set([
            "HOME", "TMPDIR", "PATH", "LANG", "LC_ALL"
        ])
        var exactEnvironment = allowedEnvironment
        if let coreFoundationEncoding = environment["__CF_USER_TEXT_ENCODING"] {
            let fields = coreFoundationEncoding.split(separator: ":")
            guard fields.count == 3,
                  let encodedUser = Self.hexField(fields[0]),
                  Self.hexField(fields[1]) != nil,
                  Self.hexField(fields[2]) != nil,
                  encodedUser == getuid() else {
                throw LauncherFailure.invalid(
                    "system text-encoding environment is malformed"
                )
            }
            exactEnvironment.insert("__CF_USER_TEXT_ENCODING")
        }
        guard Set(environment.keys) == exactEnvironment,
              environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin",
              environment["LANG"] == "C",
              environment["LC_ALL"] == "C",
              let home = environment["HOME"],
              let temporary = environment["TMPDIR"] else {
            throw LauncherFailure.invalid(
                "command launcher environment is not exact and sterile"
            )
        }
        try Self.requireDirectory(home, label: "HOME", exactMode: nil)
        try Self.requireDirectory(
            temporary,
            label: "TMPDIR",
            exactMode: 0o700
        )

        let dispatcher = try Self.canonicalExistingURL(
            payload[3],
            label: "dispatcher"
        )
        let projectRoot = dispatcher.deletingLastPathComponent()
        try Self.requireDirectory(
            projectRoot.path,
            label: "project root",
            exactMode: nil
        )
        let expectedVerifier = projectRoot.appendingPathComponent(
            "security/verify_app_bundle.sh"
        )
        let verifier = try Self.canonicalExistingURL(
            payload[7],
            label: "application verifier"
        )
        guard verifier == expectedVerifier else {
            throw LauncherFailure.invalid(
                "application verifier is not the canonical project verifier"
            )
        }
        try Self.requireDigest(payload[5])
        try Self.requireDigest(payload[9])
        guard try Self.fileSHA256(dispatcher) == payload[5],
              try Self.fileSHA256(verifier) == payload[9] else {
            throw LauncherFailure.invalid(
                "dispatcher or verifier changed before command launch"
            )
        }
        var workingDirectoryBuffer = [CChar](
            repeating: 0,
            count: Int(PATH_MAX)
        )
        var projectRootStatus = stat()
        var workingDirectoryStatus = stat()
        guard projectRoot.path.withCString({
            lstat($0, &projectRootStatus)
        }) == 0,
              chdir(projectRoot.path) == 0,
              getcwd(
                &workingDirectoryBuffer,
                workingDirectoryBuffer.count
              ) != nil,
              lstat(".", &workingDirectoryStatus) == 0,
              workingDirectoryStatus.st_dev == projectRootStatus.st_dev,
              workingDirectoryStatus.st_ino == projectRootStatus.st_ino else {
            throw LauncherFailure.invalid(
                "command launcher working directory is not the project root"
            )
        }

        let groupFile = try Self.canonicalAbsentURL(
            payload[1],
            label: "process-group marker"
        )
        guard groupFile.lastPathComponent == "active-command-pgid" else {
            throw LauncherFailure.invalid(
                "process-group marker name is invalid"
            )
        }
        try Self.requireDirectory(
            groupFile.deletingLastPathComponent().path,
            label: "process-group control directory",
            exactMode: 0o700
        )
        let controlPrefix =
            groupFile.deletingLastPathComponent().path + "/"
        guard !controlPrefix.hasPrefix(projectRoot.path + "/") else {
            throw LauncherFailure.invalid(
                "process-group control directory entered the checkout"
            )
        }

        self.groupFile = groupFile
        self.dispatcher = dispatcher
        dispatcherSHA256 = payload[5]
        self.verifier = verifier
        verifierSHA256 = payload[9]
        self.projectRoot = projectRoot
        application = projectRoot.appendingPathComponent(
            "dist/CoreLMBenchmark.app"
        )
        self.action = action
    }

    func revalidateCommands() throws {
        guard try Self.fileSHA256(dispatcher) == dispatcherSHA256,
              try Self.fileSHA256(verifier) == verifierSHA256 else {
            throw LauncherFailure.invalid(
                "dispatcher or verifier changed at the spawn boundary"
            )
        }
    }

    private static func requireDigest(_ value: String) throws {
        guard value.count == 64,
              value.allSatisfy({ $0.isNumber || ("a"..."f").contains($0) }) else {
            throw LauncherFailure.invalid("command digest is malformed")
        }
    }

    private static func hexField(_ value: Substring) -> UInt32? {
        guard value.hasPrefix("0x"),
              value.count >= 3,
              value.count <= 10 else {
            return nil
        }
        return UInt32(value.dropFirst(2), radix: 16)
    }

    private static func canonicalExistingURL(
        _ path: String,
        label: String
    ) throws -> URL {
        guard path.hasPrefix("/"), !path.utf8.contains(0) else {
            throw LauncherFailure.invalid("\(label) is not absolute")
        }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        guard url.path == path,
              url.resolvingSymlinksInPath().standardizedFileURL == url else {
            throw LauncherFailure.invalid("\(label) is not canonical")
        }
        return url
    }

    private static func canonicalAbsentURL(
        _ path: String,
        label: String
    ) throws -> URL {
        guard path.hasPrefix("/"), !path.utf8.contains(0) else {
            throw LauncherFailure.invalid("\(label) is not absolute")
        }
        let url = URL(fileURLWithPath: path).standardizedFileURL
        let parent = url.deletingLastPathComponent()
        guard url.path == path,
              parent.resolvingSymlinksInPath().standardizedFileURL == parent,
              !FileManager.default.fileExists(atPath: url.path) else {
            throw LauncherFailure.invalid(
                "\(label) is not canonical and absent"
            )
        }
        return url
    }

    private static func requireDirectory(
        _ path: String,
        label: String,
        exactMode: mode_t?
    ) throws {
        let url = try canonicalExistingURL(path, label: label)
        var status = stat()
        guard path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFDIR,
              status.st_uid == getuid(),
              (status.st_mode & 0o022) == 0,
              exactMode == nil || (status.st_mode & 0o777) == exactMode,
              url.path == path else {
            throw LauncherFailure.invalid(
                "\(label) is not an owner-controlled directory"
            )
        }
    }

    private static func fileSHA256(_ url: URL) throws -> String {
        var status = stat()
        guard url.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG,
              status.st_uid == getuid(),
              (status.st_mode & 0o022) == 0,
              access(url.path, X_OK) == 0,
              status.st_size > 0,
              status.st_size <= 32 * 1024 * 1024 else {
            throw LauncherFailure.invalid(
                "command file is not an owner-controlled executable"
            )
        }
        let data = try Data(contentsOf: url, options: [.mappedIfSafe])
        guard data.count == status.st_size else {
            throw LauncherFailure.invalid("command file changed while read")
        }
        return SHA256.hash(data: data).map {
            String(format: "%02x", $0)
        }.joined()
    }
}

@main
private struct CoreLMOperatorCommandLauncher {
    static func main() {
        do {
            let environment = ProcessInfo.processInfo.environment
            let configuration = try LauncherConfiguration(
                arguments: CommandLine.arguments,
                environment: environment
            )
            let childEnvironment = Dictionary(
                uniqueKeysWithValues: [
                    "HOME", "TMPDIR", "PATH", "LANG", "LC_ALL"
                ].map { key in
                    (key, environment[key]!)
                }
            )
            let processID = getpid()
            let groupID: pid_t
            if getpgrp() == processID {
                // Foundation Process already places a spawned executable in a
                // dedicated group on this macOS runtime.  Calling setsid as a
                // group leader would fail with EPERM; the exact PGID property
                // needed by both supervisors is already established.
                groupID = processID
            } else {
                groupID = setsid()
            }
            guard groupID == processID, getpgid(0) == groupID else {
                throw LauncherFailure.invalid(
                    "command launcher could not create a dedicated process group"
                )
            }
            try publishMarker(configuration.groupFile, groupID: groupID)
            try configuration.revalidateCommands()

            if let arguments = configuration.action.dispatcherArguments {
                let commandStatus = try runChild(
                    executable: configuration.dispatcher,
                    arguments: arguments,
                    projectRoot: configuration.projectRoot,
                    environment: childEnvironment
                )
                if commandStatus != 0 {
                    exit(commandStatus)
                }
            }
            let status: Int32
            if configuration.action.requiresPostCommandAppVerification
                || configuration.action == .appCheck {
                // The primary command can be long-running.  Rebind both fixed
                // commands at the exact post-command verifier spawn boundary.
                try configuration.revalidateCommands()
                status = try runChild(
                    executable: configuration.verifier,
                    arguments: [configuration.application.path],
                    projectRoot: configuration.projectRoot,
                    environment: childEnvironment
                )
            } else {
                status = 0
            }
            exit(status)
        } catch {
            FileHandle.standardError.write(
                Data(
                    "CORE LM OPERATOR COMMAND FAIL: "
                        .appending(error.localizedDescription)
                        .appending("\n")
                        .utf8
                )
            )
            exit(127)
        }
    }

    private static func runChild(
        executable: URL,
        arguments: [String],
        projectRoot: URL,
        environment: [String: String]
    ) throws -> Int32 {
        guard chdir(projectRoot.path) == 0 else {
            throw LauncherFailure.invalid(
                "command launcher could not enter the project root"
            )
        }
        var argumentStorage = try cStringVector(
            [executable.path] + arguments
        )
        var environmentStorage = try cStringVector(
            environment.keys.sorted().compactMap { key in
                environment[key].map { "\(key)=\($0)" }
            }
        )
        defer {
            freeCStringVector(argumentStorage)
            freeCStringVector(environmentStorage)
        }
        var child: pid_t = 0
        let spawnStatus = argumentStorage.withUnsafeMutableBufferPointer {
            argumentBuffer in
            environmentStorage.withUnsafeMutableBufferPointer {
                environmentBuffer in
                posix_spawn(
                    &child,
                    argumentBuffer[0],
                    nil,
                    nil,
                    argumentBuffer.baseAddress!,
                    environmentBuffer.baseAddress!
                )
            }
        }
        guard spawnStatus == 0, child > 1 else {
            throw LauncherFailure.invalid(
                "command launcher could not spawn the fixed command"
            )
        }
        var childStatus: Int32 = 0
        while waitpid(child, &childStatus, 0) < 0 {
            if errno == EINTR {
                continue
            }
            throw LauncherFailure.invalid(
                "command launcher could not wait for the fixed command"
            )
        }
        let lowStatus = childStatus & 0x7F
        if lowStatus == 0 {
            return (childStatus >> 8) & 0xFF
        }
        return 128 + lowStatus
    }

    private static func cStringVector(
        _ values: [String]
    ) throws -> [UnsafeMutablePointer<CChar>?] {
        var result: [UnsafeMutablePointer<CChar>?] = []
        for value in values {
            guard let duplicate = strdup(value) else {
                freeCStringVector(result)
                throw LauncherFailure.invalid(
                    "command launcher could not allocate fixed process data"
                )
            }
            result.append(duplicate)
        }
        result.append(nil)
        return result
    }

    private static func freeCStringVector(
        _ values: [UnsafeMutablePointer<CChar>?]
    ) {
        for case let value? in values {
            free(value)
        }
    }

    private static func publishMarker(_ final: URL, groupID: pid_t) throws {
        let pending = final.deletingLastPathComponent().appendingPathComponent(
            ".active-command-pgid.\(groupID)"
        )
        let descriptor = open(
            pending.path,
            O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
            0o600
        )
        guard descriptor >= 0 else {
            throw LauncherFailure.invalid(
                "could not create the private process-group marker"
            )
        }
        var published = false
        var descriptorOpen = true
        defer {
            if descriptorOpen {
                _ = close(descriptor)
            }
            if !published {
                _ = unlink(pending.path)
            }
        }
        let marker = Array("\(groupID)\n".utf8)
        var offset = 0
        while offset < marker.count {
            let written = marker.withUnsafeBytes { bytes in
                write(
                    descriptor,
                    bytes.baseAddress!.advanced(by: offset),
                    marker.count - offset
                )
            }
            if written < 0, errno == EINTR {
                continue
            }
            guard written > 0 else {
                throw LauncherFailure.invalid(
                    "could not write the process-group marker"
                )
            }
            offset += written
        }
        guard fsync(descriptor) == 0,
              close(descriptor) == 0 else {
            throw LauncherFailure.invalid(
                "could not commit the process-group marker"
            )
        }
        descriptorOpen = false
        let renamed = pending.path.withCString { pendingPath in
            final.path.withCString { finalPath in
                renamex_np(pendingPath, finalPath, UInt32(RENAME_EXCL))
            }
        }
        guard renamed == 0 else {
            throw LauncherFailure.invalid(
                "could not atomically publish the process-group marker"
            )
        }
        published = true
    }
}
