import Darwin
import Foundation
import Testing
@testable import CoreLMOperator

private final class OperatorTestBundleMarker: NSObject {}

private func parseOperatorTestProcessID(_ bytes: Data) -> pid_t? {
    guard bytes.count >= 2, bytes.count <= 12, bytes.last == 0x0A else {
        return nil
    }
    let digits = bytes.dropLast()
    guard
        let first = digits.first,
        (0x31...0x39).contains(first),
        digits.dropFirst().allSatisfy({ (0x30...0x39).contains($0) }),
        let text = String(data: Data(digits), encoding: .ascii),
        let processID = Int32(text),
        processID > 1
    else {
        return nil
    }
    return processID
}

// The integration cases below exercise real process groups and inherited
// stdout/stderr file descriptors. Keep suites serial so separate fixtures do
// not compete for CI process scheduling while preserving concurrency inside
// each individual stress test.
@Suite(.serialized)
struct OperatorTests {
    private static let canonicalModelInventory =
        "{\"acceptedAsBenchmarkEvidence\":false,\"action\":\"list\","
        + "\"adapters\":[{},{},{},{},{},{},{}],"
        + "\"classification\":\"MODEL_METADATA_ADMISSION_NOT_BENCHMARK_EVIDENCE\","
        + "\"countsTowardScientificVerdict\":false,"
        + "\"limitations\":[\"a\",\"b\",\"c\",\"d\"],"
        + "\"modelExecuted\":false,\"profiles\":[{}],"
        + "\"registrySHA256\":\"05b1900a44462902a1a823a7e4213043cca3613a63c53f042ededa72dcbb9680\","
        + "\"schemaVersion\":\"corelm-model-compatibility-inspection-v1\"}\n"

    private final class LockedRunCapture: @unchecked Sendable {
        private let lock = NSLock()
        private var retainedSnapshots: [OperatorOutputSnapshot] = []
        private var retainedResult: OperatorCommandResult?

        func append(_ snapshot: OperatorOutputSnapshot) {
            lock.lock()
            retainedSnapshots.append(snapshot)
            lock.unlock()
        }

        func finish(_ result: OperatorCommandResult) {
            lock.lock()
            retainedResult = result
            lock.unlock()
        }

        func value() -> (
            snapshots: [OperatorOutputSnapshot],
            result: OperatorCommandResult?
        ) {
            lock.lock()
            defer { lock.unlock() }
            return (retainedSnapshots, retainedResult)
        }
    }

    private final class TestProcessCleanupGuard {
        private var groups: Set<pid_t> = []
        private var processes: Set<pid_t> = []
        private var groupFiles: Set<URL> = []
        private var processFiles: Set<URL> = []

        func recordGroup(_ groupID: pid_t) {
            if OperatorProcessGroup.isSafe(groupID) {
                groups.insert(groupID)
            }
        }

        func recordProcess(_ processID: pid_t) {
            if processID > 1 {
                processes.insert(processID)
            }
        }

        func recordGroupFile(_ url: URL) {
            groupFiles.insert(url)
        }

        func recordProcessFile(_ url: URL) {
            processFiles.insert(url)
        }

        private func processID(from url: URL) -> pid_t? {
            guard
                let bytes = try? Data(contentsOf: url),
                let processID = parseOperatorTestProcessID(bytes)
            else {
                return nil
            }
            return processID
        }

        private func discoverRecordedProcesses() {
            for url in groupFiles {
                if let processID = processID(from: url),
                   OperatorProcessGroup.isSafe(processID) {
                    groups.insert(processID)
                }
            }
            for url in processFiles {
                if let processID = processID(from: url) {
                    processes.insert(processID)
                }
            }
        }

        func clean() {
            guard
                !groups.isEmpty || !processes.isEmpty
                    || !groupFiles.isEmpty || !processFiles.isEmpty
            else {
                return
            }
            for _ in 0..<20 {
                discoverRecordedProcesses()
                for groupID in groups {
                    _ = kill(-groupID, SIGKILL)
                }
                for processID in processes {
                    _ = kill(processID, SIGKILL)
                }
                let groupAlive = groups.contains {
                    kill(-$0, 0) == 0 || errno != ESRCH
                }
                let processAlive = processes.contains {
                    kill($0, 0) == 0 || errno != ESRCH
                }
                if !groupAlive, !processAlive {
                    return
                }
                usleep(100_000)
            }
        }

        func disarm() {
            groups.removeAll()
            processes.removeAll()
            groupFiles.removeAll()
            processFiles.removeAll()
        }
    }

    private struct Fixture {
        let root: URL
        let control: URL
        let project: OperatorProject
        let configuration: OperatorLaunchConfiguration

        func remove() {
            try? FileManager.default.removeItem(at: root)
            try? FileManager.default.removeItem(at: control)
        }
    }

    private func expectFailure(_ operation: () throws -> Void) {
        do {
            try operation()
            Issue.record("Expected operation to fail closed.")
        } catch {
            // Expected.
        }
    }

    private func makeFixture(
        dispatcher: String = "#!/bin/sh\nexit 0\n",
        commandLauncher: URL? = nil
    ) throws -> Fixture {
        let base = FileManager.default.temporaryDirectory
            .resolvingSymlinksInPath()
            .standardizedFileURL
        let identifier = UUID().uuidString
        let root = base.appendingPathComponent(
            "corelm-operator-tests-\(identifier)",
            isDirectory: true
        )
        let control = base.appendingPathComponent(
            "corelm-operator-control-\(identifier)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        try FileManager.default.createDirectory(
            at: control,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        for relative in OperatorProject.controlFilePaths {
            let file = root.appendingPathComponent(relative)
            try FileManager.default.createDirectory(
                at: file.deletingLastPathComponent(),
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
            let contents: String
            if relative == "corelm" {
                contents = dispatcher
            } else if relative.hasSuffix(".sh") {
                contents = "#!/bin/sh\nexit 0\n"
            } else if relative.hasSuffix(".py") {
                contents = "# fixture\n"
            } else {
                contents = "// fixture\n"
            }
            if !FileManager.default.fileExists(atPath: file.path) {
                try Data(contents.utf8).write(
                    to: file,
                    options: .withoutOverwriting
                )
            }
            let executable = relative == "corelm" || relative.hasSuffix(".sh")
            try FileManager.default.setAttributes(
                [.posixPermissions: executable ? 0o700 : 0o600],
                ofItemAtPath: file.path
            )
        }
        let launcher: URL
        if let commandLauncher {
            launcher = commandLauncher
        } else {
            launcher = control.appendingPathComponent("fixture-launcher")
            try Data("#!/bin/sh\nexit 0\n".utf8).write(
                to: launcher,
                options: .withoutOverwriting
            )
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o700],
                ofItemAtPath: launcher.path
            )
        }
        let groupFile = control.appendingPathComponent("active-command-pgid")
        let project = try OperatorProject(rootPath: root.path)
        let configuration = try OperatorLaunchConfiguration(
            arguments: [
                "CoreLMOperator",
                "--project-root", root.path,
                "--command-launcher", launcher.path,
                "--group-file", groupFile.path
            ]
        )
        return Fixture(
            root: root,
            control: control,
            project: project,
            configuration: configuration
        )
    }

    private func createApplication(in fixture: Fixture) throws -> URL {
        let app = fixture.root.appendingPathComponent(
            "dist/CoreLMBenchmark.app", isDirectory: true
        )
        let macOS = app.appendingPathComponent(
            "Contents/MacOS", isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: macOS,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let executable = macOS.appendingPathComponent("CoreLMBenchmarkApp")
        try Data("fixture".utf8).write(
            to: executable,
            options: .withoutOverwriting
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: executable.path
        )
        let info = app.appendingPathComponent("Contents/Info.plist")
        try Data("fixture".utf8).write(
            to: info,
            options: .withoutOverwriting
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: info.path
        )
        return app
    }

    private func builtCommandLauncher() throws -> URL {
        var executableBuffer = [CChar](
            repeating: 0,
            count: Int(PATH_MAX)
        )
        var executableBufferSize = UInt32(executableBuffer.count)
        guard _NSGetExecutablePath(
            &executableBuffer,
            &executableBufferSize
        ) == 0 else {
            throw OperatorValidationError.invalid(
                "Could not resolve the Swift test executable."
            )
        }
        let startingURLs = [
            URL(fileURLWithPath: String(cString: executableBuffer)),
            Bundle.main.bundleURL,
            Bundle(for: OperatorTestBundleMarker.self).bundleURL
        ]
        for startingURL in startingURLs {
            var directory = startingURL.standardizedFileURL
            if !directory.hasDirectoryPath {
                directory.deleteLastPathComponent()
            }
            for _ in 0..<10 {
                let candidate = directory.appendingPathComponent(
                    "CoreLMOperatorCommandLauncher"
                )
                if FileManager.default.isExecutableFile(
                    atPath: candidate.path
                ) {
                    return candidate
                }
                let parent = directory.deletingLastPathComponent()
                if parent == directory {
                    break
                }
                directory = parent
            }
        }
        throw OperatorValidationError.invalid(
            "SwiftPM did not build CoreLMOperatorCommandLauncher for integration tests."
        )
    }

    private func runtimeEnvironment(
        fixture: Fixture
    ) throws -> [String: String] {
        let home = fixture.control.appendingPathComponent("home")
        let temporary = fixture.control.appendingPathComponent("tmp")
        for directory in [home, temporary] {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700]
            )
        }
        return ["HOME": home.path, "TMPDIR": temporary.path]
    }

    private func waitForProcessID(
        in url: URL,
        group: Bool = false,
        seconds: Double
    ) -> Int32? {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            var status = stat()
            if url.path.withCString({ lstat($0, &status) }) == 0,
               (status.st_mode & S_IFMT) == S_IFREG,
               status.st_nlink == 1,
               let bytes = try? Data(contentsOf: url),
               let processID = parseOperatorTestProcessID(bytes),
               group ? OperatorProcessGroup.isSafe(processID) : true,
               kill(group ? -processID : processID, 0) == 0 {
                return processID
            }
            usleep(10_000)
        }
        return nil
    }

    @Test
    func actionsHaveOnlyFixedCommandMappings() {
        #expect(
            OperatorAction.allCases == [
                .verifyRepository,
                .modelCompatibility,
                .buildApp,
                .fullSystemProof,
                .openBuiltApplication
            ]
        )
        #expect(OperatorAction.verifyRepository.coreLMArguments == ["verify"])
        #expect(
            OperatorAction.modelCompatibility.coreLMArguments
                == ["models", "list"]
        )
        #expect(OperatorAction.modelCompatibility.launcherToken == "models")
        #expect(OperatorAction.buildApp.coreLMArguments == ["macos", "build"])
        #expect(
            OperatorAction.fullSystemProof.coreLMArguments
                == ["macos", "proof"]
        )
        #expect(OperatorAction.openBuiltApplication.coreLMArguments == nil)
        #expect(OperatorAction.openBuiltApplication.launcherToken == "app-check")
    }

    @Test
    func launchConfigurationAcceptsOnlyExactLauncherAuthority() throws {
        let fixture = try makeFixture()
        defer { fixture.remove() }
        #expect(fixture.configuration.project == fixture.project)
        for arguments in [
            ["CoreLMOperator"],
            ["CoreLMOperator", "--project-root", fixture.root.path],
            [
                "CoreLMOperator",
                "--command-launcher",
                fixture.configuration.commandAuthority.launcher.path,
                "--project-root",
                fixture.root.path,
                "--group-file",
                fixture.configuration.commandAuthority.groupFile.path
            ],
            [
                "CoreLMOperator",
                "--project-root", fixture.root.path,
                "--command-launcher",
                fixture.configuration.commandAuthority.launcher.path,
                "--group-file",
                fixture.configuration.commandAuthority.groupFile.path,
                "extra"
            ]
        ] {
            expectFailure {
                _ = try OperatorLaunchConfiguration(arguments: arguments)
            }
        }

        try Data("#!/bin/sh\nexit 9\n".utf8).write(
            to: fixture.configuration.commandAuthority.launcher,
            options: .atomic
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: fixture.configuration.commandAuthority.launcher.path
        )
        expectFailure {
            try fixture.configuration.commandAuthority.prepareForSpawn()
        }
    }

    @Test
    func projectRejectsSymlinkAndTransitiveControlDrift() throws {
        let fixture = try makeFixture()
        defer { fixture.remove() }
        let link = fixture.root.deletingLastPathComponent().appendingPathComponent(
            "corelm-operator-link-\(UUID().uuidString)"
        )
        try FileManager.default.createSymbolicLink(
            at: link,
            withDestinationURL: fixture.root
        )
        defer { try? FileManager.default.removeItem(at: link) }
        expectFailure {
            _ = try OperatorProject(rootPath: link.path)
        }

        let transitive = fixture.root.appendingPathComponent(
            "security/verify_git_checkout.py"
        )
        try Data("# changed\n".utf8).write(to: transitive, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: transitive.path
        )
        expectFailure {
            try fixture.project.revalidateControlSurface()
        }
    }

    @Test
    func builtApplicationRequiresExactRegularCanonicalTopology() throws {
        let fixture = try makeFixture()
        defer { fixture.remove() }
        expectFailure {
            _ = try fixture.project.validatedBuiltApplication()
        }
        let app = try createApplication(in: fixture)
        #expect(try fixture.project.validatedBuiltApplication() == app)
        let executable = app.appendingPathComponent(
            "Contents/MacOS/CoreLMBenchmarkApp"
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o722],
            ofItemAtPath: executable.path
        )
        expectFailure {
            _ = try fixture.project.validatedBuiltApplication()
        }
    }

    @Test
    func sanitizerRedactsPrivatePathsHostAndCredentials() {
        let privateHome = "/" + "Users" + "/private"
        let credentialPrefix = "gh" + "p_"
        let syntheticCredential = credentialPrefix
            + String(repeating: "a", count: 30)
        let message = privateHome + "/repo on operator-host "
            + syntheticCredential
        let sanitized = OperatorLogSanitizer.sanitize(
            message,
            home: privateHome,
            hostname: "operator-host"
        )
        #expect(!sanitized.contains(privateHome))
        #expect(!sanitized.contains("operator-host"))
        #expect(!sanitized.contains(credentialPrefix))
        #expect(sanitized.contains("<home>"))
        #expect(sanitized.contains("<host>"))
        #expect(sanitized.contains("[REDACTED_CREDENTIAL]"))
    }

    @Test
    func outputBufferPreservesSplitUTF8AndIsBounded() {
        let privateHome = "/" + "Users" + "/private"
        let splitValue = Data("before — after\n".utf8)
        let dash = Array(splitValue).firstIndex(of: 0xE2)!
        let buffer = SanitizedOutputBuffer(
            maximumCharacters: 256,
            maximumLineCharacters: 64,
            home: privateHome,
            hostname: "operator-host"
        )
        buffer.append(Data(splitValue[..<(dash + 1)]))
        buffer.append(Data(splitValue[(dash + 1)...]))
        #expect(buffer.snapshot().contains("before — after"))
        buffer.append(Data([0xFF, 0x0A]))
        #expect(buffer.snapshot().contains("malformed UTF-8 output line redacted"))
        buffer.append(Data((String(repeating: "x", count: 128) + "\n").utf8))
        #expect(buffer.snapshot().contains("oversized output line redacted"))
        for index in 0..<100 {
            buffer.append(Data("retained-line-\(index)\n".utf8))
        }
        let result = buffer.finish()
        #expect(result.hasPrefix("[earlier output truncated]\n"))
        #expect(result.contains("retained-line-99"))
        #expect(result.count <= 300)
    }

    @Test
    func proofTerminalObservationRequiresOneExactLFStdoutLine() {
        let pass = Data((OperatorProofTerminalObserver.passLine + "\n").utf8)
        for split in 0...pass.count {
            let observer = OperatorProofTerminalObserver()
            observer.consume(Data(pass[..<split]), stream: .standardOutput)
            observer.consume(Data(pass[split...]), stream: .standardOutput)
            observer.finish(.standardOutput)
            #expect(observer.observation().proof == .proofPass)
        }

        let metric = OperatorProofTerminalObserver.metricFailLine
        let acceptedMetric = OperatorProofTerminalObserver()
        acceptedMetric.consume(
            Data((metric + "\n").utf8),
            stream: .standardOutput
        )
        #expect(acceptedMetric.observation().proof == .metricFail)

        let invalidCases: [(String, OperatorOutputStream, Bool)] = [
            (OperatorProofTerminalObserver.passLine, .standardOutput, false),
            (OperatorProofTerminalObserver.passLine + "\r\n", .standardOutput, true),
            ("prefix " + OperatorProofTerminalObserver.passLine + "\n", .standardOutput, true),
            (OperatorProofTerminalObserver.passLine + " suffix\n", .standardOutput, true),
            (OperatorProofTerminalObserver.passLine + "\n", .standardError, true)
        ]
        for (value, stream, finish) in invalidCases {
            let observer = OperatorProofTerminalObserver()
            observer.consume(Data(value.utf8), stream: stream)
            if finish {
                observer.finish(stream)
            } else {
                observer.finish(.standardOutput)
            }
            #expect(observer.observation().proof != .proofPass)
            #expect(observer.observation().proof != .metricFail)
        }

        for lines in [
            [OperatorProofTerminalObserver.passLine,
             OperatorProofTerminalObserver.passLine],
            [OperatorProofTerminalObserver.passLine,
             OperatorProofTerminalObserver.metricFailLine]
        ] {
            let observer = OperatorProofTerminalObserver()
            observer.consume(
                Data((lines.joined(separator: "\n") + "\n").utf8),
                stream: .standardOutput
            )
            #expect(observer.observation().proof == .ambiguous)
        }

        var malformedReserved = Data("END-TO-END PROOF PASS:".utf8)
        malformedReserved.append(0xFF)
        malformedReserved.append(0x0A)
        for stream in [
            OperatorOutputStream.standardOutput,
            OperatorOutputStream.standardError
        ] {
            let observer = OperatorProofTerminalObserver()
            observer.consume(malformedReserved, stream: stream)
            #expect(observer.observation().proof == .ambiguous)
        }
        let duplicate = OperatorProofTerminalObserver()
        duplicate.consume(pass, stream: .standardOutput)
        duplicate.consume(malformedReserved, stream: .standardError)
        #expect(duplicate.observation().proof == .ambiguous)

        for stream in [
            OperatorOutputStream.standardOutput,
            OperatorOutputStream.standardError
        ] {
            let combined = OperatorProofTerminalObserver()
            combined.consume(pass, stream: .standardOutput)
            let midline = Data(
                ("noise " + OperatorProofTerminalObserver.passLine + "\n").utf8
            )
            let split = midline.count / 2
            combined.consume(Data(midline[..<split]), stream: stream)
            combined.consume(Data(midline[split...]), stream: stream)
            #expect(combined.observation().proof == .ambiguous)

            let malformedCombined = OperatorProofTerminalObserver()
            malformedCombined.consume(pass, stream: .standardOutput)
            malformedCombined.consume(malformedReserved, stream: stream)
            #expect(malformedCombined.observation().proof == .ambiguous)
        }

        let oversizedPrefix = Data(repeating: 0x78, count: 65 * 1024)
        for stream in [
            OperatorOutputStream.standardOutput,
            OperatorOutputStream.standardError
        ] {
            let observer = OperatorProofTerminalObserver()
            observer.consume(oversizedPrefix, stream: stream)
            observer.consume(pass, stream: stream)
            #expect(observer.observation().proof == .ambiguous)
            observer.consume(pass, stream: .standardOutput)
            #expect(observer.observation().proof == .ambiguous)
        }
    }

    @Test
    func terminalClassifierUsesTypedStateAndCanonicalApp() throws {
        #expect(
            try OperatorTerminalClassifier.outcome(
                action: .verifyRepository,
                exitStatus: 0,
                observation: OperatorTerminalObservation(proof: .none),
                builtApplicationAvailable: false
            ) == .repositoryVerified
        )
        #expect(
            try OperatorTerminalClassifier.outcome(
                action: .modelCompatibility,
                exitStatus: 0,
                observation: OperatorTerminalObservation(proof: .none),
                modelInventoryOutput: Self.canonicalModelInventory,
                builtApplicationAvailable: false
            ) == .modelInventoryListed
        )
        #expect(throws: OperatorValidationError.self) {
            _ = try OperatorTerminalClassifier.outcome(
                action: .modelCompatibility,
                exitStatus: 0,
                observation: OperatorTerminalObservation(proof: .none),
                modelInventoryOutput: Self.canonicalModelInventory.replacingOccurrences(
                    of: "\"modelExecuted\":false",
                    with: "\"modelExecuted\":true"
                ),
                builtApplicationAvailable: false
            )
        }
        #expect(
            try OperatorTerminalClassifier.outcome(
                action: .fullSystemProof,
                exitStatus: 0,
                observation: OperatorTerminalObservation(proof: .proofPass),
                builtApplicationAvailable: true
            ) == .proofPass
        )
        for observation in [
            OperatorTerminalObservation(proof: .none),
            OperatorTerminalObservation(proof: .ambiguous)
        ] {
            expectFailure {
                _ = try OperatorTerminalClassifier.outcome(
                    action: .fullSystemProof,
                    exitStatus: 0,
                    observation: observation,
                    builtApplicationAvailable: true
                )
            }
        }
        expectFailure {
            _ = try OperatorTerminalClassifier.outcome(
                action: .buildApp,
                exitStatus: 0,
                observation: OperatorTerminalObservation(proof: .none),
                builtApplicationAvailable: false
            )
        }
        expectFailure {
            _ = try OperatorTerminalClassifier.outcome(
                action: .verifyRepository,
                exitStatus: 37,
                observation: OperatorTerminalObservation(proof: .none),
                builtApplicationAvailable: false
            )
        }
    }

    @Test
    func sterileEnvironmentDropsUntrustedKeys() throws {
        let fixture = try makeFixture()
        defer { fixture.remove() }
        let home = fixture.control.appendingPathComponent("home")
        let temporary = fixture.control.appendingPathComponent("tmp")
        for directory in [home, temporary] {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700]
            )
        }
        let environment = try OperatorCommandRunner.sterileEnvironment(
            from: [
                "HOME": home.path,
                "TMPDIR": temporary.path,
                "UNTRUSTED": "must-not-cross"
            ]
        )
        #expect(
            Set(environment.keys)
                == Set(["HOME", "TMPDIR", "PATH", "LANG", "LC_ALL"])
        )
        #expect(environment["UNTRUSTED"] == nil)
    }

    @Test
    func processGroupRejectsUnsafeTargets() {
        #expect(!OperatorProcessGroup.isSafe(0))
        #expect(!OperatorProcessGroup.isSafe(1))
        #expect(!OperatorProcessGroup.isSafe(getpgrp()))
        #expect(OperatorProcessGroup.isSafe(max(getpgrp() + 1, 2)))
    }

    @Test
    func processIDReadinessWaitsForNumericContents() throws {
        let url = FileManager.default.temporaryDirectory
            .resolvingSymlinksInPath()
            .standardizedFileURL
            .appendingPathComponent(
                "corelm-operator-pid-readiness-\(UUID().uuidString)"
            )
        try Data().write(to: url, options: .withoutOverwriting)
        defer { try? FileManager.default.removeItem(at: url) }
        let expected = getpid()
        let payload = Data("\(expected)\n".utf8)
        let written = DispatchSemaphore(value: 0)
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.1) {
            try? payload.write(to: url, options: .atomic)
            written.signal()
        }
        let observed = waitForProcessID(in: url, seconds: 2)
        #expect(observed == expected)
        #expect(written.wait(timeout: .now() + 1) == .success)
    }

    @Test
    func realRunnerDrainsBothStreamsThroughEOFBeforeCompletion() throws {
        let launcher = try builtCommandLauncher()
        let terminal = OperatorProofTerminalObserver.passLine
        let dispatcher = """
            #!/bin/sh
            (
                index=0
                while [ "$index" -lt 3000 ]; do
                    printf 'stdout-%04d-abcdefghijklmnopqrstuvwxyz\\n' "$index"
                    index=$((index + 1))
                done
            ) &
            stdout_pid=$!
            (
                index=0
                while [ "$index" -lt 3000 ]; do
                    printf 'stderr-%04d-abcdefghijklmnopqrstuvwxyz\\n' "$index" >&2
                    index=$((index + 1))
                done
            ) &
            stderr_pid=$!
            wait "$stdout_pid"
            wait "$stderr_pid"
            (
                trap '' TERM
                /bin/sleep 1
                printf 'late-inherited-fd-tail\\n'
            ) &
            printf '%s\\n' '\(terminal)'
            exit 0
            """
        let fixture = try makeFixture(
            dispatcher: dispatcher,
            commandLauncher: launcher
        )
        defer { fixture.remove() }
        let environment = try runtimeEnvironment(fixture: fixture)
        let runner = OperatorCommandRunner(
            sourceEnvironment: environment,
            hostname: "fixture-host"
        )
        let capture = LockedRunCapture()
        let completed = DispatchSemaphore(value: 0)
        let started = Date()
        var didComplete = false
        let handle = try runner.run(
            action: .fullSystemProof,
            configuration: fixture.configuration,
            onOutput: { capture.append($0) },
            completion: {
                capture.finish($0)
                completed.signal()
            }
        )
        defer {
            if !didComplete {
                handle.cancel()
                _ = completed.wait(timeout: .now() + 10)
            }
        }
        let completionObserved =
            completed.wait(timeout: .now() + 15) == .success
        didComplete = completionObserved
        try #require(completionObserved)
        let elapsed = Date().timeIntervalSince(started)
        let value = capture.value()
        let result = try #require(value.result)
        #expect(elapsed >= 0.8)
        #expect(result.exitStatus == 0)
        #expect(result.integrityError == nil)
        #expect(result.terminalObservation.proof == .proofPass)
        #expect(result.output.contains("stdout-2999"))
        #expect(result.output.contains("stderr-2999"))
        #expect(result.output.contains("late-inherited-fd-tail"))
        #expect(result.output.count < 140_000)
        #expect(!value.snapshots.isEmpty)
        for pair in zip(value.snapshots, value.snapshots.dropFirst()) {
            #expect(pair.0.sequence < pair.1.sequence)
            #expect(pair.0.runID == pair.1.runID)
        }
        #expect(value.snapshots.last?.sequence == result.finalSequence)
        #expect(value.snapshots.last?.text == result.output)
        #expect(
            !FileManager.default.fileExists(
                atPath: fixture.configuration.commandAuthority.groupFile.path
            )
        )
    }

    @Test
    func realLauncherPassesExactlyFiveEnvironmentKeys() throws {
        let launcher = try builtCommandLauncher()
        let initialFixture = try makeFixture(
            commandLauncher: launcher
        )
        let source = initialFixture.root.appendingPathComponent(
            "environment-fixture.c"
        )
        try Data(
            """
            #include <stdio.h>
            extern char **environ;
            int main(void) {
                for (char **item = environ; *item != NULL; ++item) {
                    puts(*item);
                }
                return 0;
            }
            """.utf8
        ).write(to: source, options: .withoutOverwriting)
        let compiler = Process()
        compiler.executableURL = URL(fileURLWithPath: "/usr/bin/xcrun")
        compiler.arguments = [
            "--sdk", "macosx", "clang",
            source.path,
            "-o", initialFixture.project.dispatcher.path
        ]
        compiler.standardInput = FileHandle.nullDevice
        compiler.standardOutput = FileHandle.nullDevice
        compiler.standardError = FileHandle.nullDevice
        try compiler.run()
        compiler.waitUntilExit()
        #expect(compiler.terminationStatus == 0)
        let project = try OperatorProject(rootPath: initialFixture.root.path)
        let configuration = try OperatorLaunchConfiguration(
            arguments: [
                "CoreLMOperator",
                "--project-root", initialFixture.root.path,
                "--command-launcher", launcher.path,
                "--group-file",
                initialFixture.control
                    .appendingPathComponent("active-command-pgid").path
            ]
        )
        let fixture = Fixture(
            root: initialFixture.root,
            control: initialFixture.control,
            project: project,
            configuration: configuration
        )
        defer { fixture.remove() }
        let environment = try runtimeEnvironment(fixture: fixture)
        let runner = OperatorCommandRunner(
            sourceEnvironment: environment,
            hostname: "fixture-host"
        )
        let capture = LockedRunCapture()
        let completed = DispatchSemaphore(value: 0)
        _ = try runner.run(
            action: .verifyRepository,
            configuration: fixture.configuration,
            onOutput: { capture.append($0) },
            completion: {
                capture.finish($0)
                completed.signal()
            }
        )
        #expect(completed.wait(timeout: .now() + 10) == .success)
        let result = try #require(capture.value().result)
        #expect(result.exitStatus == 0)
        let keys = result.output.split(separator: "\n")
            .filter { !$0.hasPrefix("[") }
            .compactMap { $0.split(separator: "=", maxSplits: 1).first }
            .map(String.init)
        #expect(keys == ["HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"])
        #expect(!result.output.contains("__CF_USER_TEXT_ENCODING"))
    }

    @Test
    func realLauncherRejectsVerifierMutationBeforePostCommandSpawn() throws {
        let launcher = try builtCommandLauncher()
        let dispatcher = """
            #!/bin/sh
            /usr/bin/printf '%s\n' '#!/bin/sh' \
                "printf 'MUTATED-VERIFIER-RAN\\n'" \
                'exit 0' >security/verify_app_bundle.sh
            /bin/chmod 700 security/verify_app_bundle.sh
            exit 0
            """
        let fixture = try makeFixture(
            dispatcher: dispatcher,
            commandLauncher: launcher
        )
        defer { fixture.remove() }
        let environment = try runtimeEnvironment(fixture: fixture)
        let runner = OperatorCommandRunner(
            sourceEnvironment: environment,
            hostname: "fixture-host"
        )
        let capture = LockedRunCapture()
        let completed = DispatchSemaphore(value: 0)
        var didComplete = false
        let handle = try runner.run(
            action: .buildApp,
            configuration: fixture.configuration,
            onOutput: { capture.append($0) },
            completion: {
                capture.finish($0)
                completed.signal()
            }
        )
        defer {
            if !didComplete {
                handle.cancel()
                _ = completed.wait(timeout: .now() + 10)
            }
        }
        let completionObserved =
            completed.wait(timeout: .now() + 10) == .success
        didComplete = completionObserved
        try #require(completionObserved)
        let result = try #require(capture.value().result)
        #expect(result.exitStatus == 127)
        #expect(result.integrityError != nil)
        #expect(!result.output.contains("MUTATED-VERIFIER-RAN"))
        #expect(
            result.output.contains(
                "dispatcher or verifier changed at the spawn boundary"
            )
        )
        #expect(
            !FileManager.default.fileExists(
                atPath: fixture.configuration.commandAuthority.groupFile.path
            )
        )
    }

    @Test
    func realRunnerCancelKillsTERMResistantGroupWithoutResidue() throws {
        let launcher = try builtCommandLauncher()
        let identifier = UUID().uuidString
        let base = FileManager.default.temporaryDirectory
            .resolvingSymlinksInPath()
            .standardizedFileURL
        let pidFile = base.appendingPathComponent(
            "corelm-operator-descendant-\(identifier).pid"
        )
        let separateGroupFile = base.appendingPathComponent(
            "corelm-operator-separate-group-\(identifier).pid"
        )
        defer { try? FileManager.default.removeItem(at: pidFile) }
        defer { try? FileManager.default.removeItem(at: separateGroupFile) }
        let dispatcher = """
            #!/bin/sh
            (
                trap '' TERM
                while :; do /bin/sleep 1; done
            ) &
            child=$!
            printf '%s\\n' "$child" >'\(pidFile.path)'
            /usr/bin/python3 -c 'import os,signal,time; os.setsid(); signal.signal(signal.SIGTERM, signal.SIG_IGN); open("\(separateGroupFile.path)", "w", encoding="ascii").write(str(os.getpid()) + "\\n"); time.sleep(60)' &
            cleanup_groups() {
                trap '' TERM
                separate_group=$(/bin/cat '\(separateGroupFile.path)')
                /bin/kill -TERM -- "-$separate_group" 2>/dev/null || :
                /bin/sleep 4
                /bin/kill -KILL -- "-$separate_group" 2>/dev/null || :
                exit 143
            }
            trap cleanup_groups TERM
            while :; do /bin/sleep 1; done
            """
        let fixture = try makeFixture(
            dispatcher: dispatcher,
            commandLauncher: launcher
        )
        defer { fixture.remove() }
        let environment = try runtimeEnvironment(fixture: fixture)
        let runner = OperatorCommandRunner(
            sourceEnvironment: environment,
            hostname: "fixture-host"
        )
        let capture = LockedRunCapture()
        let completed = DispatchSemaphore(value: 0)
        let cleanupGuard = TestProcessCleanupGuard()
        cleanupGuard.recordProcessFile(pidFile)
        cleanupGuard.recordGroupFile(separateGroupFile)
        defer { cleanupGuard.clean() }
        let handle = try runner.run(
            action: .verifyRepository,
            configuration: fixture.configuration,
            onOutput: { capture.append($0) },
            completion: {
                capture.finish($0)
                completed.signal()
            }
        )
        let groupBytes = try Data(
            contentsOf: fixture.configuration.commandAuthority.groupFile
        )
        let groupText = try #require(String(data: groupBytes, encoding: .ascii))
        let groupID = try #require(
            Int32(groupText.trimmingCharacters(in: .whitespacesAndNewlines))
        )
        cleanupGuard.recordGroup(groupID)
        let childID = try #require(
            waitForProcessID(in: pidFile, seconds: 3)
        )
        try #require(getpgid(childID) == groupID)
        cleanupGuard.recordProcess(childID)
        let separateGroupID = try #require(
            waitForProcessID(in: separateGroupFile, group: true, seconds: 3)
        )
        try #require(getpgid(separateGroupID) == separateGroupID)
        cleanupGuard.recordGroup(separateGroupID)
        let cancelled = Date()
        handle.cancel()
        // The monotonic semaphore deadline is the upper completion bound.
        // A narrower Date-based check would also measure scheduler delay after
        // the completion signal and can reject an already-clean result.
        try #require(completed.wait(timeout: .now() + 12) == .success)
        let elapsed = Date().timeIntervalSince(cancelled)
        let result = try #require(capture.value().result)
        #expect(elapsed >= 5.5)
        #expect(result.exitStatus != 0)
        try #require(kill(-groupID, 0) == -1 && errno == ESRCH)
        try #require(kill(childID, 0) == -1 && errno == ESRCH)
        try #require(kill(-separateGroupID, 0) == -1 && errno == ESRCH)
        #expect(
            !FileManager.default.fileExists(
                atPath: fixture.configuration.commandAuthority.groupFile.path
            )
        )
        cleanupGuard.disarm()
    }
}
