import Foundation

enum Verdict: String, Codable {
    case pass = "PASS"
    case fail = "FAIL"
    case inconclusive = "INCONCLUSIVE"
}

struct ThresholdConfiguration: Codable {
    let minimumCompressionRatio: Double
    let maximumNormalizedRMSE: Double
    let minimumCosineSimilarity: Double
    let maximumMeanEnergyRelativeDrift: Double

    enum CodingKeys: String, CodingKey {
        case minimumCompressionRatio = "minimum_compression_ratio"
        case maximumNormalizedRMSE = "maximum_normalized_rmse"
        case minimumCosineSimilarity = "minimum_cosine_similarity"
        case maximumMeanEnergyRelativeDrift = "maximum_mean_energy_relative_drift"
    }
}

struct RunConfiguration: Codable {
    let dimension: Int
    let steps: Int
    let seed: Int
    let inputScenario: String
    let inputBound: Double?
    let pcaComponents: Int?
    let topK: Int?
    let qmax: Int?
    let keyframeInterval: Int?
    let thresholds: ThresholdConfiguration?
}

struct MethodResult: Codable, Identifiable {
    var id: String { name }
    let name: String
    let payloadBytes: Int
    let fileBytes: Int
    let compressionRatio: Double
    let rmse: Double
    let normalizedRMSE: Double
    let cosineSimilarity: Double
    let maximumAbsoluteError: Double
    let trajectoryRMSE: Double?
    let meanEnergyRelativeDrift: Double?
    let csiRelativeDrift: Double?
    let energyDriftRelativeDifference: Double?
    let encodeNanoseconds: Int
    let decodeNanoseconds: Int
    let stepsPerSecond: Double
    let peakMemoryBytes: Int?
}

struct InvariantResult: Codable {
    let violations: Int
    let deterministicReplay: Bool
    let details: [String]
}

struct TimeSample: Codable, Identifiable {
    var id: Int { step }
    let step: Int
    let stateNorm: Double
    let energy: Double
    let csi: Double
    let energyDrift: Double
    let pcaRMSE: Double
    let voidTokenRMSE: Double
}

struct BenchmarkResult: Codable, Identifiable {
    var id: String { runId }
    let schemaVersion: String
    let runId: String
    let createdAt: String
    let configuration: RunConfiguration
    let inputDigest: String?
    let coreRuntimeNanoseconds: Int?
    let methods: [MethodResult]
    let timeSeries: [TimeSample]?
    let invariants: InvariantResult
    let verdict: Verdict
    let verdictReasons: [String]
}

struct RunSettings {
    var steps = 200
    var dimension = 96
    var seed = 42
    var scenario = "gaussian_bounded"
    var pcaComponents = 8
    var topK = 16
    var qmax = 127
    var keyframeInterval = 0
    var minimumCompressionRatio = 4.0
    var maximumNormalizedRMSE = 0.10
    var minimumCosineSimilarity = 0.95
    var maximumEnergyDrift = 0.05
}

enum ModuleState: String {
    case ready = "Ready"
    case running = "Running"
    case complete = "Complete"
}
