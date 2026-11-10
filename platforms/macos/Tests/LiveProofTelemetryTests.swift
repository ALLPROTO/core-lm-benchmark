import Foundation
import Testing
@testable import CoreLMBenchmarkApp

@Suite
struct LiveProofTelemetryTests {
    private struct EventBuilder {
        let sessionID: String
        var sequence = 0
        var previousSHA256 = String(repeating: "0", count: 64)

        mutating func line(
            _ event: String,
            facts: [String: Any]
        ) throws -> String {
            sequence += 1
            let object: [String: Any] = [
                "schema_version": "corelm-live-proof-event-v1",
                "session_id": sessionID,
                "sequence": sequence,
                "producer": "app_worker",
                "event": event,
                "facts": facts,
                "previous_event_sha256": previousSHA256
            ]
            let serialized = try JSONSerialization.data(
                withJSONObject: object,
                options: [.sortedKeys, .withoutEscapingSlashes]
            )
            let data = try SecurityValidation.canonicalizedJSONData(
                from: serialized, maximumBytes: 16 * 1024
            )
            previousSHA256 = SecurityValidation.sha256Hex(data)
            return try #require(String(data: data, encoding: .utf8))
        }
    }

    @Test
    func acceptsTheCrossLanguageCanonicalRuntimeVector() throws {
        let url = try #require(
            Bundle.module.url(
                forResource: "live-proof-event-v1-runtime",
                withExtension: "jsonl",
                subdirectory: "Fixtures"
            )
        )
        let bytes = try Data(contentsOf: url)
        #expect(
            SecurityValidation.sha256Hex(bytes)
                == "45305fd25c114e9d896846f72fdabe7af990de80af758d36ed42a93fb36a17d0"
        )
        #expect(bytes.last == 0x0A)
        let lineBytes = bytes.dropLast()
        #expect(
            SecurityValidation.sha256Hex(Data(lineBytes))
                == "4877fbdbe0c88632deec0074bfe86eef602f334400c92558f3a453ffe20ed00e"
        )
        let line = try #require(
            String(data: lineBytes, encoding: .utf8)
        )
        let sessionID = "12345678-1234-4abc-8123-123456789abc"
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)
        try state.apply(line: line, expectedSessionID: sessionID)
        #expect(state.stage == .runtime)
        #expect(state.device == "mps")
    }

    @Test
    func acceptsTheCrossLanguageCanonicalRealMetricVector() throws {
        let url = try #require(
            Bundle.module.url(
                forResource: "live-proof-event-v1-metric",
                withExtension: "jsonl",
                subdirectory: "Fixtures"
            )
        )
        let bytes = try Data(contentsOf: url)
        #expect(bytes.last == 0x0A)
        let lineBytes = Data(bytes.dropLast())
        #expect(
            try SecurityValidation.verifiedCanonicalJSONDigest(
                from: lineBytes, maximumBytes: 16 * 1024
            ) == "39794328c52603ab7134807b1b5813af4505305eb863447c95065363100960a2"
        )
    }

    @Test
    func reconcilesAFullTranscriptFromRetainedRealContainerRecords() throws {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("app-real-llm-evidence")
            .appendingPathComponent("validation-064-071.json")
        let fixtureData = try Data(contentsOf: fixtureURL)
        let retainedResult = try JSONDecoder().decode(
            RealLLMResult.self,
            from: fixtureData
        )
        var fixtureObject = try #require(
            JSONSerialization.jsonObject(with: fixtureData) as? [String: Any]
        )
        let containerBytes = retainedResult.records.reduce(0) {
            partial, record in
            partial + record.containerManifest.reduce(0) {
                $0 + $1.containerBytes
            }
        }
        let primaryProjection: [String: Any] = [
            "schemaVersion": "corelm-live-proof-test-primary-projection-v1",
            "containers": retainedResult.records.flatMap { record in
                record.containerManifest.map { container in
                    [
                        "blockIndex": record.blockIndex,
                        "layerIndex": container.layerIndex,
                        "bytes": container.containerBytes,
                        "sha256": container.containerSHA256
                    ] as [String: Any]
                }
            },
            "predictionTokens": retainedResult.records.reduce(0) {
                $0 + $1.predictionTokens
            }
        ]
        let primaryProjectionData = try SecurityValidation.canonicalizedJSONData(
            from: JSONSerialization.data(withJSONObject: primaryProjection),
            maximumBytes: 1024 * 1024
        )
        fixtureObject["primaryEvidence"] = [
            "schemaVersion": "corelm-live-proof-test-primary-projection-v1",
            "path": "test-fixture-primary-evidence/manifest.json",
            "manifestSHA256": SecurityValidation.sha256Hex(
                primaryProjectionData
            ),
            "manifestBytes": primaryProjectionData.count,
            "containerCount": retainedResult.records.count * 24,
            "containerBytes": containerBytes,
            "blocks": retainedResult.records.count,
            "predictionTokens": retainedResult.records.reduce(0) {
                $0 + $1.predictionTokens
            }
        ]
        fixtureObject.removeValue(forKey: "resultSHA256")
        let unsignedResult = try SecurityValidation.canonicalizedJSONData(
            from: JSONSerialization.data(withJSONObject: fixtureObject),
            maximumBytes: SecurityValidation.maximumRealLLMResultBytes
        )
        fixtureObject["resultSHA256"] = SecurityValidation.sha256Hex(
            unsignedResult
        )
        let coherentResultData = try SecurityValidation.canonicalizedJSONData(
            from: JSONSerialization.data(withJSONObject: fixtureObject),
            maximumBytes: SecurityValidation.maximumRealLLMResultBytes
        )
        let result = try JSONDecoder().decode(
            RealLLMResult.self,
            from: coherentResultData
        )
        #expect(
            try SecurityValidation.verifiedCanonicalResultDigest(
                from: coherentResultData
            ) == result.resultSHA256
        )
        let aggregate = try #require(result.aggregate)
        let bitsByLayer = try #require(
            aggregate.configuration.bitsByLayer
        )
        let primary = try #require(result.primaryEvidence)
        let sessionID = UUID().uuidString.lowercased()
        var builder = EventBuilder(sessionID: sessionID)
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)

        var lines = [
            try builder.line("runtime_ready", facts: [
                "device": result.environment.device,
                "python": result.environment.python,
                "torch": result.environment.torch,
                "transformers": result.environment.transformers
            ]),
            try builder.line("assets_verified", facts: [
                "model_repository": result.protocolInfo.modelRepository,
                "model_revision": result.protocolInfo.modelRevision,
                "model_weights_sha256": result.protocolInfo.modelWeightsSHA256,
                "dataset_repository": result.protocolInfo.datasetRepository,
                "dataset_revision": result.protocolInfo.datasetRevision,
                "dataset_sha256": "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
                "split": result.protocolInfo.split
            ]),
            try builder.line("model_load_started", facts: [:]),
            try builder.line("model_loaded_mps", facts: [
                "model_repository": result.protocolInfo.modelRepository,
                "model_revision": result.protocolInfo.modelRevision,
                "device": result.environment.device,
                "parameter_count": 494_032_768
            ]),
            try builder.line("token_slice_selected_and_hashed", facts: [
                "start_block": result.protocolInfo.validationStartBlock,
                "blocks": result.protocolInfo.validationBlocks,
                "tokens_per_block": 512,
                "selected_token_ids_sha256": result.selectedTokenIdsSHA256
            ])
        ]
        for (offset, record) in result.records.enumerated() {
            lines.append(
                try builder.line("block_started", facts: [
                    "block_index": record.blockIndex,
                    "ordinal": offset + 1,
                    "total": result.records.count
                ])
            )
            for container in record.containerManifest {
                lines.append(
                    try builder.line("codec_roundtrip_written", facts: [
                        "block_index": record.blockIndex,
                        "layer_index": container.layerIndex,
                        "bits": bitsByLayer[container.layerIndex],
                        "container_bytes": container.containerBytes,
                        "container_sha256": container.containerSHA256
                    ])
                )
            }
            lines.append(
                try builder.line("block_metrics_measured", facts: [
                    "block_index": record.blockIndex,
                    "dense_bf16_bytes": record.denseBF16Bytes,
                    "encoded_file_bytes": record.encodedFileBytes,
                    "compression_ratio_vs_bf16":
                        Double(record.denseBF16Bytes)
                            / Double(record.encodedFileBytes),
                    "delta_nll_nat_per_token": record.deltaNLLNatPerToken,
                    "top1_agreement": record.top1Agreement,
                    "prediction_tokens": record.predictionTokens
                ])
            )
        }
        lines.append(
            try builder.line("primary_evidence_sealed", facts: [
                "container_count": primary.containerCount,
                "container_bytes": primary.containerBytes,
                "blocks": primary.blocks,
                "prediction_tokens": primary.predictionTokens,
                "manifest_sha256": primary.manifestSHA256
            ])
        )
        let endBlock = result.protocolInfo.validationStartBlock
            + result.protocolInfo.validationBlocks - 1
        lines.append(
            try builder.line("result_sealed", facts: [
                "result_sha256": result.resultSHA256,
                "output_filename": String(
                    format: "validation-%03d-%03d.json",
                    result.protocolInfo.validationStartBlock,
                    endBlock
                )
            ])
        )
        lines.append(
            try builder.line(
                "run_complete", facts: ["passed": aggregate.pass]
            )
        )

        for line in lines {
            try state.apply(line: line, expectedSessionID: sessionID)
        }
        try state.reconcile(with: result)

        #expect(lines.count == 216)
        #expect(state.swiftVerificationPassed)
        #expect(state.workerPassed == aggregate.pass)
        #expect(state.completedLayerCount == 192)
    }

    @Test
    func acceptsOneCompleteHashChainedRealBlock() throws {
        let sessionID = UUID().uuidString.lowercased()
        var builder = EventBuilder(sessionID: sessionID)
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)

        var lines = [
            try builder.line("runtime_ready", facts: [
                "device": "mps",
                "python": "3.12.13",
                "torch": "2.13.0",
                "transformers": "5.14.1"
            ]),
            try builder.line("assets_verified", facts: [
                "model_repository": "Qwen/Qwen2.5-0.5B",
                "model_revision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
                "model_weights_sha256": "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
                "dataset_repository": "Salesforce/wikitext",
                "dataset_revision": "b08601e04326c79dfdd32d625aee71d232d685c3",
                "dataset_sha256": "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
                "split": "validation"
            ]),
            try builder.line("model_load_started", facts: [:]),
            try builder.line("model_loaded_mps", facts: [
                "model_repository": "Qwen/Qwen2.5-0.5B",
                "model_revision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
                "device": "mps",
                "parameter_count": 494_032_768
            ]),
            try builder.line("token_slice_selected_and_hashed", facts: [
                "start_block": 64,
                "blocks": 1,
                "tokens_per_block": 512,
                "selected_token_ids_sha256": String(repeating: "c", count: 64)
            ]),
            try builder.line("block_started", facts: [
                "block_index": 64,
                "ordinal": 1,
                "total": 1
            ])
        ]
        for layer in 0..<24 {
            lines.append(
                try builder.line("codec_roundtrip_written", facts: [
                    "block_index": 64,
                    "layer_index": layer,
                    "bits": 5,
                    "container_bytes": 1_000 + layer,
                    "container_sha256": String(
                        format: "%064x", layer + 1
                    )
                ])
            )
        }
        lines.append(
            try builder.line("block_metrics_measured", facts: [
                "block_index": 64,
                "dense_bf16_bytes": 64_000,
                "encoded_file_bytes": 32_000,
                "compression_ratio_vs_bf16": 2.0,
                "delta_nll_nat_per_token": -0.000_01,
                "top1_agreement": 1.0,
                "prediction_tokens": 128
            ])
        )
        lines.append(
            try builder.line("primary_evidence_sealed", facts: [
                "container_count": 24,
                "container_bytes": (0..<24).reduce(0) { $0 + 1_000 + $1 },
                "blocks": 1,
                "prediction_tokens": 128,
                "manifest_sha256": String(repeating: "d", count: 64)
            ])
        )
        lines.append(
            try builder.line("result_sealed", facts: [
                "result_sha256": String(repeating: "e", count: 64),
                "output_filename": "validation-064-064.json"
            ])
        )
        lines.append(
            try builder.line("run_complete", facts: ["passed": true])
        )

        for line in lines {
            try state.apply(line: line, expectedSessionID: sessionID)
        }

        #expect(state.stage == .complete)
        #expect(state.completedLayerCount == 24)
        #expect(state.expectedLayerCount == 24)
        #expect(state.orderedBlockMetrics.count == 1)
        #expect(state.workerPassed == true)
        #expect(!state.isInvalid)
    }

    @Test
    func rejectsNonCanonicalJSONBeforeUsingFacts() throws {
        let sessionID = UUID().uuidString.lowercased()
        var builder = EventBuilder(sessionID: sessionID)
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)
        let canonical = try builder.line("runtime_ready", facts: [
            "device": "mps",
            "python": "3.12.13",
            "torch": "2.13.0",
            "transformers": "5.14.1"
        ])
        let nonCanonical = canonical.replacingOccurrences(
            of: ":", with: ": ", options: [], range: canonical.range(of: ":")
        )

        #expect(throws: (any Error).self) {
            try state.apply(
                line: nonCanonical, expectedSessionID: sessionID
            )
        }
    }

    @Test
    func rejectsSequenceAndHashChainDiscontinuity() throws {
        let sessionID = UUID().uuidString.lowercased()
        var builder = EventBuilder(sessionID: sessionID)
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)
        let first = try builder.line("runtime_ready", facts: [
            "device": "mps",
            "python": "3.12.13",
            "torch": "2.13.0",
            "transformers": "5.14.1"
        ])
        try state.apply(line: first, expectedSessionID: sessionID)
        let firstSHA256 = builder.previousSHA256

        let second = try builder.line("assets_verified", facts: [
            "model_repository": "Qwen/Qwen2.5-0.5B",
            "model_revision": "060db6499f32faf8b98477b0a26969ef7d8b9987",
            "model_weights_sha256": "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
            "dataset_repository": "Salesforce/wikitext",
            "dataset_revision": "b08601e04326c79dfdd32d625aee71d232d685c3",
            "dataset_sha256": "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
            "split": "validation"
        ])
        let tampered = second.replacingOccurrences(
            of: firstSHA256,
            with: String(repeating: "f", count: 64)
        )
        #expect(throws: (any Error).self) {
            try state.apply(line: tampered, expectedSessionID: sessionID)
        }
    }

    @Test
    func rejectsOutOfOrderScientificClaims() throws {
        let sessionID = UUID().uuidString.lowercased()
        var builder = EventBuilder(sessionID: sessionID)
        var state = LiveProofTelemetryState()
        state.reset(expectedSessionID: sessionID)
        let first = try builder.line("runtime_ready", facts: [
            "device": "mps",
            "python": "3.12.13",
            "torch": "2.13.0",
            "transformers": "5.14.1"
        ])
        try state.apply(line: first, expectedSessionID: sessionID)
        let skipped = try builder.line("model_load_started", facts: [:])

        #expect(throws: (any Error).self) {
            try state.apply(line: skipped, expectedSessionID: sessionID)
        }
    }
}
