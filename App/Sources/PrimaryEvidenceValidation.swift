import Foundation

extension BenchmarkStore {
    private func primaryEvidenceClose(_ left: Double, _ right: Double) -> Bool {
        left.isFinite && right.isFinite
            && abs(left - right)
                <= max(1e-12, 1e-12 * max(abs(left), abs(right)))
    }

    private func orderedBinary64Mean(_ values: [Double]) throws -> Double {
        guard !values.isEmpty else {
            throw SecurityValidationError.invalid(
                "A primary-evidence metric sequence is empty."
            )
        }
        var total = 0.0
        for value in values {
            guard value.isFinite && value >= 0 else {
                throw SecurityValidationError.invalid(
                    "A primary-evidence loss is invalid."
                )
            }
            total += value
            guard total.isFinite else {
                throw SecurityValidationError.invalid(
                    "A primary-evidence loss sum overflowed."
                )
            }
        }
        return total / Double(values.count)
    }

    private func littleEndianTokenData(_ tokenIds: [Int]) throws -> Data {
        var data = Data()
        data.reserveCapacity(tokenIds.count * 4)
        for tokenId in tokenIds {
            guard (0..<151_936).contains(tokenId) else {
                throw SecurityValidationError.invalid(
                    "A retained source token ID is outside the Qwen vocabulary."
                )
            }
            var value = UInt32(tokenId).littleEndian
            withUnsafeBytes(of: &value) { bytes in
                data.append(contentsOf: bytes)
            }
        }
        return data
    }

    func verifyPrimaryEvidence(
        _ result: RealLLMResult,
        outputURL: URL
    ) throws {
        guard result.schemaVersion
                == "corelm-voidtoken-v5-validation-development-v3",
              let reference = result.primaryEvidence,
              reference.schemaVersion
                == "corelm-real-llm-primary-evidence-v1",
              reference.path == "primary-evidence/manifest.json",
              SecurityValidation.isLowercaseSHA256(
                reference.manifestSHA256
              ),
              reference.containerCount == 192,
              reference.blocks == 8,
              reference.predictionTokens == 1_024,
              reference.manifestBytes > 0,
              reference.manifestBytes <= 512 * 1_024,
              reference.containerBytes > 0,
              reference.containerBytes <= 64 * 1_024 * 1_024
        else {
            throw SecurityValidationError.invalid(
                "The result lacks a bounded primary-evidence descriptor."
            )
        }

        let runDirectory = outputURL.deletingLastPathComponent()
        let primaryDirectory = runDirectory.appendingPathComponent(
            "primary-evidence", isDirectory: true
        )
        let containersDirectory = primaryDirectory.appendingPathComponent(
            "containers", isDirectory: true
        )
        try SecurityValidation.validateDirectory(
            primaryDirectory,
            requireCurrentOwner: true
        )
        try SecurityValidation.validateDirectory(
            containersDirectory,
            requireCurrentOwner: true
        )
        let manifestURL = primaryDirectory
            .appendingPathComponent("manifest.json")
        let manifestData = try SecurityValidation.readRegularFile(
            at: manifestURL,
            maximumBytes: 512 * 1_024
        )
        guard manifestData.count == reference.manifestBytes,
              SecurityValidation.sha256Hex(manifestData)
                == reference.manifestSHA256
        else {
            throw SecurityValidationError.invalid(
                "The primary-evidence manifest digest is inconsistent."
            )
        }
        let manifest = try JSONDecoder().decode(
            RealLLMPrimaryEvidenceManifest.self,
            from: manifestData
        )
        guard manifest.schemaVersion
                == "corelm-real-llm-primary-evidence-v1",
              manifest.resultFile == outputURL.lastPathComponent,
              manifest.containers.count == 192,
              manifest.tokenMetrics.path
                == "primary-evidence/token-metrics.json",
              manifest.tokenMetrics.blocks == 8,
              manifest.tokenMetrics.predictionTokens == 1_024,
              manifest.tokenMetrics.bytes > 0,
              manifest.tokenMetrics.bytes <= 2 * 1_024 * 1_024,
              SecurityValidation.isLowercaseSHA256(
                manifest.tokenMetrics.sha256
              )
        else {
            throw SecurityValidationError.invalid(
                "The primary-evidence manifest is inconsistent."
            )
        }

        var totalContainerBytes = 0
        for blockOffset in 0..<8 {
            let blockIndex = 64 + blockOffset
            try SecurityValidation.validateDirectory(
                containersDirectory.appendingPathComponent(
                    String(format: "block-%03d", blockIndex),
                    isDirectory: true
                ),
                requireCurrentOwner: true
            )
            let record = result.records[blockOffset]
            var framedContainers = Data()
            var blockPayloadBytes = 0
            var blockContainerBytes = 0
            for layerIndex in 0..<24 {
                let position = blockOffset * 24 + layerIndex
                let artifact = manifest.containers[position]
                let expectedPath = String(
                    format: "primary-evidence/containers/block-%03d/layer-%02d.vtl5",
                    blockIndex,
                    layerIndex
                )
                guard artifact.blockIndex == blockIndex,
                      artifact.layerIndex == layerIndex,
                      artifact.path == expectedPath,
                      artifact.bytes > 8,
                      artifact.bytes <= 8 * 1_024 * 1_024,
                      SecurityValidation.isLowercaseSHA256(artifact.sha256)
                else {
                    throw SecurityValidationError.invalid(
                        "A primary container path or bound is inconsistent."
                    )
                }
                let containerURL = runDirectory
                    .appendingPathComponent(expectedPath)
                let raw = try SecurityValidation.readRegularFile(
                    at: containerURL,
                    maximumBytes: 8 * 1_024 * 1_024
                )
                guard raw.count == artifact.bytes,
                      SecurityValidation.sha256Hex(raw) == artifact.sha256,
                      raw.prefix(4) == Data([0x56, 0x54, 0x4c, 0x35])
                else {
                    throw SecurityValidationError.invalid(
                        "A retained primary container digest is inconsistent."
                    )
                }
                let header = [UInt8](raw.prefix(8))
                let metadataLength = Int(header[4])
                    | (Int(header[5]) << 8)
                    | (Int(header[6]) << 16)
                    | (Int(header[7]) << 24)
                guard metadataLength > 0,
                      metadataLength <= 1_024 * 1_024,
                      8 + metadataLength < raw.count
                else {
                    throw SecurityValidationError.invalid(
                        "A retained primary container header is malformed."
                    )
                }
                let metadataData = raw.subdata(
                    in: 8..<(8 + metadataLength)
                )
                let metadata = try JSONDecoder().decode(
                    RealLLMContainerMetadata.self,
                    from: metadataData
                )
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
                let resultMetadata = record.containerManifest[layerIndex].metadata
                guard try encoder.encode(metadata) == metadataData,
                      try encoder.encode(metadata)
                        == encoder.encode(resultMetadata),
                      metadata.layerIndex == layerIndex,
                      metadata.payloadBytes
                        == raw.count - 8 - metadataLength,
                      metadata.payloadBytes
                        == record.containerManifest[layerIndex].payloadBytes,
                      raw.count
                        == record.containerManifest[layerIndex].containerBytes,
                      artifact.sha256
                        == record.containerManifest[layerIndex].containerSHA256
                else {
                    throw SecurityValidationError.invalid(
                        "A raw container differs from its result manifest."
                    )
                }
                let payload = raw.suffix(metadata.payloadBytes)
                guard SecurityValidation.sha256Hex(Data(payload))
                        == metadata.payloadSha256
                else {
                    throw SecurityValidationError.invalid(
                        "A raw container payload digest is inconsistent."
                    )
                }
                var layer = UInt32(layerIndex).littleEndian
                var length = UInt64(raw.count).littleEndian
                withUnsafeBytes(of: &layer) {
                    framedContainers.append(contentsOf: $0)
                }
                withUnsafeBytes(of: &length) {
                    framedContainers.append(contentsOf: $0)
                }
                framedContainers.append(raw)
                blockPayloadBytes = try SecurityValidation.checkedAdd(
                    blockPayloadBytes,
                    metadata.payloadBytes
                )
                blockContainerBytes = try SecurityValidation.checkedAdd(
                    blockContainerBytes,
                    raw.count
                )
                totalContainerBytes = try SecurityValidation.checkedAdd(
                    totalContainerBytes,
                    raw.count
                )
            }
            guard blockPayloadBytes == record.payloadBytes,
                  blockContainerBytes == record.encodedFileBytes,
                  SecurityValidation.sha256Hex(framedContainers)
                    == record.payloadSHA256
            else {
                throw SecurityValidationError.invalid(
                    "Raw container totals differ from the result record."
                )
            }
        }
        guard totalContainerBytes == reference.containerBytes else {
            throw SecurityValidationError.invalid(
                "Raw container bytes differ from the evidence descriptor."
            )
        }

        let tokenURL = runDirectory.appendingPathComponent(
            manifest.tokenMetrics.path
        )
        let tokenData = try SecurityValidation.readRegularFile(
            at: tokenURL,
            maximumBytes: 2 * 1_024 * 1_024
        )
        guard tokenData.count == manifest.tokenMetrics.bytes,
              SecurityValidation.sha256Hex(tokenData)
                == manifest.tokenMetrics.sha256
        else {
            throw SecurityValidationError.invalid(
                "The retained token metrics digest is inconsistent."
            )
        }
        let tokenDocument = try JSONDecoder().decode(
            RealLLMTokenMetricsDocument.self,
            from: tokenData
        )
        guard tokenDocument.schemaVersion
                == "corelm-real-llm-token-metrics-v1",
              tokenDocument.blocks.count == 8
        else {
            throw SecurityValidationError.invalid(
                "The retained token metrics schema is inconsistent."
            )
        }
        var selectedTokenData = Data()
        var blockBaselineMeans: [Double] = []
        var blockCandidateMeans: [Double] = []
        var totalAgreements = 0
        for blockOffset in 0..<8 {
            let blockIndex = 64 + blockOffset
            let block = tokenDocument.blocks[blockOffset]
            let record = result.records[blockOffset]
            guard block.blockIndex == blockIndex,
                  block.tokenIds.count == 512,
                  block.predictionTokens == 128,
                  block.tokens.count == 128
            else {
                throw SecurityValidationError.invalid(
                    "A retained token block has invalid dimensions."
                )
            }
            let blockTokenData = try littleEndianTokenData(block.tokenIds)
            selectedTokenData.append(blockTokenData)
            let blockDigest = SecurityValidation.sha256Hex(blockTokenData)
            guard blockDigest == record.tokenIdsSHA256,
                  blockDigest == result.baselines[blockOffset].tokenIdsSHA256
            else {
                throw SecurityValidationError.invalid(
                    "A retained source-token digest is inconsistent."
                )
            }
            var baselineLosses: [Double] = []
            var candidateLosses: [Double] = []
            var agreements = 0
            for offset in 0..<128 {
                let token = block.tokens[offset]
                let agrees = token.baselineTop1TokenId
                    == token.candidateTop1TokenId
                guard token.offset == offset,
                      token.targetTokenId == block.tokenIds[384 + offset],
                      (0..<151_936).contains(token.targetTokenId),
                      (0..<151_936).contains(token.baselineTop1TokenId),
                      (0..<151_936).contains(token.candidateTop1TokenId),
                      token.top1Agrees == agrees
                else {
                    throw SecurityValidationError.invalid(
                        "A retained token decision is inconsistent."
                    )
                }
                baselineLosses.append(token.baselineLossNat)
                candidateLosses.append(token.candidateLossNat)
                agreements += agrees ? 1 : 0
            }
            let baselineMean = try orderedBinary64Mean(baselineLosses)
            let candidateMean = try orderedBinary64Mean(candidateLosses)
            guard primaryEvidenceClose(
                    baselineMean,
                    record.baselineNLLNatPerToken
                  ),
                  primaryEvidenceClose(
                    candidateMean,
                    record.candidateNLLNatPerToken
                  ),
                  primaryEvidenceClose(
                    candidateMean - baselineMean,
                    record.deltaNLLNatPerToken
                  ),
                  agreements == record.top1AgreementCount,
                  primaryEvidenceClose(
                    Double(agreements) / 128,
                    record.top1Agreement
                  )
            else {
                throw SecurityValidationError.invalid(
                    "NLL or top-1 does not recompute from token evidence."
                )
            }
            blockBaselineMeans.append(baselineMean)
            blockCandidateMeans.append(candidateMean)
            totalAgreements += agreements
        }
        guard SecurityValidation.sha256Hex(selectedTokenData)
                == result.selectedTokenIdsSHA256,
              let aggregate = result.aggregate
        else {
            throw SecurityValidationError.invalid(
                "The selected source-token digest is inconsistent."
            )
        }
        let baselineNLL = try orderedBinary64Mean(blockBaselineMeans)
        let candidateNLL = try orderedBinary64Mean(blockCandidateMeans)
        let top1 = Double(totalAgreements) / 1_024
        guard primaryEvidenceClose(
                baselineNLL,
                aggregate.baselineNLLNatPerToken
              ),
              primaryEvidenceClose(
                candidateNLL,
                aggregate.candidateNLLNatPerToken
              ),
              primaryEvidenceClose(
                candidateNLL - baselineNLL,
                aggregate.deltaNLLNatPerToken
              ),
              primaryEvidenceClose(top1, aggregate.top1Agreement)
        else {
            throw SecurityValidationError.invalid(
                "Aggregate metrics do not recompute from token evidence."
            )
        }
    }
}
