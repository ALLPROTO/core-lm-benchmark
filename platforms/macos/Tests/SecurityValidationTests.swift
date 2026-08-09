import Foundation
import Darwin
import Testing
@testable import CoreLMBenchmarkApp

@Suite
struct SecurityValidationTests {
    private func waitUntil(_ condition: () -> Bool) -> Bool {
        for _ in 0..<500 {
            if condition() {
                return true
            }
            usleep(10_000)
        }
        return condition()
    }

    @Test
    func testCapturedProcessGroupKillsChildAfterLeaderExits() throws {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-process-group-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: temporary,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporary) }

        let ready = temporary.appendingPathComponent("ready")
        let termObserved = temporary.appendingPathComponent("term-observed")
        let fixture = """
        import os
        import signal
        import sys
        import time

        def write_marker(path, payload):
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

        os.setpgid(0, 0)
        child = os.fork()
        if child == 0:
            def observe_term(_signum, _frame):
                write_marker(sys.argv[2], b"SIGTERM ignored\\n")

            signal.signal(signal.SIGTERM, observe_term)
            write_marker(sys.argv[1], b"ready\\n")
            while True:
                time.sleep(1)

        while True:
            time.sleep(1)
        """

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        task.arguments = ["-c", fixture, ready.path, termObserved.path]
        try task.run()
        let groupID = pid_t(task.processIdentifier)
        var groupNeedsCleanup = true
        defer {
            if groupNeedsCleanup {
                _ = ProcessGroupSupervisor.signal(SIGKILL, groupID: groupID)
            }
            if task.isRunning {
                _ = kill(task.processIdentifier, SIGKILL)
            }
        }

        try #require(waitUntil { getpgid(groupID) == groupID })
        try #require(waitUntil {
            FileManager.default.fileExists(atPath: ready.path)
        })
        try #require(
            ProcessGroupSupervisor.signal(SIGTERM, groupID: groupID)
        )
        try #require(waitUntil { !task.isRunning })
        task.waitUntilExit()
        #expect(task.terminationReason == .uncaughtSignal)
        #expect(task.terminationStatus == SIGTERM)
        try #require(waitUntil {
            FileManager.default.fileExists(atPath: termObserved.path)
        })
        #expect(ProcessGroupSupervisor.groupExists(groupID))

        try #require(ProcessGroupSupervisor.forceKillIfPresent(groupID))
        try #require(waitUntil {
            !ProcessGroupSupervisor.groupExists(groupID)
        })
        groupNeedsCleanup = false
    }

    @Test
    func testReleaseProofPolicyPinsRegisteredValidationSlice() {
        let developmentSettings = RealLLMRunSettings(
            validationStartBlock: 128,
            validationBlocks: 16
        )
        let releaseSettings = CompressionProofRunPolicy.effectiveSettings(
            requested: developmentSettings,
            allowsDevelopmentOverrides: false
        )
        #expect(
            releaseSettings.validationStartBlock
                == CompressionProofRunPolicy.registeredStartBlock
        )
        #expect(
            releaseSettings.validationBlocks
                == CompressionProofRunPolicy.registeredBlockCount
        )

        let retainedDevelopmentSettings =
            CompressionProofRunPolicy.effectiveSettings(
                requested: developmentSettings,
                allowsDevelopmentOverrides: true
            )
        #expect(retainedDevelopmentSettings.validationStartBlock == 128)
        #expect(retainedDevelopmentSettings.validationBlocks == 16)
    }

    private func expectFailure(
        _ operation: () throws -> Void
    ) {
        do {
            try operation()
            Issue.record("Expected operation to fail closed.")
        } catch {
            // Expected.
        }
    }

    private func expectFailure(
        containing expectedMessage: String,
        _ operation: () throws -> Void
    ) {
        do {
            try operation()
            Issue.record("Expected operation to fail closed.")
        } catch {
            #expect(error.localizedDescription.contains(expectedMessage))
        }
    }

    @Test
    func testCanonicalPythonCompatibleDigest() throws {
        let digest =
            "acb9f7c35d3b2f7747c83912a817df22f48e6ebd7a50e60ab0f968d69eae2fb6"
        let json = """
        {
          "z": {"n": 0.003228019940281981},
          "resultSHA256": "\(digest)",
          "b": [true, "é", -8.493661880493164e-06],
          "a": 1.0
        }
        """
        #expect(
            try SecurityValidation.verifiedCanonicalResultDigest(
                from: Data(json.utf8)
            ) == digest
        )
    }

    @Test
    func testCanonicalDigestOfRecordedRealLLMArtifact() throws {
        let project = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let artifact = project
            .appendingPathComponent("real-llm-v5-development")
            .appendingPathComponent("validation-024-031.json")
        let data = try Data(contentsOf: artifact)
        #expect(
            try SecurityValidation.verifiedCanonicalResultDigest(
                from: data
            ) == "c72d433eea71e3bb60cd5cfab0b30bd25b12a6b7ba5bb9c1e0411bd7f89f2773"
        )
    }

    @Test
    func testCanonicalDigestMismatchFailsClosed() {
        let json = """
        {"a":1,"resultSHA256":"0000000000000000000000000000000000000000000000000000000000000000"}
        """
        expectFailure {
            _ = try SecurityValidation.verifiedCanonicalResultDigest(
                from: Data(json.utf8)
            )
        }
    }

    @Test
    func testIntegerOverflowIsRejected() throws {
        expectFailure {
            _ = try SecurityValidation.checkedAdd(Int.max, 1)
        }
        #expect(try SecurityValidation.checkedAdd(64, 32) == 96)
    }

    @Test
    func testChildEnvironmentIsAllowlisted() {
        let environment = SecurityValidation.sanitizedChildEnvironment(
            additions: ["HF_HUB_OFFLINE": "1"]
        )
        #expect(environment["HF_HUB_OFFLINE"] == "1")
        #expect(environment["PYTHONPATH"] == nil)
        #expect(environment["PYTHONHOME"] == nil)
        #expect(environment["DYLD_INSERT_LIBRARIES"] == nil)
        #expect(environment["SSH_AUTH_SOCK"] == nil)
    }

    @Test
    @MainActor
    func testCompressionWorkerEnvironmentHasMacSafetyLimits() {
        let cache = URL(fileURLWithPath: "/tmp/corelm-model-cache")
        let groupFile = URL(
            fileURLWithPath: "/tmp/corelm-run/.worker-process-group"
        )
        let environment = BenchmarkStore.realLLMWorkerEnvironment(
            cache: cache,
            supervisionFile: groupFile
        )

        #expect(environment["HF_HOME"] == cache.path)
        #expect(environment["HF_HUB_OFFLINE"] == "1")
        #expect(environment["TRANSFORMERS_OFFLINE"] == "1")
        #expect(environment["CORELM_WORKER_GROUP_FILE"] == groupFile.path)
        #expect(environment["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1")
        #expect(environment["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] == "0.85")
        #expect(environment["PYTORCH_MPS_LOW_WATERMARK_RATIO"] == "0.75")
        for key in [
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"
        ] {
            #expect(environment[key] == "2")
        }
        #expect(BenchmarkStore.realLLMHardTimeoutSeconds == 300)
        #expect(environment["PYTHONPATH"] == nil)
        #expect(environment["DYLD_INSERT_LIBRARIES"] == nil)
        #expect(environment["HF_TOKEN"] == nil)
        #expect(environment["HUGGING_FACE_HUB_TOKEN"] == nil)
    }

    @Test
    @MainActor
    func testCompressionWorkerFailureKeepsCauseAndRedactsHome() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let message = BenchmarkStore.workerFailureMessage(
            status: 1,
            detail: "Traceback\nModuleNotFoundError at \(home)/private.py\n"
        )
        #expect(message.contains("status 1"))
        #expect(message.contains("ModuleNotFoundError"))
        #expect(message.contains("<home>/private.py"))
        #expect(!message.contains(home))
    }

    @Test
    @MainActor
    func testPublicResultLabelIsRelativeAndFailsClosed() {
        let identifier = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        let result = URL(
            fileURLWithPath:
                "/Users/private-name/Library/Application Support/"
                    + "CoreLMBenchmark/real-llm-results/\(identifier)/"
                    + "validation-064-071.json"
        )
        let label = BenchmarkStore.publicResultLabel(for: result)
        #expect(label == "\(identifier)/validation-064-071.json")
        #expect(label?.contains("/Users/") == false)
        #expect(label?.contains("private-name") == false)

        let malformedDirectory = result
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("not-a-run")
            .appendingPathComponent("validation-064-071.json")
        #expect(BenchmarkStore.publicResultLabel(for: malformedDirectory) == nil)
        #expect(
            BenchmarkStore.publicResultLabel(
                for: result.deletingLastPathComponent()
                    .appendingPathComponent("unexpected.json")
            ) == nil
        )
        #expect(
            BenchmarkStore.publicResultLabel(
                for: URL(string: "https://example.invalid/result.json")!
            ) == nil
        )
    }

    @Test
    @MainActor
    func testPublicLogSanitizerRemovesPathsCredentialsAndNulls() {
        let token = "gh" + "p_" + String(repeating: "A", count: 30)
        let raw =
            "Traceback: /Users/private-name/project/runner.py\u{0} "
            + "token=\(token)"
        let sanitized = BenchmarkStore.sanitizedPublicMessage(raw)
        #expect(sanitized.contains("<home>/project/runner.py"))
        #expect(sanitized.contains("[REDACTED_CREDENTIAL]"))
        #expect(!sanitized.contains("/Users/"))
        #expect(!sanitized.contains("private-name"))
        #expect(!sanitized.contains(token))
        #expect(!sanitized.contains("\u{0}"))
    }

    @Test
    func testRegularFileReaderRejectsSymlink() throws {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-security-tests-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: temporary,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporary) }

        let regular = temporary.appendingPathComponent("result.json")
        try Data("{}".utf8).write(to: regular, options: .atomic)
        let link = temporary.appendingPathComponent("link.json")
        try FileManager.default.createSymbolicLink(
            at: link,
            withDestinationURL: regular
        )

        #expect(
            try SecurityValidation.readRegularFile(
                at: regular,
                maximumBytes: 32
            ) == Data("{}".utf8)
        )
        expectFailure {
            _ = try SecurityValidation.readRegularFile(
                at: link,
                maximumBytes: 32
            )
        }
    }

    @Test
    func testRegularFileReaderEnforcesSizeLimit() throws {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-security-tests-\(UUID().uuidString)"
            )
        defer { try? FileManager.default.removeItem(at: temporary) }
        try Data(repeating: 0x41, count: 33).write(
            to: temporary,
            options: .atomic
        )
        expectFailure {
            _ = try SecurityValidation.readRegularFile(
                at: temporary,
                maximumBytes: 32
            )
        }
    }

    @Test
    func testOutputPathMustRemainAbsentForExclusiveWorkerWrite() throws {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-security-tests-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: temporary,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporary) }
        let output = temporary.appendingPathComponent("result.json")

        try SecurityValidation.requirePathAbsentInValidatedDirectory(output)
        try Data("{}".utf8).write(to: output)
        expectFailure {
            try SecurityValidation.requirePathAbsentInValidatedDirectory(
                output
            )
        }
    }

    @Test
    func testPythonRuntimeManifestRejectsTamperingAndExtraFiles() throws {
        let buildDirectory = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(".build", isDirectory: true)
        let temporary = buildDirectory
            .appendingPathComponent(
                "corelm-runtime-manifest-\(UUID().uuidString)",
                isDirectory: true
            )
        let base = temporary.appendingPathComponent(
            "base", isDirectory: true
        )
        let virtualEnvironment = temporary.appendingPathComponent(
            "venv", isDirectory: true
        )
        let baseBin = base.appendingPathComponent("bin", isDirectory: true)
        let venvBin = virtualEnvironment.appendingPathComponent(
            "bin", isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: temporary) }
        try FileManager.default.createDirectory(
            at: buildDirectory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        for directory in [temporary, base, virtualEnvironment, baseBin, venvBin] {
            try FileManager.default.createDirectory(
                at: directory,
                withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700]
            )
        }
        let resolvedPython = baseBin.appendingPathComponent("python3")
        let executable = Data("#!/bin/sh\nexit 0\n".utf8)
        try executable.write(to: resolvedPython)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: resolvedPython.path
        )
        let declaredPython = venvBin.appendingPathComponent("python")
        try FileManager.default.createSymbolicLink(
            atPath: declaredPython.path,
            withDestinationPath: resolvedPython.path
        )
        let volatileCache = baseBin.appendingPathComponent(
            "__pycache__", isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: volatileCache,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        try Data("volatile".utf8).write(
            to: volatileCache.appendingPathComponent("module.pyc")
        )
        let digest = SecurityValidation.sha256Hex(executable)
        let manifest: [String: Any] = [
            "entries": [
                [
                    "kind": "file",
                    "path": "bin/python3",
                    "root": 0,
                    "sha256": digest,
                    "size": executable.count
                ],
                [
                    "kind": "symlink",
                    "path": "bin/python",
                    "root": 1,
                    "target": resolvedPython.path
                ]
            ],
            "fileCount": 1,
            "pythonDeclaredPath": declaredPython.path,
            "pythonExecutableSHA256": digest,
            "pythonResolvedPath": declaredPython
                .resolvingSymlinksInPath().standardizedFileURL.path,
            "pythonVersion": "3.12.13",
            "roots": [
                ["path": base.path, "role": "base-prefix"],
                [
                    "path": virtualEnvironment.path,
                    "role": "virtual-environment"
                ]
            ],
            "schemaVersion": "corelm-python-runtime-manifest-v1",
            "symlinkCount": 1,
            "totalBytes": executable.count
        ]
        let manifestURL = temporary.appendingPathComponent("manifest.json")
        try JSONSerialization.data(
            withJSONObject: manifest,
            options: [.sortedKeys]
        ).write(to: manifestURL)
        try SecurityValidation.validatePythonRuntimeManifest(
            at: manifestURL,
            expectedPythonURL: declaredPython
        )
        let aliasedRuntime = buildDirectory.appendingPathComponent(
            "corelm-runtime-alias-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createSymbolicLink(
            at: aliasedRuntime,
            withDestinationURL: temporary
        )
        defer { try? FileManager.default.removeItem(at: aliasedRuntime) }
        try SecurityValidation.validatePythonRuntimeManifest(
            at: manifestURL,
            expectedPythonURL: aliasedRuntime
                .appendingPathComponent("venv/bin/python")
        )

        let unsafeLink = venvBin.appendingPathComponent("python-cache")
        try FileManager.default.createSymbolicLink(
            atPath: unsafeLink.path,
            withDestinationPath: volatileCache
                .appendingPathComponent("module.pyc").path
        )
        var unsafeEntries = try #require(
            manifest["entries"] as? [[String: Any]]
        )
        unsafeEntries.append([
            "kind": "symlink",
            "path": "bin/python-cache",
            "root": 1,
            "target": volatileCache
                .appendingPathComponent("module.pyc").path
        ])
        var unsafeManifest = manifest
        unsafeManifest["entries"] = unsafeEntries
        unsafeManifest["symlinkCount"] = 2
        try JSONSerialization.data(
            withJSONObject: unsafeManifest,
            options: [.sortedKeys]
        ).write(to: manifestURL)
        expectFailure {
            try SecurityValidation.validatePythonRuntimeManifest(
                at: manifestURL,
                expectedPythonURL: declaredPython
            )
        }
        try FileManager.default.removeItem(at: unsafeLink)

        let outsideRuntime = temporary.appendingPathComponent("outside.py")
        try Data("outside".utf8).write(to: outsideRuntime)
        try FileManager.default.createSymbolicLink(
            atPath: unsafeLink.path,
            withDestinationPath: outsideRuntime.path
        )
        unsafeEntries[unsafeEntries.count - 1]["target"] = outsideRuntime.path
        unsafeManifest["entries"] = unsafeEntries
        try JSONSerialization.data(
            withJSONObject: unsafeManifest,
            options: [.sortedKeys]
        ).write(to: manifestURL)
        expectFailure {
            try SecurityValidation.validatePythonRuntimeManifest(
                at: manifestURL,
                expectedPythonURL: declaredPython
            )
        }
        try FileManager.default.removeItem(at: unsafeLink)
        try JSONSerialization.data(
            withJSONObject: manifest,
            options: [.sortedKeys]
        ).write(to: manifestURL)

        let injected = venvBin.appendingPathComponent("sitecustomize.py")
        try Data("raise RuntimeError()\n".utf8).write(to: injected)
        expectFailure {
            try SecurityValidation.validatePythonRuntimeManifest(
                at: manifestURL,
                expectedPythonURL: declaredPython
            )
        }
        try FileManager.default.removeItem(at: injected)
        try Data("# tampered\n".utf8).write(to: resolvedPython)
        expectFailure {
            try SecurityValidation.validatePythonRuntimeManifest(
                at: manifestURL,
                expectedPythonURL: declaredPython
            )
        }
    }

    @Test
    @MainActor
    func testExistingRealLLMResultPassesCanonicalAndStructuralVerification()
        throws
    {
        let source = try #require(
            Bundle.module.url(
                forResource: "real-llm-validation-064-071",
                withExtension: "json",
                subdirectory: "Fixtures"
            )
        )
        let original = try SecurityValidation.readRegularFile(
            at: source,
            maximumBytes: SecurityValidation.maximumRealLLMResultBytes
        )
        _ = try SecurityValidation.verifiedCanonicalResultDigest(from: original)

        var object = try #require(
            JSONSerialization.jsonObject(with: original) as? [String: Any]
        )
        object["schemaVersion"] =
            "corelm-voidtoken-v5-validation-development-v2"
        var manifestRecords = try #require(
            object["records"] as? [[String: Any]]
        )
        for recordIndex in manifestRecords.indices {
            let payloadTotal = try #require(
                manifestRecords[recordIndex]["payloadBytes"] as? NSNumber
            ).intValue
            let encodedTotal = try #require(
                manifestRecords[recordIndex]["encodedFileBytes"] as? NSNumber
            ).intValue
            let remainingPayload = payloadTotal - 200_000
            let ordinaryPayload = remainingPayload / 22
            var ordinaryRemainder = remainingPayload % 22
            var manifest: [[String: Any]] = []
            for layerIndex in 0..<24 {
                let bits = [0, 8].contains(layerIndex) ? 9 : 8
                let payloadBytes: Int
                if [0, 8].contains(layerIndex) {
                    payloadBytes = 100_000
                } else {
                    payloadBytes =
                        ordinaryPayload + (ordinaryRemainder > 0 ? 1 : 0)
                    ordinaryRemainder = max(0, ordinaryRemainder - 1)
                }
                let digest: (String) -> String = { label in
                    SecurityValidation.sha256Hex(
                        Data(
                            "\(label)-\(recordIndex)-\(layerIndex)".utf8
                        )
                    )
                }
                let metadata: [String: Any] = [
                    "bits": bits,
                    "codeCompression": "zlib-9",
                    "codeCount": 383 * 256,
                    "codeMapping": "zigzag-symmetric-v1",
                    "dtype": "float32",
                    "format": "voidtoken-rotated-entropy-v5",
                    "groupSize": 128,
                    "groupsPerRow": 2,
                    "inputSha256": digest("input"),
                    "layerIndex": layerIndex,
                    "packedBytes": bits == 9 ? 110_304 : 98_048,
                    "packing": bits == 9
                        ? "byte-low-plus-lsb-high-fields-v1"
                        : "lsb-first-v1",
                    "payloadBytes": payloadBytes,
                    "payloadSha256": digest("payload"),
                    "quantization": "symmetric-max-abs-v1",
                    "reconstructionSha256": digest("reconstruction"),
                    "scaleBytes": 383 * 2 * 2,
                    "scaleCompression": "zlib-9",
                    "scaleCount": 383 * 2,
                    "scaleDtype": "float16-le",
                    "shape": [383, 256],
                    "signDerivation": "shake256-layer-column-v1",
                    "signMode": "none",
                    "storedCodeBytes": payloadBytes - 1_500,
                    "storedScaleBytes": 1_500,
                    "transform": "normalized-walsh-hadamard-v1",
                    "transformBlockSize": 128
                ]
                let metadataBytes = try JSONSerialization.data(
                    withJSONObject: metadata,
                    options: [.sortedKeys, .withoutEscapingSlashes]
                )
                manifest.append(
                    [
                        "layerIndex": layerIndex,
                        "metadata": metadata,
                        "payloadBytes": payloadBytes,
                        "containerBytes":
                            8 + metadataBytes.count + payloadBytes,
                        "containerSHA256": digest("container")
                    ]
                )
            }
            #expect(
                manifest.reduce(0) {
                    $0 + (($1["payloadBytes"] as? NSNumber)?.intValue ?? -1)
                } == payloadTotal
            )
            #expect(
                manifest.reduce(0) {
                    $0 + (($1["containerBytes"] as? NSNumber)?.intValue ?? -1)
                } == encodedTotal
            )
            let manifestBytes = try JSONSerialization.data(
                withJSONObject: manifest,
                options: [.sortedKeys, .withoutEscapingSlashes]
            )
            manifestRecords[recordIndex]["containerManifest"] = manifest
            manifestRecords[recordIndex]["containerManifestSHA256"] =
                SecurityValidation.sha256Hex(manifestBytes)
        }
        object["records"] = manifestRecords
        var environment = try #require(
            object["environment"] as? [String: Any]
        )
        environment["hfHome"] = "configured"
        object["environment"] = environment
        object.removeValue(forKey: "resultSHA256")
        let withoutDigest = try JSONSerialization.data(
            withJSONObject: object,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        object["resultSHA256"] =
            try SecurityValidation
                .canonicalResultDigestExcludingEmbeddedClaim(
                    from: withoutDigest
                )
        let hardenedData = try JSONSerialization.data(
            withJSONObject: object,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        let digest = try SecurityValidation.verifiedCanonicalResultDigest(
            from: hardenedData
        )
        let decoded = try JSONDecoder().decode(
            RealLLMResult.self,
            from: hardenedData
        )
        #expect(decoded.resultSHA256 == digest)

        let store = BenchmarkStore()
        let expected = RealLLMRunSettings(
            validationStartBlock:
                decoded.protocolInfo.validationStartBlock,
            validationBlocks:
                decoded.protocolInfo.validationBlocks
        )
        try store.verifyRealLLMResult(decoded, expected: expected)

        environment["hfHome"] = source.path
        object["environment"] = environment
        let wrongEnvironment = try JSONSerialization.data(
            withJSONObject: object
        )
        let wrongEnvironmentResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: wrongEnvironment
        )
        expectFailure {
            try store.verifyRealLLMResult(
                wrongEnvironmentResult,
                expected: expected
            )
        }

        environment["hfHome"] = "configured"
        object["environment"] = environment
        var baselines = try #require(
            object["baselines"] as? [[String: Any]]
        )
        var firstBaseline = try #require(baselines.first)
        let originalNativeAgreement = try #require(
            firstBaseline["nativeBF16Top1Agreement"] as? NSNumber
        ).doubleValue
        firstBaseline["nativeBF16Top1Agreement"] = 0.5 + (1.0 / 256.0)
        baselines[0] = firstBaseline
        object["baselines"] = baselines
        let fractionalNativeAgreement = try JSONSerialization.data(
            withJSONObject: object
        )
        let fractionalNativeAgreementResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: fractionalNativeAgreement
        )
        expectFailure(containing: "not k/128") {
            try store.verifyRealLLMResult(
                fractionalNativeAgreementResult,
                expected: expected
            )
        }
        firstBaseline["nativeBF16Top1Agreement"] =
            originalNativeAgreement
        let originalDenseBytes = try #require(
            firstBaseline["denseBF16Bytes"] as? NSNumber
        ).intValue
        firstBaseline["denseBF16Bytes"] = originalDenseBytes - 2
        baselines[0] = firstBaseline
        object["baselines"] = baselines
        let inconsistentScalarCount = try JSONSerialization.data(
            withJSONObject: object
        )
        let inconsistentScalarCountResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: inconsistentScalarCount
        )
        expectFailure(containing: "scalar count") {
            try store.verifyRealLLMResult(
                inconsistentScalarCountResult,
                expected: expected
            )
        }
        firstBaseline["denseBF16Bytes"] = originalDenseBytes
        baselines[0] = firstBaseline
        object["baselines"] = baselines

        var records = try #require(
            object["records"] as? [[String: Any]]
        )
        var firstRecord = try #require(records.first)
        let originalDifference = try #require(
            firstRecord["cacheDifferenceSumSquares"] as? NSNumber
        ).doubleValue
        firstRecord["cacheDifferenceSumSquares"] = originalDifference + 1
        records[0] = firstRecord
        object["records"] = records
        let inconsistentCache = try JSONSerialization.data(
            withJSONObject: object
        )
        let inconsistentCacheResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: inconsistentCache
        )
        expectFailure {
            try store.verifyRealLLMResult(
                inconsistentCacheResult,
                expected: expected
            )
        }

        firstRecord["cacheDifferenceSumSquares"] = originalDifference
        firstRecord["cacheMaximumAbsoluteError"] = 0.0
        records[0] = firstRecord
        object["records"] = records
        let impossibleMaximumError = try JSONSerialization.data(
            withJSONObject: object
        )
        let impossibleMaximumErrorResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: impossibleMaximumError
        )
        expectFailure(containing: "maximum-error bounds") {
            try store.verifyRealLLMResult(
                impossibleMaximumErrorResult,
                expected: expected
            )
        }

        firstRecord["cacheReferenceSumSquares"] = 1.0
        firstRecord["cacheCandidateSumSquares"] = 1.0
        firstRecord["cacheDotProduct"] = -2.0
        firstRecord["cacheDifferenceSumSquares"] = 6.0
        firstRecord["cacheMaximumAbsoluteError"] = 1.0
        records[0] = firstRecord
        object["records"] = records
        let impossibleInnerProduct = try JSONSerialization.data(
            withJSONObject: object
        )
        let impossibleInnerProductResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: impossibleInnerProduct
        )
        expectFailure(containing: "Cauchy-Schwarz") {
            try store.verifyRealLLMResult(
                impossibleInnerProductResult,
                expected: expected
            )
        }
    }

    private struct CaptureFixture {
        let result: RealLLMResult
        let resultFileSHA256: String
        let receiptObject: [String: Any]
        let receiptData: Data
        let receiptFileSHA256: String
        let structuralReportData: Data
        let replayReportData: Data
        let terminalReportData: Data
        let runIdentifier: String
    }

    private func captureJSON(
        _ value: Any,
        prettyPrinted: Bool = false,
        newline: Bool = false
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
        if newline {
            data.append(0x0a)
        }
        return data
    }

    private func makeCaptureFixture() throws -> CaptureFixture {
        let source = try #require(
            Bundle.module.url(
                forResource: "real-llm-validation-064-071",
                withExtension: "json",
                subdirectory: "Fixtures"
            )
        )
        let original = try Data(contentsOf: source)
        var resultObject = try #require(
            JSONSerialization.jsonObject(with: original) as? [String: Any]
        )
        var records = try #require(
            resultObject["records"] as? [[String: Any]]
        )
        for recordIndex in records.indices {
            let payloadTotal = try #require(
                records[recordIndex]["payloadBytes"] as? NSNumber
            ).intValue
            let encodedTotal = try #require(
                records[recordIndex]["encodedFileBytes"] as? NSNumber
            ).intValue
            let remainingPayload = payloadTotal - 200_000
            let ordinaryPayload = remainingPayload / 22
            var ordinaryRemainder = remainingPayload % 22
            var manifest: [[String: Any]] = []
            for layerIndex in 0..<24 {
                let bits = [0, 8].contains(layerIndex) ? 9 : 8
                let payloadBytes: Int
                if [0, 8].contains(layerIndex) {
                    payloadBytes = 100_000
                } else {
                    payloadBytes = ordinaryPayload
                        + (ordinaryRemainder > 0 ? 1 : 0)
                    ordinaryRemainder = max(0, ordinaryRemainder - 1)
                }
                let digest: (String) -> String = { label in
                    SecurityValidation.sha256Hex(
                        Data(
                            "capture-\(label)-\(recordIndex)-\(layerIndex)"
                                .utf8
                        )
                    )
                }
                let metadata: [String: Any] = [
                    "bits": bits,
                    "codeCompression": "zlib-9",
                    "codeCount": 383 * 256,
                    "codeMapping": "zigzag-symmetric-v1",
                    "dtype": "float32",
                    "format": "voidtoken-rotated-entropy-v5",
                    "groupSize": 128,
                    "groupsPerRow": 2,
                    "inputSha256": digest("input"),
                    "layerIndex": layerIndex,
                    "packedBytes": bits == 9 ? 110_304 : 98_048,
                    "packing": bits == 9
                        ? "byte-low-plus-lsb-high-fields-v1"
                        : "lsb-first-v1",
                    "payloadBytes": payloadBytes,
                    "payloadSha256": digest("payload"),
                    "quantization": "symmetric-max-abs-v1",
                    "reconstructionSha256": digest("reconstruction"),
                    "scaleBytes": 383 * 2 * 2,
                    "scaleCompression": "zlib-9",
                    "scaleCount": 383 * 2,
                    "scaleDtype": "float16-le",
                    "shape": [383, 256],
                    "signDerivation": "shake256-layer-column-v1",
                    "signMode": "none",
                    "storedCodeBytes": payloadBytes - 1_500,
                    "storedScaleBytes": 1_500,
                    "transform": "normalized-walsh-hadamard-v1",
                    "transformBlockSize": 128
                ]
                let metadataBytes = try captureJSON(metadata)
                manifest.append(
                    [
                        "layerIndex": layerIndex,
                        "metadata": metadata,
                        "payloadBytes": payloadBytes,
                        "containerBytes":
                            8 + metadataBytes.count + payloadBytes,
                        "containerSHA256": digest("container")
                    ]
                )
            }
            records[recordIndex]["containerManifest"] = manifest
            records[recordIndex]["containerManifestSHA256"] =
                SecurityValidation.sha256Hex(
                    try captureJSON(manifest)
                )
            #expect(
                manifest.reduce(0) {
                    $0 + (($1["containerBytes"] as? NSNumber)?.intValue ?? -1)
                } == encodedTotal
            )
        }
        resultObject["records"] = records
        let primary: [String: Any] = [
            "schemaVersion": "corelm-primary-evidence-v1",
            "path": "primary-evidence/manifest.json",
            "manifestSHA256": String(repeating: "3", count: 64),
            "manifestBytes": 4_096,
            "containerCount": 192,
            "containerBytes": 18_000_000,
            "blocks": 8,
            "predictionTokens": 1_024
        ]
        resultObject["schemaVersion"] =
            "corelm-voidtoken-v5-validation-development-v3"
        resultObject["primaryEvidence"] = primary
        let result = try JSONDecoder().decode(
            RealLLMResult.self,
            from: captureJSON(resultObject)
        )
        let aggregate = try #require(result.aggregate)
        let resultFileSHA256 = String(repeating: "a", count: 64)
        let sourceCommit = String(repeating: "1", count: 40)
        let sourceTree = String(repeating: "2", count: 40)
        let buildDocument: [String: Any] = [
            "schemaVersion": "corelm-build-provenance-v1",
            "source": [
                "archiveManifestSHA256": NSNull(),
                "commit": sourceCommit,
                "dirty": false,
                "exactTag": "corelm-portfolio-v5",
                "mode": "git",
                "remote": (
                    "https://github.com/ALLPROTO/"
                    + "core-lm-benchmark.git"
                ),
                "tree": sourceTree
            ],
            "toolchain": [:]
        ]
        let buildSHA256 = SecurityValidation.sha256Hex(
            try captureJSON(buildDocument, newline: true)
        )
        let receiptObject: [String: Any] = [
            "application": [
                "bundleIdentifier": "com.corelm.benchmark",
                "bundleName": "CoreLMBenchmark.app",
                "executableSHA256": String(repeating: "e", count: 64),
                "processIdentifier": 101,
                "version": "0.5.0"
            ],
            "buildProvenance": [
                "document": buildDocument,
                "path": "Resources/build-provenance.json",
                "sha256": buildSHA256
            ],
            "challengeNonce": String(repeating: "c", count: 64),
            "createdAt": "2026-07-30T20:00:00Z",
            "error": NSNull(),
            "primaryEvidence": primary,
            "protocol": [
                "candidateIndex": 32,
                "device": "mps",
                "hfHome": "configured",
                "offlineRequested": true,
                "sanitizedChildEnvironment": true,
                "validationBlocks": 8,
                "validationStartBlock": 64
            ],
            "result": [
                "compressionRatioVsBF16":
                    aggregate.compressionRatioVsBF16,
                "deltaNLLNatPerToken": aggregate.deltaNLLNatPerToken,
                "metricVerdict": "PASS",
                "path": "validation-064-071.json",
                "resultFileSHA256": resultFileSHA256,
                "resultRole": "PUBLIC_VALIDATION_REGRESSION",
                "resultSHA256": result.resultSHA256,
                "swiftStructuralVerification": "PASS",
                "top1Agreement": aggregate.top1Agreement
            ],
            "schemaVersion": "corelm-macos-app-real-llm-run-v5",
            "startedAt": "2026-07-30T18:00:00Z",
            "worker": [
                "processIdentifier": 102,
                "python": "signed-runtime-manifest",
                "pythonExecutableSHA256": String(repeating: "4", count: 64),
                "runtimeManifestSHA256": String(repeating: "5", count: 64),
                "script": "Resources/RealLLM/app_proof_runner.py",
                "scriptSHA256": String(repeating: "6", count: 64),
                "terminationStatus": 0
            ]
        ]
        let receiptData = try captureJSON(
            receiptObject, prettyPrinted: true
        )
        let receiptFileSHA256 = SecurityValidation.sha256Hex(receiptData)
        let reportBinding: [String: Any] = [
            "metric_verdict": "PASS",
            "receipt_sha256": receiptFileSHA256,
            "result_sha256": resultFileSHA256,
            "schema_version": 1,
            "source": ["commit": sourceCommit, "tree": sourceTree],
            "synthetic_data": false,
            "workload_classification":
                "AUTHOR_SELECTED_PUBLIC_VALIDATION_REGRESSION"
        ]
        var structural = reportBinding
        structural["report_kind"] = "structural_verifier"
        structural["verdict"] = "PASS"
        var replay = reportBinding
        replay["execution_scope"] =
            "AUTHOR_RECORDED_NOT_INDEPENDENTLY_REEXECUTED_BY_RELEASE_VERIFIER"
        replay["model"] = [
            "repository": "Qwen/Qwen2.5-0.5B",
            "revision": "060db6499f32faf8b98477b0a26969ef7d8b9987"
        ]
        replay["replay"] = [
            "decisions": 1_024,
            "lossAbsoluteTolerance": 2e-5,
            "lossRelativeTolerance": 2e-6,
            "maximumAllowedBaselineDifference": 2e-5,
            "maximumAllowedCandidateDifference": 2e-5,
            "maximumBaselineLossDifference": 0.0,
            "maximumCandidateLossDifference": 0.0,
            "perDecisionEvidenceSHA256": String(repeating: "7", count: 64),
            "primaryManifestSHA256": String(repeating: "8", count: 64),
            "tokenMetricsSHA256": String(repeating: "9", count: 64)
        ]
        replay["report_kind"] = "fresh_model_replay"
        replay["verdict"] =
            "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS"
        return CaptureFixture(
            result: result,
            resultFileSHA256: resultFileSHA256,
            receiptObject: receiptObject,
            receiptData: receiptData,
            receiptFileSHA256: receiptFileSHA256,
            structuralReportData: try captureJSON(
                structural, newline: true
            ),
            replayReportData: try captureJSON(replay, newline: true),
            terminalReportData: Data("END-TO-END PROOF PASS\n".utf8),
            runIdentifier: "123e4567-e89b-42d3-a456-426614174000"
        )
    }

    @Test
    func testPortfolioCaptureArgumentsAreExactAndFailClosed() {
        let runIdentifier = "123e4567-e89b-42d3-a456-426614174000"
        let readyFilePath = "/private/tmp/corelm-capture/ready.json"
        #expect(
            PortfolioCaptureRequest(arguments: ["app"])
                == .none
        )
        #expect(
            PortfolioCaptureRequest(
                arguments: ["app", "--portfolio-capture-preflight"]
            ) == .preflight
        )
        #expect(
            PortfolioCaptureRequest(
                arguments: ["app", "--portfolio-capture-live"]
            ) == .live
        )
        #expect(
            PortfolioCaptureRequest(
                arguments: [
                    "app", "--portfolio-capture",
                    "--portfolio-result-id", runIdentifier,
                    "--portfolio-ready-file", readyFilePath
                ]
            ) == .result(
                runIdentifier: runIdentifier,
                readyFilePath: readyFilePath
            )
        )
        for arguments in [
            ["app", "--portfolio-capture"],
            ["app", "--portfolio-result-id", runIdentifier],
            ["app", "--portfolio-ready-file", readyFilePath],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier.uppercased(), "--portfolio-ready-file",
                readyFilePath
            ],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier, "--portfolio-ready-file", "relative.json"
            ],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier, "--portfolio-ready-file",
                "/private/tmp/../tmp/ready.json"
            ],
            [
                "app", "--portfolio-capture-preflight",
                "--automated-compression-proof"
            ],
            ["app", "--portfolio-capture-live", "free-form"],
            [
                "app", "--portfolio-capture-live",
                "--automated-compression-proof"
            ],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier, "--portfolio-ready-file", readyFilePath,
                "--proof-challenge",
                String(repeating: "a", count: 64)
            ],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier, "--portfolio-result-id", runIdentifier,
                "--portfolio-ready-file", readyFilePath
            ],
            [
                "app", "--portfolio-capture", "--portfolio-result-id",
                runIdentifier, "--portfolio-ready-file", readyFilePath,
                "--portfolio-ready-file", readyFilePath
            ]
        ] {
            #expect(
                PortfolioCaptureRequest(arguments: arguments) == .invalid
            )
        }
    }

    @Test
    @MainActor
    func testPortfolioPreflightDoesNotStartOrSelectAnyModelRun() async {
        let store = BenchmarkStore(
            commandLineArguments: [
                "CoreLMBenchmarkApp", "--portfolio-capture-preflight"
            ]
        )
        await store.automatedRunIfRequested()
        #expect(store.portfolioCaptureIsPreflight)
        #expect(store.portfolioCaptureSnapshot == nil)
        #expect(store.portfolioCaptureStatusCode == "AUTOMATED CAPTURE PREFLIGHT")
        #expect(!store.isRunning)
        #expect(store.realLLMResult == nil)
        #expect(store.realLLMResultURL == nil)
        #expect(store.lastRealLLMWorkerPID == nil)
        #expect(store.errorMessage == nil)
    }

    @Test
    @MainActor
    func testPortfolioLivePresentationIsFixedAndModelFree() async {
        let store = BenchmarkStore(
            commandLineArguments: [
                "CoreLMBenchmarkApp", "--portfolio-capture-live"
            ]
        )
        #expect(store.portfolioCaptureIsLive)
        #expect(store.portfolioCaptureSnapshot == nil)
        #expect(
            store.portfolioCaptureStatusCode
                == "AUTOMATED VALIDATION IN PROGRESS"
        )
        #expect(!store.isRunning)
        #expect(store.realLLMResult == nil)
        #expect(store.realLLMResultURL == nil)
        #expect(store.lastRealLLMWorkerPID == nil)
        #expect(store.errorMessage == nil)

        // Defense in depth: even an unintended direct call returns before
        // any window preparation, result load, or model execution.
        await store.automatedRunIfRequested()
        #expect(!store.isRunning)
        #expect(store.realLLMResult == nil)
        #expect(store.realLLMResultURL == nil)
        #expect(store.lastRealLLMWorkerPID == nil)
    }

    @Test
    @MainActor
    func testPortfolioCaptureSnapshotBindsExactReceiptAndProofReports()
        throws
    {
        let fixture = try makeCaptureFixture()
        let snapshot = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
            result: fixture.result,
            resultFileSHA256: fixture.resultFileSHA256,
            receiptData: fixture.receiptData,
            receiptFileSHA256: fixture.receiptFileSHA256,
            runIdentifier: fixture.runIdentifier,
            structuralReportData: fixture.structuralReportData,
            replayReportData: fixture.replayReportData,
            terminalReportData: fixture.terminalReportData
        )
        #expect(snapshot.sourceTag == "corelm-portfolio-v5")
        #expect(snapshot.sourceCommit == String(repeating: "1", count: 40))
        #expect(snapshot.sourceTree == String(repeating: "2", count: 40))
        #expect(
            snapshot.challengeSHA256
                == SecurityValidation.sha256Hex(
                    Data(String(repeating: "c", count: 64).utf8)
                )
        )
        #expect(snapshot.runIdentifier == fixture.runIdentifier)
        #expect(snapshot.metricVerdict == "PASS")
        #expect(
            BenchmarkStore.portfolioMetricDecimal(
                snapshot.compressionRatioVsBF16
            ) == "2.052384"
        )
        #expect(
            BenchmarkStore.portfolioMetricDecimal(
                snapshot.deltaNLLNatPerToken
            ) == "-0.000008"
        )
        #expect(
            BenchmarkStore.portfolioMetricDecimal(snapshot.top1Agreement)
                == "0.995117"
        )
        #expect(snapshot.moduleState == "COMPLETE")
        #expect(snapshot.heavyReplayState == "PASS")
        #expect(snapshot.verifierState == "PASS")
        #expect(snapshot.structuralVerdict == "PASS")
        #expect(
            snapshot.replayVerdict
                == "AUTHOR_RECORDED_HEAVY_REPLAY_INTEGRITY_PASS"
        )
        #expect(snapshot.terminalVerdict == "END-TO-END PROOF PASS")

        let swiftReplayText = try #require(
            String(data: fixture.replayReportData, encoding: .utf8)
        )
        let pythonReplayText = swiftReplayText
            .replacingOccurrences(
                of: "2.0000000000000002e-05", with: "2e-05"
            )
            .replacingOccurrences(
                of: "1.9999999999999999e-06", with: "2e-06"
            )
            .replacingOccurrences(
                of: "\"maximumBaselineLossDifference\":0,",
                with: "\"maximumBaselineLossDifference\":0.0,"
            )
            .replacingOccurrences(
                of: "\"maximumCandidateLossDifference\":0,",
                with: "\"maximumCandidateLossDifference\":0.0,"
            )
        _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
            result: fixture.result,
            resultFileSHA256: fixture.resultFileSHA256,
            receiptData: fixture.receiptData,
            receiptFileSHA256: fixture.receiptFileSHA256,
            runIdentifier: fixture.runIdentifier,
            structuralReportData: fixture.structuralReportData,
            replayReportData: Data(pythonReplayText.utf8),
            terminalReportData: fixture.terminalReportData
        )

        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: fixture.receiptData,
                receiptFileSHA256: fixture.receiptFileSHA256,
                runIdentifier: fixture.runIdentifier
            )
        }
    }

    @Test
    @MainActor
    func testPortfolioCaptureRejectsTamperingPartialReportsAndNoncanonicalReceipt()
        throws
    {
        let fixture = try makeCaptureFixture()
        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: fixture.receiptData,
                receiptFileSHA256: fixture.receiptFileSHA256,
                runIdentifier: fixture.runIdentifier,
                structuralReportData: fixture.structuralReportData
            )
        }

        var replay = try #require(
            JSONSerialization.jsonObject(
                with: fixture.replayReportData
            ) as? [String: Any]
        )
        replay["result_sha256"] = String(repeating: "f", count: 64)
        let forgedReplay = try captureJSON(replay, newline: true)
        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: fixture.receiptData,
                receiptFileSHA256: fixture.receiptFileSHA256,
                runIdentifier: fixture.runIdentifier,
                structuralReportData: fixture.structuralReportData,
                replayReportData: forgedReplay,
                terminalReportData: fixture.terminalReportData
            )
        }

        var metricReceipt = fixture.receiptObject
        var metricResult = try #require(
            metricReceipt["result"] as? [String: Any]
        )
        metricResult["top1Agreement"] = 0.5
        metricReceipt["result"] = metricResult
        let forgedMetricReceipt = try captureJSON(
            metricReceipt, prettyPrinted: true
        )
        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: forgedMetricReceipt,
                receiptFileSHA256:
                    SecurityValidation.sha256Hex(forgedMetricReceipt),
                runIdentifier: fixture.runIdentifier,
                structuralReportData: fixture.structuralReportData,
                replayReportData: fixture.replayReportData,
                terminalReportData: fixture.terminalReportData
            )
        }

        let compactReceipt = try captureJSON(fixture.receiptObject)
        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: compactReceipt,
                receiptFileSHA256:
                    SecurityValidation.sha256Hex(compactReceipt),
                runIdentifier: fixture.runIdentifier
            )
        }

        var receipt = fixture.receiptObject
        var build = try #require(
            receipt["buildProvenance"] as? [String: Any]
        )
        var document = try #require(
            build["document"] as? [String: Any]
        )
        var source = try #require(
            document["source"] as? [String: Any]
        )
        source["exactTag"] = "/Users/private/result"
        document["source"] = source
        build["document"] = document
        receipt["buildProvenance"] = build
        let pathReceipt = try captureJSON(receipt, prettyPrinted: true)
        expectFailure {
            _ = try BenchmarkStore.validatedPortfolioCaptureSnapshot(
                result: fixture.result,
                resultFileSHA256: fixture.resultFileSHA256,
                receiptData: pathReceipt,
                receiptFileSHA256:
                    SecurityValidation.sha256Hex(pathReceipt),
                runIdentifier: fixture.runIdentifier
            )
        }
    }

    @Test
    @MainActor
    func testPortfolioReadinessIsCanonicalAtomicPrivateAndExclusive()
        throws
    {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-portfolio-ready-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: temporary,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporary) }
        let readyFile = temporary.appendingPathComponent("ready.json")
        let runIdentifier = "123e4567-e89b-42d3-a456-426614174000"
        let resultDigest = String(repeating: "a", count: 64)
        let receiptDigest = String(repeating: "b", count: 64)
        let executableDigest = String(repeating: "c", count: 64)

        try BenchmarkStore.writePortfolioCaptureReadiness(
            at: readyFile,
            runIdentifier: runIdentifier,
            resultFileSHA256: resultDigest,
            receiptFileSHA256: receiptDigest,
            applicationExecutableSHA256: executableDigest,
            metricVerdict: "PASS",
            compressionRatioVsBF16: 2.052383755768127,
            deltaNLLNatPerToken: -8.493661880493164e-06,
            top1Agreement: 0.9951171875
        )

        let expected = Data(
            (
                "{\"application_executable_sha256\":\"\(executableDigest)\"," +
                "\"compression_ratio_vs_bf16\":\"2.052384\"," +
                "\"delta_nll_nat_per_token\":\"-0.000008\"," +
                "\"metric_verdict\":\"PASS\",\"module_states\":{" +
                "\"compression\":\"COMPLETE\"," +
                "\"heavy_replay\":\"PASS\",\"kv_cache\":\"COMPLETE\"," +
                "\"primary_evidence\":\"COMPLETE\"," +
                "\"qwen_model\":\"COMPLETE\"}," +
                "\"receipt_sha256\":\"\(receiptDigest)\"," +
                "\"result_sha256\":\"\(resultDigest)\"," +
                "\"run_identifier\":\"\(runIdentifier)\"," +
                "\"schema_version\":1," +
                "\"status\":\"CAPTURE_RESULT_READY\"," +
                "\"top1_agreement\":\"0.995117\"," +
                "\"verifier_state\":\"PASS\"}\n"
            ).utf8
        )
        let observed = try Data(contentsOf: readyFile)
        #expect(observed == expected)

        let object = try #require(
            JSONSerialization.jsonObject(with: observed) as? [String: Any]
        )
        #expect(object.count == 12)
        #expect(Set(object.keys) == [
            "application_executable_sha256",
            "compression_ratio_vs_bf16",
            "delta_nll_nat_per_token", "metric_verdict", "module_states",
            "receipt_sha256", "result_sha256", "run_identifier",
            "schema_version", "status", "top1_agreement",
            "verifier_state"
        ])
        #expect(object["status"] as? String == "CAPTURE_RESULT_READY")
        #expect(object["run_identifier"] as? String == runIdentifier)
        #expect(object["result_sha256"] as? String == resultDigest)
        #expect(object["receipt_sha256"] as? String == receiptDigest)
        #expect(
            object["application_executable_sha256"] as? String
                == executableDigest
        )
        #expect(object["metric_verdict"] as? String == "PASS")
        #expect(
            object["compression_ratio_vs_bf16"] as? String
                == "2.052384"
        )
        #expect(
            object["delta_nll_nat_per_token"] as? String
                == "-0.000008"
        )
        #expect(object["top1_agreement"] as? String == "0.995117")
        #expect(object["verifier_state"] as? String == "PASS")
        #expect(
            object["module_states"] as? [String: String] == [
                "compression": "COMPLETE",
                "heavy_replay": "PASS",
                "kv_cache": "COMPLETE",
                "primary_evidence": "COMPLETE",
                "qwen_model": "COMPLETE"
            ]
        )

        var status = stat()
        #expect(readyFile.path.withCString { lstat($0, &status) } == 0)
        #expect((status.st_mode & S_IFMT) == S_IFREG)
        #expect((status.st_mode & mode_t(0o7777)) == mode_t(0o600))
        #expect(status.st_uid == getuid())
        #expect(status.st_nlink == 1)

        expectFailure {
            try BenchmarkStore.writePortfolioCaptureReadiness(
                at: readyFile,
                runIdentifier: runIdentifier,
                resultFileSHA256: resultDigest,
                receiptFileSHA256: receiptDigest,
                applicationExecutableSHA256: executableDigest,
                metricVerdict: "PASS",
                compressionRatioVsBF16: 2.052383755768127,
                deltaNLLNatPerToken: -8.493661880493164e-06,
                top1Agreement: 0.9951171875
            )
        }
        #expect(try Data(contentsOf: readyFile) == expected)
        let temporaryFiles = try FileManager.default.contentsOfDirectory(
            atPath: temporary.path
        )
        #expect(temporaryFiles == ["ready.json"])
    }

    @Test
    @MainActor
    func testPortfolioReadinessRejectsUnsafePathsAndBindingsWithoutWriting()
        throws
    {
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "corelm-portfolio-ready-negative-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: temporary,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        defer { try? FileManager.default.removeItem(at: temporary) }
        let secure = temporary.appendingPathComponent(
            "secure", isDirectory: true
        )
        let publicDirectory = temporary.appendingPathComponent(
            "public", isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: secure,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        try FileManager.default.createDirectory(
            at: publicDirectory,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o755]
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: publicDirectory.path
        )
        let linked = temporary.appendingPathComponent(
            "linked", isDirectory: true
        )
        try FileManager.default.createSymbolicLink(
            at: linked,
            withDestinationURL: secure
        )

        let runIdentifier = "123e4567-e89b-42d3-a456-426614174000"
        let digest = String(repeating: "d", count: 64)
        func attempt(_ target: URL, digest value: String = digest) {
            expectFailure {
                try BenchmarkStore.writePortfolioCaptureReadiness(
                    at: target,
                    runIdentifier: runIdentifier,
                    resultFileSHA256: value,
                    receiptFileSHA256: digest,
                    applicationExecutableSHA256: digest,
                    metricVerdict: "PASS",
                    compressionRatioVsBF16: 2.0,
                    deltaNLLNatPerToken: 0.0,
                    top1Agreement: 1.0
                )
            }
        }

        let publicTarget = publicDirectory.appendingPathComponent("ready.json")
        attempt(publicTarget)
        #expect(!FileManager.default.fileExists(atPath: publicTarget.path))

        let linkedTarget = linked.appendingPathComponent("ready.json")
        attempt(linkedTarget)
        #expect(!FileManager.default.fileExists(atPath: linkedTarget.path))

        let malformedTarget = secure.appendingPathComponent("malformed.json")
        attempt(malformedTarget, digest: "D" + String(repeating: "d", count: 63))
        #expect(!FileManager.default.fileExists(atPath: malformedTarget.path))

        let invalidMetricTarget = secure.appendingPathComponent("metric.json")
        expectFailure {
            try BenchmarkStore.writePortfolioCaptureReadiness(
                at: invalidMetricTarget,
                runIdentifier: runIdentifier,
                resultFileSHA256: digest,
                receiptFileSHA256: digest,
                applicationExecutableSHA256: digest,
                metricVerdict: "PASS",
                compressionRatioVsBF16: .nan,
                deltaNLLNatPerToken: 0.0,
                top1Agreement: 1.0
            )
        }
        #expect(
            !FileManager.default.fileExists(atPath: invalidMetricTarget.path)
        )

        let existing = secure.appendingPathComponent("existing.json")
        try Data("do-not-replace\n".utf8).write(to: existing)
        attempt(existing)
        #expect(try Data(contentsOf: existing) == Data("do-not-replace\n".utf8))

        let symlinkTarget = secure.appendingPathComponent("symlink.json")
        try FileManager.default.createSymbolicLink(
            at: symlinkTarget,
            withDestinationURL: existing
        )
        attempt(symlinkTarget)
        #expect(try Data(contentsOf: existing) == Data("do-not-replace\n".utf8))
        #expect(
            try FileManager.default.destinationOfSymbolicLink(
                atPath: symlinkTarget.path
            ) == existing.path
        )
    }

}
