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

        os.setpgid(0, 0)
        child = os.fork()
        if child == 0:
            def observe_term(_signum, _frame):
                with open(sys.argv[2], "w", encoding="ascii") as marker:
                    marker.write("SIGTERM ignored\\n")
                    marker.flush()
                    os.fsync(marker.fileno())

            signal.signal(signal.SIGTERM, observe_term)
            with open(sys.argv[1], "w", encoding="ascii") as marker:
                marker.write(str(os.getpid()) + "\\n")
                marker.flush()
                os.fsync(marker.fileno())
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

}
