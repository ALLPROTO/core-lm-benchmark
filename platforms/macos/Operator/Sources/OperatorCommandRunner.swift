import Darwin
import Foundation

enum OperatorOutputStream {
    case standardOutput
    case standardError
}

struct OperatorOutputSnapshot: Equatable {
    let runID: UUID
    let sequence: UInt64
    let text: String
}

struct OperatorCommandResult: Equatable {
    let runID: UUID
    let finalSequence: UInt64
    let exitStatus: Int32
    let output: String
    let terminalObservation: OperatorTerminalObservation
    let integrityError: String?
}

enum OperatorLogSanitizer {
    static func sanitize(
        _ message: String,
        home: String,
        hostname: String
    ) -> String {
        var sanitized = message.replacingOccurrences(of: "\u{0}", with: "")
        if !home.isEmpty {
            sanitized = sanitized.replacingOccurrences(of: home, with: "<home>")
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
        if hostname.count >= 3 {
            sanitized = sanitized.replacingOccurrences(
                of: hostname,
                with: "<host>"
            )
        }
        return sanitized
    }
}

final class SanitizedOutputBuffer: @unchecked Sendable {
    private let maximumCharacters: Int
    private let maximumLineCharacters: Int
    private let home: String
    private let hostname: String
    private let lock = NSLock()
    private var retained = ""
    private var pending = Data()
    private var droppingOversizedLine = false
    private var didTruncate = false

    init(
        maximumCharacters: Int = 64 * 1024,
        maximumLineCharacters: Int = 8 * 1024,
        home: String,
        hostname: String
    ) {
        precondition(maximumCharacters >= 256)
        precondition(maximumLineCharacters >= 64)
        self.maximumCharacters = maximumCharacters
        self.maximumLineCharacters = maximumLineCharacters
        self.home = home
        self.hostname = hostname
    }

    @discardableResult
    func append(_ data: Data) -> String {
        guard !data.isEmpty else { return snapshot() }
        lock.lock()
        defer { lock.unlock() }

        var incoming = data
        if droppingOversizedLine {
            guard let newline = incoming.firstIndex(of: 0x0A) else {
                return renderedLocked()
            }
            incoming.removeSubrange(...newline)
            droppingOversizedLine = false
        }
        pending.append(incoming)
        consumeCompleteLinesLocked()
        if pending.count > maximumLineCharacters {
            appendRetainedLocked("[oversized output line redacted]\n")
            pending.removeAll(keepingCapacity: true)
            droppingOversizedLine = true
        }
        return renderedLocked()
    }

    @discardableResult
    func finish() -> String {
        lock.lock()
        defer { lock.unlock() }
        if !droppingOversizedLine, !pending.isEmpty {
            appendSanitizedBytesLocked(pending)
        }
        pending.removeAll(keepingCapacity: true)
        droppingOversizedLine = false
        return renderedLocked()
    }

    func snapshot() -> String {
        lock.lock()
        defer { lock.unlock() }
        return renderedLocked()
    }

    private func consumeCompleteLinesLocked() {
        while let newline = pending.firstIndex(of: 0x0A) {
            let line = Data(pending[...newline])
            pending.removeSubrange(...newline)
            if line.count > maximumLineCharacters {
                appendRetainedLocked("[oversized output line redacted]\n")
            } else {
                appendSanitizedBytesLocked(line)
            }
        }
    }

    private func appendSanitizedBytesLocked(_ value: Data) {
        guard let decoded = String(data: value, encoding: .utf8) else {
            appendRetainedLocked("[malformed UTF-8 output line redacted]\n")
            return
        }
        appendRetainedLocked(
            OperatorLogSanitizer.sanitize(
                decoded,
                home: home,
                hostname: hostname
            )
        )
    }

    private func appendRetainedLocked(_ value: String) {
        retained.append(value)
        guard retained.count > maximumCharacters else { return }
        didTruncate = true
        retained = String(retained.suffix(maximumCharacters))
    }

    private func renderedLocked() -> String {
        didTruncate ? "[earlier output truncated]\n" + retained : retained
    }
}

private final class OperatorCombinedOutput: @unchecked Sendable {
    private let standardOutput: SanitizedOutputBuffer
    private let standardError: SanitizedOutputBuffer

    init(home: String, hostname: String) {
        standardOutput = SanitizedOutputBuffer(
            home: home,
            hostname: hostname
        )
        standardError = SanitizedOutputBuffer(
            home: home,
            hostname: hostname
        )
    }

    func append(_ data: Data, stream: OperatorOutputStream) {
        switch stream {
        case .standardOutput:
            standardOutput.append(data)
        case .standardError:
            standardError.append(data)
        }
    }

    func finish(_ stream: OperatorOutputStream) {
        switch stream {
        case .standardOutput:
            standardOutput.finish()
        case .standardError:
            standardError.finish()
        }
    }

    func rendered() -> String {
        let stdout = standardOutput.snapshot()
        let stderr = standardError.snapshot()
        var sections: [String] = []
        if !stdout.isEmpty {
            sections.append("[stdout]\n" + stdout)
        }
        if !stderr.isEmpty {
            sections.append("[stderr]\n" + stderr)
        }
        return sections.joined(separator: "\n")
    }
}

final class OperatorProofTerminalObserver: @unchecked Sendable {
    static let passLine =
        "END-TO-END PROOF PASS: the locally built app ran pinned Qwen on MPS,"
    static let metricFailLine =
        "END-TO-END PROOF VERIFIED — METRIC FAIL: "
        + "the locally built app ran pinned Qwen on MPS,"

    private let maximumPendingBytes = 64 * 1024
    private let lock = NSLock()
    private var stdoutPending = Data()
    private var stderrPending = Data()
    private var stdoutDroppingOversizedLine = false
    private var stderrDroppingOversizedLine = false
    private var state: OperatorProofTerminalState = .none

    func consume(_ data: Data, stream: OperatorOutputStream) {
        guard !data.isEmpty else { return }
        lock.lock()
        defer { lock.unlock() }
        switch stream {
        case .standardOutput:
            consumeLocked(
                data,
                pending: &stdoutPending,
                droppingOversizedLine: &stdoutDroppingOversizedLine,
                stdout: true
            )
        case .standardError:
            consumeLocked(
                data,
                pending: &stderrPending,
                droppingOversizedLine: &stderrDroppingOversizedLine,
                stdout: false
            )
        }
    }

    func finish(_ stream: OperatorOutputStream) {
        lock.lock()
        defer { lock.unlock() }
        switch stream {
        case .standardOutput:
            finishLocked(
                pending: &stdoutPending,
                droppingOversizedLine: &stdoutDroppingOversizedLine,
                stdout: true
            )
        case .standardError:
            finishLocked(
                pending: &stderrPending,
                droppingOversizedLine: &stderrDroppingOversizedLine,
                stdout: false
            )
        }
    }

    func observation() -> OperatorTerminalObservation {
        lock.lock()
        defer { lock.unlock() }
        return OperatorTerminalObservation(proof: state)
    }

    private func consumeLocked(
        _ data: Data,
        pending: inout Data,
        droppingOversizedLine: inout Bool,
        stdout: Bool
    ) {
        var incoming = data
        if droppingOversizedLine {
            guard let newline = incoming.firstIndex(of: 0x0A) else {
                return
            }
            incoming.removeSubrange(...newline)
            droppingOversizedLine = false
        }
        pending.append(incoming)
        while let newline = pending.firstIndex(of: 0x0A) {
            let line = Data(pending[..<newline])
            pending.removeSubrange(...newline)
            observeLocked(line, stdout: stdout, terminated: true)
        }
        if pending.count > maximumPendingBytes {
            state = .ambiguous
            pending.removeAll(keepingCapacity: true)
            droppingOversizedLine = true
        }
    }

    private func finishLocked(
        pending: inout Data,
        droppingOversizedLine: inout Bool,
        stdout: Bool
    ) {
        if droppingOversizedLine {
            droppingOversizedLine = false
            pending.removeAll(keepingCapacity: true)
            return
        }
        guard !pending.isEmpty else { return }
        observeLocked(pending, stdout: stdout, terminated: false)
        pending.removeAll(keepingCapacity: false)
    }

    private func observeLocked(
        _ bytes: Data,
        stdout: Bool,
        terminated: Bool
    ) {
        guard let line = String(data: bytes, encoding: .utf8) else {
            if containsReservedMarker(bytes) {
                state = .ambiguous
            }
            return
        }
        let candidate: OperatorProofTerminalState?
        if line == Self.passLine {
            candidate = .proofPass
        } else if line == Self.metricFailLine {
            candidate = .metricFail
        } else {
            candidate = nil
        }
        if let candidate {
            guard stdout, terminated, state == .none else {
                state = .ambiguous
                return
            }
            state = candidate
        } else if containsReservedMarker(bytes) {
            state = .ambiguous
        }
    }

    private func containsReservedMarker(_ bytes: Data) -> Bool {
        let prefix = Data("END-TO-END PROOF".utf8)
        return bytes.range(of: prefix) != nil
    }
}

final class OperatorCommandHandle: @unchecked Sendable {
    let runID: UUID
    private let groupController: OperatorProcessGroupController

    init(
        runID: UUID,
        groupController: OperatorProcessGroupController
    ) {
        self.runID = runID
        self.groupController = groupController
    }

    func cancel() {
        groupController.requestTermination()
    }
}

final class OperatorProcessGroupController: @unchecked Sendable {
    private let groupID: pid_t
    private let queue: DispatchQueue
    private let lock = NSLock()
    private let completed = DispatchGroup()
    private var started = false

    init(groupID: pid_t, label: String) {
        self.groupID = groupID
        queue = DispatchQueue(label: label, qos: .userInitiated)
        completed.enter()
    }

    func requestTermination() {
        lock.lock()
        guard !started else {
            lock.unlock()
            return
        }
        started = true
        lock.unlock()
        queue.async {
            OperatorProcessGroup.terminate(self.groupID)
            self.completed.leave()
        }
    }

    func terminateAndWait() {
        requestTermination()
        completed.wait()
    }
}

enum OperatorProcessGroup {
    static func terminate(_ groupID: pid_t) {
        guard isSafe(groupID) else { return }
        if kill(-groupID, SIGTERM) != 0, errno == ESRCH {
            return
        }
        // run-proof's EXIT trap needs up to four seconds to terminate its own
        // separately supervised worker groups.  Six seconds preserves that
        // cleanup window before this outer contour escalates.
        for _ in 0..<60 {
            if kill(-groupID, 0) != 0, errno == ESRCH {
                return
            }
            usleep(100_000)
        }
        _ = kill(-groupID, SIGKILL)
    }

    static func isSafe(_ groupID: pid_t) -> Bool {
        groupID > 1 && groupID != getpgrp()
    }
}

final class OperatorCommandRunner {
    typealias OutputHandler = (OperatorOutputSnapshot) -> Void
    typealias CompletionHandler = (OperatorCommandResult) -> Void

    private let sourceEnvironment: [String: String]
    private let hostname: String

    init(
        sourceEnvironment: [String: String] = ProcessInfo.processInfo.environment,
        hostname: String = ProcessInfo.processInfo.hostName
    ) {
        self.sourceEnvironment = sourceEnvironment
        self.hostname = hostname
    }

    @discardableResult
    func run(
        action: OperatorAction,
        configuration: OperatorLaunchConfiguration,
        onOutput: @escaping OutputHandler,
        completion: @escaping CompletionHandler
    ) throws -> OperatorCommandHandle {
        let project = configuration.project
        let authority = configuration.commandAuthority
        try project.revalidateControlSurface()
        try authority.prepareForSpawn()
        let environment = try Self.sterileEnvironment(from: sourceEnvironment)
        let output = OperatorCombinedOutput(
            home: environment["HOME"] ?? "",
            hostname: hostname
        )
        let terminalObserver = OperatorProofTerminalObserver()
        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.executableURL = authority.launcher
        process.currentDirectoryURL = project.root
        process.arguments = [
            "--group-file", authority.groupFile.path,
            "--dispatcher", project.dispatcher.path,
            "--dispatcher-sha256", project.dispatcherSHA256,
            "--verifier", project.verifier.path,
            "--verifier-sha256", project.verifierSHA256,
            "--action", action.launcherToken
        ]
        process.environment = environment
        process.qualityOfService = .utility
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let processExited = DispatchGroup()
        processExited.enter()
        process.terminationHandler = { _ in
            processExited.leave()
        }

        // This is the final integrity check before the only process spawn.
        try project.revalidateControlSurface()
        try authority.prepareForSpawn()
        do {
            try process.run()
        } catch {
            try? stdoutPipe.fileHandleForWriting.close()
            try? stderrPipe.fileHandleForWriting.close()
            throw error
        }
        try? stdoutPipe.fileHandleForWriting.close()
        try? stderrPipe.fileHandleForWriting.close()

        let groupID: pid_t
        do {
            groupID = try Self.captureProcessGroup(
                process: process,
                authority: authority
            )
        } catch {
            let markerError = error.localizedDescription
            let pid = process.processIdentifier
            if OperatorProcessGroup.isSafe(pid), getpgid(pid) == pid {
                OperatorProcessGroup.terminate(pid)
            } else if process.isRunning {
                process.terminate()
            }
            process.waitUntilExit()
            let startupErrorData = try? stderrPipe.fileHandleForReading.read(
                upToCount: 8 * 1024
            )
            let startupError = startupErrorData.flatMap {
                String(data: $0, encoding: .utf8)
            }.map {
                OperatorLogSanitizer.sanitize(
                    $0,
                    home: environment["HOME"] ?? "",
                    hostname: hostname
                ).trimmingCharacters(in: .whitespacesAndNewlines)
            } ?? ""
            try? stdoutPipe.fileHandleForReading.close()
            try? stderrPipe.fileHandleForReading.close()
            let detail = startupError.isEmpty
                ? markerError
                : markerError + " " + startupError
            throw OperatorValidationError.invalid(detail)
        }

        let runID = UUID()
        let deliveryQueue = DispatchQueue(
            label: "com.corelm.operator.output.\(runID.uuidString)"
        )
        let cleanupQueue = DispatchQueue(
            label: "com.corelm.operator.cleanup.\(runID.uuidString)",
            qos: .utility
        )
        let groupController = OperatorProcessGroupController(
            groupID: groupID,
            label: "com.corelm.operator.cancel.\(runID.uuidString)"
        )
        let drains = DispatchGroup()
        let sequenceLock = NSLock()
        var sequence: UInt64 = 0

        let publish: () -> Void = {
            deliveryQueue.sync {
                sequenceLock.lock()
                sequence += 1
                let current = sequence
                sequenceLock.unlock()
                onOutput(
                    OperatorOutputSnapshot(
                        runID: runID,
                        sequence: current,
                        text: output.rendered()
                    )
                )
            }
        }
        func startDrain(_ handle: FileHandle, stream: OperatorOutputStream) {
            drains.enter()
            DispatchQueue.global(qos: .utility).async {
                defer {
                    terminalObserver.finish(stream)
                    output.finish(stream)
                    publish()
                    try? handle.close()
                    drains.leave()
                }
                do {
                    while let data = try handle.read(upToCount: 16 * 1024),
                          !data.isEmpty {
                        terminalObserver.consume(data, stream: stream)
                        output.append(data, stream: stream)
                        publish()
                    }
                } catch {
                    output.append(
                        Data("[operator output drain failed]\n".utf8),
                        stream: stream
                    )
                }
            }
        }
        startDrain(
            stdoutPipe.fileHandleForReading,
            stream: .standardOutput
        )
        startDrain(
            stderrPipe.fileHandleForReading,
            stream: .standardError
        )

        cleanupQueue.async {
            processExited.wait()
            groupController.terminateAndWait()
            drains.wait()

            var integrityErrors: [String] = []
            do {
                try project.revalidateControlSurface()
            } catch {
                integrityErrors.append(error.localizedDescription)
            }
            do {
                try authority.revalidateLauncher()
            } catch {
                integrityErrors.append(error.localizedDescription)
            }
            do {
                try Self.removeGroupMarker(
                    authority: authority,
                    expectedGroupID: groupID
                )
            } catch {
                integrityErrors.append(error.localizedDescription)
            }

            deliveryQueue.async {
                sequenceLock.lock()
                let finalSequence = sequence
                sequenceLock.unlock()
                let status: Int32
                if process.terminationReason == .exit {
                    status = process.terminationStatus
                } else {
                    status = 128 + process.terminationStatus
                }
                completion(
                    OperatorCommandResult(
                        runID: runID,
                        finalSequence: finalSequence,
                        exitStatus: status,
                        output: output.rendered(),
                        terminalObservation: terminalObserver.observation(),
                        integrityError: integrityErrors.isEmpty
                            ? nil
                            : integrityErrors.joined(separator: " ")
                    )
                )
            }
        }
        return OperatorCommandHandle(
            runID: runID,
            groupController: groupController
        )
    }

    static func sterileEnvironment(
        from source: [String: String]
    ) throws -> [String: String] {
        guard let home = source["HOME"],
              let temporary = source["TMPDIR"] else {
            throw OperatorValidationError.invalid(
                "Operator launcher did not provide HOME and TMPDIR."
            )
        }
        try OperatorSecurePath.requireDirectory(
            try OperatorSecurePath.canonicalExistingURL(
                home,
                label: "operator HOME"
            ),
            label: "operator HOME"
        )
        try OperatorSecurePath.requireDirectory(
            try OperatorSecurePath.canonicalExistingURL(
                temporary,
                label: "operator TMPDIR"
            ),
            label: "operator TMPDIR",
            exactMode: 0o700
        )
        return [
            "HOME": home,
            "TMPDIR": temporary,
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C"
        ]
    }

    private static func captureProcessGroup(
        process: Process,
        authority: OperatorCommandAuthority
    ) throws -> pid_t {
        for _ in 0..<200 {
            if FileManager.default.fileExists(atPath: authority.groupFile.path) {
                break
            }
            if !process.isRunning {
                break
            }
            usleep(10_000)
        }
        var status = stat()
        guard authority.groupFile.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG,
              status.st_uid == getuid(),
              (status.st_mode & 0o777) == 0o600,
              status.st_size > 1,
              status.st_size <= 16 else {
            throw OperatorValidationError.invalid(
                "Operator command did not publish a valid process-group marker."
            )
        }
        let bytes = try Data(contentsOf: authority.groupFile)
        guard let text = String(data: bytes, encoding: .ascii),
              text.last == "\n",
              text.dropLast().allSatisfy({ $0.isNumber }),
              let value = Int32(text.dropLast()),
              value == process.processIdentifier,
              OperatorProcessGroup.isSafe(value) else {
            throw OperatorValidationError.invalid(
                "Operator process-group marker content is invalid."
            )
        }
        if process.isRunning, getpgid(value) != value {
            throw OperatorValidationError.invalid(
                "Operator command launcher did not own its process group."
            )
        }
        return value
    }

    private static func removeGroupMarker(
        authority: OperatorCommandAuthority,
        expectedGroupID: pid_t
    ) throws {
        var status = stat()
        guard authority.groupFile.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG,
              status.st_uid == getuid(),
              (status.st_mode & 0o777) == 0o600 else {
            throw OperatorValidationError.invalid(
                "Operator process-group marker changed before cleanup."
            )
        }
        let expected = Data("\(expectedGroupID)\n".utf8)
        guard try Data(contentsOf: authority.groupFile) == expected,
              unlink(authority.groupFile.path) == 0 else {
            throw OperatorValidationError.invalid(
                "Operator process-group marker cleanup failed."
            )
        }
    }
}
