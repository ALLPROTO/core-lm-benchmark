import Foundation

struct RealLLMRunSettings {
    var validationStartBlock = 64
    var validationBlocks = 8
    let candidateIndex = 32
}

enum CompressionProofRunPolicy {
    static let registeredStartBlock = 64
    static let registeredBlockCount = 8
    static let registeredEndBlock =
        registeredStartBlock + registeredBlockCount - 1

    #if DEBUG
    static let allowsDevelopmentOverrides = true
    #else
    static let allowsDevelopmentOverrides = false
    #endif

    static func effectiveSettings(
        requested: RealLLMRunSettings,
        allowsDevelopmentOverrides: Bool = allowsDevelopmentOverrides
    ) -> RealLLMRunSettings {
        guard allowsDevelopmentOverrides else {
            return RealLLMRunSettings(
                validationStartBlock: registeredStartBlock,
                validationBlocks: registeredBlockCount
            )
        }
        return requested
    }
}

struct RealLLMProtocolSummary: Codable {
    let modelRepository: String
    let modelRevision: String
    let modelWeightsSHA256: String
    let datasetRepository: String
    let datasetRevision: String
    let split: String
    let validationStartBlock: Int
    let validationBlocks: Int
    let evaluatedCandidateIndices: [Int]
}

struct RealLLMEnvironmentSummary: Codable {
    let python: String
    let platform: String
    let machine: String
    let device: String
    let torch: String
    let transformers: String
    let numpy: String
    let pyarrow: String
    let hfHome: String?
}

struct RealLLMConfiguration: Codable {
    let backend: String
    let bitsByLayer: [Int]?
    let groupSize: Int
    let transformBlockSize: Int
    let scaleCompression: String
    let codeCompression: String
    let signMode: String
    let schedule: String?
}

struct RealLLMGates: Codable {
    let compression: Bool
    let deltaNLL: Bool
    let top1Agreement: Bool
}

struct RealLLMAggregate: Codable {
    let configuration: RealLLMConfiguration
    let configurationId: String
    let blocks: Int
    let predictionTokens: Int
    let denseBF16Bytes: Int
    let encodedFileBytes: Int
    let compressionRatioVsBF16: Double
    let baselineNLLNatPerToken: Double
    let candidateNLLNatPerToken: Double
    let deltaNLLNatPerToken: Double
    let perplexityRatio: Double
    let top1Agreement: Double
    let meanKLDivergenceNat: Double
    let cacheNormalizedRMSE: Double
    let cacheCosineSimilarity: Double
    let cacheMaximumAbsoluteError: Double
    let allPayloadDigestsUnique: Bool
    let gates: RealLLMGates
    let pass: Bool
}

struct RealLLMContainerMetadata: Codable {
    let bits: Int?
    let bitsByColumnGroup: [Int]?
    let codeCompression: String
    let codeCount: Int
    let codeMapping: String
    let dtype: String
    let format: String
    let groupSize: Int
    let groupsPerRow: Int
    let inputSha256: String
    let layerIndex: Int
    let packedBytes: Int
    let packedBytesByColumnGroup: [Int]?
    let packing: String
    let payloadBytes: Int
    let payloadSha256: String
    let quantization: String
    let reconstructionSha256: String
    let scaleBytes: Int
    let scaleCompression: String
    let scaleCount: Int
    let scaleDtype: String
    let shape: [Int]
    let signDerivation: String
    let signMode: String
    let storedCodeBytes: Int
    let storedScaleBytes: Int
    let transform: String
    let transformBlockSize: Int
}

struct RealLLMContainerManifestEntry: Codable {
    let layerIndex: Int
    let metadata: RealLLMContainerMetadata
    let payloadBytes: Int
    let containerBytes: Int
    let containerSHA256: String
}

struct RealLLMPrimaryEvidenceReference: Codable {
    let schemaVersion: String
    let path: String
    let manifestSHA256: String
    let manifestBytes: Int
    let containerCount: Int
    let containerBytes: Int
    let blocks: Int
    let predictionTokens: Int
}

struct RealLLMPrimaryContainerArtifact: Codable {
    let blockIndex: Int
    let layerIndex: Int
    let path: String
    let bytes: Int
    let sha256: String
}

struct RealLLMTokenMetricsReference: Codable {
    let path: String
    let bytes: Int
    let sha256: String
    let blocks: Int
    let predictionTokens: Int
}

struct RealLLMPrimaryEvidenceManifest: Codable {
    let schemaVersion: String
    let resultFile: String
    let containers: [RealLLMPrimaryContainerArtifact]
    let tokenMetrics: RealLLMTokenMetricsReference
}

struct RealLLMTokenMetric: Codable {
    let offset: Int
    let targetTokenId: Int
    let baselineLossNat: Double
    let candidateLossNat: Double
    let baselineTop1TokenId: Int
    let candidateTop1TokenId: Int
    let top1Agrees: Bool
}

struct RealLLMTokenMetricBlock: Codable {
    let blockIndex: Int
    let tokenIds: [Int]
    let predictionTokens: Int
    let tokens: [RealLLMTokenMetric]
}

struct RealLLMTokenMetricsDocument: Codable {
    let schemaVersion: String
    let blocks: [RealLLMTokenMetricBlock]
}

struct RealLLMRecord: Codable {
    let blockIndex: Int
    let configurationId: String
    let predictionTokens: Int
    let denseBF16Bytes: Int
    let payloadBytes: Int
    let encodedFileBytes: Int
    let baselineNLLNatPerToken: Double
    let candidateNLLNatPerToken: Double
    let deltaNLLNatPerToken: Double
    let perplexityRatio: Double
    let meanKLDivergenceNat: Double
    let top1Agreement: Double
    let top1AgreementCount: Int
    let tokenIdsSHA256: String
    let canonicalCacheBF16SHA256: String
    let payloadSHA256: String
    let containerManifest: [RealLLMContainerManifestEntry]
    let containerManifestSHA256: String
    let cacheReferenceSumSquares: Double
    let cacheCandidateSumSquares: Double
    let cacheDotProduct: Double
    let cacheDifferenceSumSquares: Double
    let cacheMaximumAbsoluteError: Double
}

struct RealLLMBaseline: Codable {
    let blockIndex: Int
    let predictionTokens: Int
    let denseBF16Bytes: Int
    let layers: Int
    let kvHeads: Int
    let headDimension: Int
    let trajectoryShapePerLayer: [Int]
    let tokenIdsSHA256: String
    let canonicalCacheBF16SHA256: String
    let canonicalBF16NLLNatPerToken: Double
    let nativeBF16Top1Agreement: Double
    let exactRebuildMaxAbsLogitDifference: Double
    let exactRebuildTop1Identical: Bool
    let layoutRebuildMaxAbsLogitDifference: Double
    let layoutRebuildTop1Identical: Bool
}

struct RealLLMResult: Codable {
    let schemaVersion: String
    let status: String
    let createdAt: String
    let testDataOpened: Bool
    let protocolInfo: RealLLMProtocolSummary
    let environment: RealLLMEnvironmentSummary
    let selectedTokenIdsSHA256: String
    let baselines: [RealLLMBaseline]
    let records: [RealLLMRecord]
    let aggregates: [RealLLMAggregate]
    let primaryEvidence: RealLLMPrimaryEvidenceReference?
    let resultSHA256: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case status
        case createdAt
        case testDataOpened
        case protocolInfo = "protocol"
        case environment
        case selectedTokenIdsSHA256
        case baselines
        case records
        case aggregates
        case primaryEvidence
        case resultSHA256
    }

    var aggregate: RealLLMAggregate? {
        aggregates.count == 1 ? aggregates[0] : nil
    }

    var verdict: Verdict {
        aggregate?.pass == true ? .pass : .fail
    }
}
