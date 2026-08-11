import CoreFoundation
import Foundation

final class LiveProofTranscriptBuffer: @unchecked Sendable {
    private let limit: Int
    private let lock = NSLock()
    private var bytes = Data()
    private var truncated = false

    init(limit: Int = 2 * 1024 * 1024) {
        self.limit = limit
    }

    func append(_ data: Data) {
        guard !data.isEmpty else { return }
        lock.lock()
        defer { lock.unlock() }
        let remaining = max(0, limit - bytes.count)
        bytes.append(data.prefix(remaining))
        if data.count > remaining {
            truncated = true
        }
    }

    func snapshot() -> (data: Data, truncated: Bool) {
        lock.lock()
        defer { lock.unlock() }
        return (bytes, truncated)
    }
}

enum LiveProofStage: String {
    case idle = "IDLE"
    case runtime = "RUNTIME READY"
    case assets = "PINNED ASSETS VERIFIED"
    case modelLoading = "LOADING REAL QWEN"
    case modelReady = "QWEN LOADED ON MPS"
    case tokenSlice = "TOKEN SLICE SELECTED"
    case prefill = "PREFILL / KV CACHE"
    case codec = "VOIDTOKEN LAYER CODEC"
    case metrics = "BLOCK METRICS"
    case evidence = "PRIMARY EVIDENCE SEALED"
    case result = "RESULT SEALED"
    case complete = "WORKER COMPLETE"
    case invalid = "LIVE CHANNEL INVALID"

    var codeTopic: LiveCodeTopic {
        switch self {
        case .idle, .runtime, .assets, .modelLoading, .modelReady:
            .modelLoading
        case .tokenSlice:
            .tokenSelection
        case .prefill:
            .prefill
        case .codec:
            .codec
        case .metrics:
            .metrics
        case .evidence, .result, .complete, .invalid:
            .sealing
        }
    }
}

enum LiveCodeTopic: Hashable {
    case modelLoading
    case tokenSelection
    case prefill
    case codec
    case metrics
    case sealing
}

struct LiveCodeSnippet {
    let filename: String
    let sourceSHA256: String
    let firstLine: Int
    let lines: [String]

    var numberedText: String {
        lines.enumerated().map { offset, line in
            String(format: "%4d  %@", firstLine + offset, line)
        }.joined(separator: "\n")
    }
}

enum LiveCodeCatalog {
    private struct Specification {
        let topic: LiveCodeTopic
        let filename: String
        let anchor: String
        let linesBefore: Int
        let lineCount: Int
    }

    private static let specifications = [
        Specification(
            topic: .modelLoading,
            filename: "app_proof_runner.py",
            anchor: "model = AutoModelForCausalLM.from_pretrained(",
            linesBefore: 6,
            lineCount: 19
        ),
        Specification(
            topic: .tokenSelection,
            filename: "app_proof_runner.py",
            anchor: "blocks, token_digest = core._token_blocks(",
            linesBefore: 3,
            lineCount: 17
        ),
        Specification(
            topic: .prefill,
            filename: "app_proof_core.py",
            anchor: "prefill = model(prefix_ids, use_cache=True, return_dict=True)",
            linesBefore: 7,
            lineCount: 18
        ),
        Specification(
            topic: .codec,
            filename: "app_proof_core.py",
            anchor: "for (layer_index, layer) in enumerate(layers):",
            linesBefore: 5,
            lineCount: 22
        ),
        Specification(
            topic: .metrics,
            filename: "app_proof_runner.py",
            anchor: "baseline, candidates = core._evaluate_block(",
            linesBefore: 6,
            lineCount: 19
        ),
        Specification(
            topic: .sealing,
            filename: "app_proof_runner.py",
            anchor: "primary_evidence = primary_evidence_writer.finalize()",
            linesBefore: 5,
            lineCount: 20
        )
    ]

    static func load(projectDirectory: URL) throws
        -> [LiveCodeTopic: LiveCodeSnippet]
    {
        let root: URL
        if Bundle.main.bundleURL.pathExtension == "app" {
            guard let resources = Bundle.main.resourceURL else {
                throw SecurityValidationError.invalid(
                    "The signed application resources are unavailable."
                )
            }
            root = resources.appendingPathComponent(
                "RealLLM", isDirectory: true
            )
        } else {
            root = projectDirectory.appendingPathComponent(
                "RealLLM", isDirectory: true
            )
        }
        try SecurityValidation.validateDirectory(
            root, requireCurrentOwner: false
        )

        var result: [LiveCodeTopic: LiveCodeSnippet] = [:]
        for specification in specifications {
            let sourceURL = try SecurityValidation.validateRegularFileInside(
                root.appendingPathComponent(specification.filename),
                root: root
            )
            let data = try SecurityValidation.readRegularFile(
                at: sourceURL,
                maximumBytes: 1 * 1024 * 1024,
                requireCurrentOwner: false
            )
            guard let text = String(data: data, encoding: .utf8) else {
                throw SecurityValidationError.invalid(
                    "Live-code source is not valid UTF-8."
                )
            }
            let lines = text.split(
                separator: "\n", omittingEmptySubsequences: false
            ).map(String.init)
            let matches = lines.indices.filter {
                lines[$0].contains(specification.anchor)
            }
            guard matches.count == 1 else {
                throw SecurityValidationError.invalid(
                    "Live-code source anchor is missing or ambiguous."
                )
            }
            let start = max(0, matches[0] - specification.linesBefore)
            let end = min(lines.count, start + specification.lineCount)
            result[specification.topic] = LiveCodeSnippet(
                filename: specification.filename,
                sourceSHA256: SecurityValidation.sha256Hex(data),
                firstLine: start + 1,
                lines: Array(lines[start..<end])
            )
        }
        return result
    }
}

struct LiveLayerProgress: Identifiable {
    let blockIndex: Int
    let layerIndex: Int
    let bits: Int
    let containerBytes: Int
    let containerSHA256: String

    var id: String { "\(blockIndex):\(layerIndex)" }
}

struct LiveBlockProgress: Identifiable {
    let blockIndex: Int
    let denseBF16Bytes: Int
    let encodedFileBytes: Int
    let compressionRatioVsBF16: Double
    let deltaNLLNatPerToken: Double
    let top1Agreement: Double
    let predictionTokens: Int

    var id: Int { blockIndex }
}

struct LiveProofDisplayEvent: Identifiable {
    let sequence: Int
    let label: String
    let detail: String

    var id: Int { sequence }
}

private struct LiveProofEvent {
    static let schemaVersion = "corelm-live-proof-event-v1"
    static let producer = "app_worker"
    static let maximumBytes = 16 * 1024
    static let rootKeys: Set<String> = [
        "schema_version", "session_id", "sequence", "producer",
        "event", "facts", "previous_event_sha256"
    ]

    let sessionID: String
    let sequence: Int
    let event: String
    let facts: [String: Any]
    let previousEventSHA256: String
    let sha256: String

    static func parse(_ line: String) throws -> LiveProofEvent {
        let data = Data(line.utf8)
        let digest = try SecurityValidation.verifiedCanonicalJSONDigest(
            from: data, maximumBytes: maximumBytes
        )
        guard let object = try JSONSerialization.jsonObject(
            with: data, options: []
        ) as? [String: Any], Set(object.keys) == rootKeys else {
            throw invalid("Live event root shape is invalid.")
        }
        guard string(object["schema_version"], maximumBytes: 128)
                == schemaVersion,
              string(object["producer"], maximumBytes: 64) == producer,
              let sessionID = string(
                object["session_id"], maximumBytes: 64
              ),
              let uuid = UUID(uuidString: sessionID),
              uuid.uuidString.lowercased() == sessionID,
              uuid != UUID(
                  uuidString: "00000000-0000-0000-0000-000000000000"
              ),
              let event = string(object["event"], maximumBytes: 128),
              let sequence = integer(
                object["sequence"], minimum: 1, maximum: 10_000
              ),
              let previous = string(
                object["previous_event_sha256"], maximumBytes: 64
              ),
              SecurityValidation.isLowercaseSHA256(previous),
              let facts = object["facts"] as? [String: Any]
        else {
            throw invalid("Live event metadata is invalid.")
        }
        return LiveProofEvent(
            sessionID: sessionID,
            sequence: sequence,
            event: event,
            facts: facts,
            previousEventSHA256: previous,
            sha256: digest
        )
    }

    func requireKeys(_ expected: Set<String>) throws {
        guard Set(facts.keys) == expected else {
            throw Self.invalid("Live event facts have an unexpected shape.")
        }
    }

    func factString(_ key: String, maximumBytes: Int = 512) throws -> String {
        guard let value = Self.string(
            facts[key], maximumBytes: maximumBytes
        ) else {
            throw Self.invalid("Live event string fact is invalid.")
        }
        return value
    }

    func factDigest(_ key: String) throws -> String {
        let value = try factString(key, maximumBytes: 64)
        guard SecurityValidation.isLowercaseSHA256(value) else {
            throw Self.invalid("Live event digest fact is invalid.")
        }
        return value
    }

    func factInteger(
        _ key: String, minimum: Int = 0, maximum: Int = Int.max
    ) throws -> Int {
        guard let value = Self.integer(
            facts[key], minimum: minimum, maximum: maximum
        ) else {
            throw Self.invalid("Live event integer fact is invalid.")
        }
        return value
    }

    func factDouble(
        _ key: String, minimum: Double, maximum: Double
    ) throws -> Double {
        guard let number = facts[key] as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(),
              number.doubleValue.isFinite,
              (minimum...maximum).contains(number.doubleValue)
        else {
            throw Self.invalid("Live event numeric fact is invalid.")
        }
        return number.doubleValue
    }

    func factBoolean(_ key: String) throws -> Bool {
        guard let number = facts[key] as? NSNumber,
              CFGetTypeID(number) == CFBooleanGetTypeID()
        else {
            throw Self.invalid("Live event Boolean fact is invalid.")
        }
        return number.boolValue
    }

    private static func string(
        _ value: Any?, maximumBytes: Int
    ) -> String? {
        guard let value = value as? String,
              !value.isEmpty,
              value.utf8.count <= maximumBytes,
              value.unicodeScalars.allSatisfy({
                  $0.value >= 0x20 && $0.value != 0x7F
              }) else {
            return nil
        }
        return value
    }

    private static func integer(
        _ value: Any?, minimum: Int, maximum: Int
    ) -> Int? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(),
              !CFNumberIsFloatType(number),
              number.doubleValue.isFinite,
              number.doubleValue.rounded() == number.doubleValue,
              number.doubleValue >= Double(minimum),
              number.doubleValue <= Double(maximum)
        else {
            return nil
        }
        return number.intValue
    }

    private static func invalid(_ message: String) -> SecurityValidationError {
        .invalid(message)
    }
}

struct LiveProofTelemetryState {
    private(set) var stage: LiveProofStage = .idle
    private(set) var statusMessage = "Waiting for a real-model run."
    private(set) var sessionID: String?
    private(set) var modelRepository: String?
    private(set) var modelRevision: String?
    private(set) var modelWeightsSHA256: String?
    private(set) var datasetRepository: String?
    private(set) var datasetRevision: String?
    private(set) var datasetSHA256: String?
    private(set) var device: String?
    private(set) var parameterCount: Int?
    private(set) var validationStartBlock: Int?
    private(set) var validationBlocks: Int?
    private(set) var tokensPerBlock: Int?
    private(set) var selectedTokenIDsSHA256: String?
    private(set) var currentBlockIndex: Int?
    private(set) var layers: [String: LiveLayerProgress] = [:]
    private(set) var blockMetrics: [Int: LiveBlockProgress] = [:]
    private(set) var manifestSHA256: String?
    private(set) var resultSHA256: String?
    private(set) var workerPassed: Bool?
    private(set) var swiftVerificationPassed = false
    private(set) var displayEvents: [LiveProofDisplayEvent] = []
    private(set) var invalidReason: String?

    private var runtimePython: String?
    private var runtimeTorch: String?
    private var runtimeTransformers: String?

    private var lastSequence = 0
    private var lastEventSHA256 = String(repeating: "0", count: 64)
    private var currentOrdinal = 0
    private var nextLayerIndex = 0
    private var evidenceReference:
        (containerCount: Int, containerBytes: Int, blocks: Int,
         predictionTokens: Int)?

    var isInvalid: Bool { invalidReason != nil }

    var completedLayerCount: Int { layers.count }

    var expectedLayerCount: Int {
        (validationBlocks ?? 0) * 24
    }

    var progress: Double {
        guard expectedLayerCount > 0 else { return 0 }
        return min(1, Double(completedLayerCount) / Double(expectedLayerCount))
    }

    var orderedLayersForCurrentBlock: [LiveLayerProgress] {
        guard let currentBlockIndex else { return [] }
        return layers.values.filter {
            $0.blockIndex == currentBlockIndex
        }.sorted { $0.layerIndex < $1.layerIndex }
    }

    var orderedBlockMetrics: [LiveBlockProgress] {
        blockMetrics.values.sorted { $0.blockIndex < $1.blockIndex }
    }

    mutating func reset(expectedSessionID: String) {
        self = LiveProofTelemetryState()
        sessionID = expectedSessionID
        statusMessage = "Starting the real Qwen worker…"
    }

    mutating func invalidate(_ message: String) {
        guard invalidReason == nil else { return }
        invalidReason = message
        stage = .invalid
        statusMessage = "Live channel rejected; proof verification continues separately."
    }

    mutating func apply(line: String, expectedSessionID: String) throws {
        guard !isInvalid else { return }
        let message = try LiveProofEvent.parse(line)
        guard message.sessionID == expectedSessionID,
              sessionID == expectedSessionID,
              message.sequence == lastSequence + 1,
              message.previousEventSHA256 == lastEventSHA256
        else {
            throw SecurityValidationError.invalid(
                "Live event session, sequence, or hash chain is invalid."
            )
        }

        switch message.event {
        case "runtime_ready":
            guard lastSequence == 0 else { throw orderError() }
            try message.requireKeys([
                "device", "python", "torch", "transformers"
            ])
            let observedDevice = try message.factString("device")
            guard observedDevice == "mps" else { throw orderError() }
            runtimePython = try message.factString("python")
            runtimeTorch = try message.factString("torch")
            runtimeTransformers = try message.factString("transformers")
            device = observedDevice
            stage = .runtime
            statusMessage = "Locked Python, Torch, and Transformers are running."
            record(message, label: "Runtime", detail: "Apple MPS runtime ready")

        case "assets_verified":
            guard lastSequence == 1 else { throw orderError() }
            try message.requireKeys([
                "model_repository", "model_revision", "model_weights_sha256",
                "dataset_repository", "dataset_revision", "dataset_sha256",
                "split"
            ])
            let repository = try message.factString("model_repository")
            let revision = try message.factString("model_revision")
            let weights = try message.factDigest("model_weights_sha256")
            let observedDatasetRepository = try message.factString(
                "dataset_repository"
            )
            let observedDatasetRevision = try message.factString(
                "dataset_revision"
            )
            let observedDatasetSHA256 = try message.factDigest(
                "dataset_sha256"
            )
            guard repository == "Qwen/Qwen2.5-0.5B",
                  revision
                    == "060db6499f32faf8b98477b0a26969ef7d8b9987",
                  weights
                    == "88c142557820ccad55bb59756bfcfcf891de9cc6202816bd346445188a0ed342",
                  observedDatasetRepository == "Salesforce/wikitext",
                  observedDatasetRevision
                    == "b08601e04326c79dfdd32d625aee71d232d685c3",
                  observedDatasetSHA256
                    == "204929b7ff9d6184953f867dedb860e40aa69c078fc1e54b3baaa8fb28511c4c",
                  (try message.factString("split")) == "validation"
            else {
                throw orderError()
            }
            modelRepository = repository
            modelRevision = revision
            modelWeightsSHA256 = weights
            datasetRepository = observedDatasetRepository
            datasetRevision = observedDatasetRevision
            datasetSHA256 = observedDatasetSHA256
            stage = .assets
            statusMessage = "Pinned model and WikiText bytes passed their digests."
            record(message, label: "Assets", detail: "Pinned Qwen + WikiText verified")

        case "model_load_started":
            guard lastSequence == 2 else { throw orderError() }
            try message.requireKeys([])
            stage = .modelLoading
            statusMessage = "Loading the real Qwen weights onto Apple MPS…"
            record(message, label: "Model", detail: "Loading Qwen weights")

        case "model_loaded_mps":
            guard lastSequence == 3 else { throw orderError() }
            try message.requireKeys([
                "model_repository", "model_revision", "device",
                "parameter_count"
            ])
            guard try message.factString("model_repository") == modelRepository,
                  try message.factString("model_revision") == modelRevision,
                  try message.factString("device") == "mps"
            else {
                throw orderError()
            }
            let observedParameterCount = try message.factInteger(
                "parameter_count", minimum: 1, maximum: 10_000_000_000
            )
            guard observedParameterCount == 494_032_768 else {
                throw orderError()
            }
            parameterCount = observedParameterCount
            stage = .modelReady
            statusMessage = "Real Qwen parameters are resident on MPS in eval mode."
            record(message, label: "Model", detail: "Qwen loaded on MPS")

        case "token_slice_selected_and_hashed":
            guard lastSequence == 4 else { throw orderError() }
            try message.requireKeys([
                "start_block", "blocks", "tokens_per_block",
                "selected_token_ids_sha256"
            ])
            validationStartBlock = try message.factInteger(
                "start_block", minimum: 64, maximum: 512
            )
            validationBlocks = try message.factInteger(
                "blocks", minimum: 1, maximum: 32
            )
            let observedTokensPerBlock = try message.factInteger(
                "tokens_per_block", minimum: 1, maximum: 4096
            )
            guard observedTokensPerBlock == 512 else {
                throw orderError()
            }
            tokensPerBlock = observedTokensPerBlock
            selectedTokenIDsSHA256 = try message.factDigest(
                "selected_token_ids_sha256"
            )
            stage = .tokenSlice
            statusMessage = "The public validation token slice was selected and hashed."
            record(message, label: "Tokens", detail: "Validation slice selected + hashed")

        case "block_started":
            guard validationBlocks != nil,
                  currentOrdinal < validationBlocks!,
                  nextLayerIndex == 0,
                  blockMetrics.count == currentOrdinal
            else {
                throw orderError()
            }
            try message.requireKeys([
                "block_index", "ordinal", "total"
            ])
            let ordinal = try message.factInteger(
                "ordinal", minimum: 1, maximum: 32
            )
            let total = try message.factInteger(
                "total", minimum: 1, maximum: 32
            )
            let block = try message.factInteger(
                "block_index", minimum: 64, maximum: 543
            )
            guard ordinal == currentOrdinal + 1,
                  total == validationBlocks,
                  block == validationStartBlock! + currentOrdinal
            else {
                throw orderError()
            }
            currentOrdinal = ordinal
            currentBlockIndex = block
            stage = .prefill
            statusMessage = "Block \(block): running Qwen prefill and extracting its KV cache."
            record(message, label: "Block \(block)", detail: "Prefill + KV cache started")

        case "codec_roundtrip_written":
            guard let currentBlockIndex,
                  currentOrdinal > 0,
                  nextLayerIndex < 24
            else {
                throw orderError()
            }
            try message.requireKeys([
                "block_index", "layer_index", "bits", "container_bytes",
                "container_sha256"
            ])
            let block = try message.factInteger(
                "block_index", minimum: 64, maximum: 543
            )
            let layer = try message.factInteger(
                "layer_index", minimum: 0, maximum: 23
            )
            guard block == currentBlockIndex,
                  layer == nextLayerIndex else {
                throw orderError()
            }
            let update = LiveLayerProgress(
                blockIndex: block,
                layerIndex: layer,
                bits: try message.factInteger(
                    "bits", minimum: 1, maximum: 16
                ),
                containerBytes: try message.factInteger(
                    "container_bytes", minimum: 1,
                    maximum: 256 * 1024 * 1024
                ),
                containerSHA256: try message.factDigest("container_sha256")
            )
            guard layers[update.id] == nil else { throw orderError() }
            layers[update.id] = update
            nextLayerIndex += 1
            stage = .codec
            statusMessage = "Block \(block): codec roundtrip wrote layer \(layer + 1)/24."
            if layer == 0 || layer == 7 || layer == 15 || layer == 23 {
                record(
                    message,
                    label: "Layer \(layer + 1)/24",
                    detail: "Block \(block) canonical container written"
                )
            }

        case "block_metrics_measured":
            guard let currentBlockIndex, nextLayerIndex == 24 else {
                throw orderError()
            }
            try message.requireKeys([
                "block_index", "dense_bf16_bytes", "encoded_file_bytes",
                "compression_ratio_vs_bf16", "delta_nll_nat_per_token",
                "top1_agreement", "prediction_tokens"
            ])
            let block = try message.factInteger(
                "block_index", minimum: 64, maximum: 543
            )
            guard block == currentBlockIndex,
                  blockMetrics[block] == nil else { throw orderError() }
            let metric = LiveBlockProgress(
                blockIndex: block,
                denseBF16Bytes: try message.factInteger(
                    "dense_bf16_bytes", minimum: 1, maximum: Int.max
                ),
                encodedFileBytes: try message.factInteger(
                    "encoded_file_bytes", minimum: 1, maximum: Int.max
                ),
                compressionRatioVsBF16: try message.factDouble(
                    "compression_ratio_vs_bf16", minimum: 0, maximum: 100
                ),
                deltaNLLNatPerToken: try message.factDouble(
                    "delta_nll_nat_per_token", minimum: -100, maximum: 100
                ),
                top1Agreement: try message.factDouble(
                    "top1_agreement", minimum: 0, maximum: 1
                ),
                predictionTokens: try message.factInteger(
                    "prediction_tokens", minimum: 1, maximum: 4096
                )
            )
            guard metric.predictionTokens == 128 else {
                throw orderError()
            }
            blockMetrics[block] = metric
            nextLayerIndex = 0
            stage = .metrics
            statusMessage = "Block \(block): 128 batched predictions measured."
            record(
                message,
                label: "Block \(block) metrics",
                detail: String(
                    format: "%.3f× · ΔNLL %+.6f · top-1 %.4f",
                    metric.compressionRatioVsBF16,
                    metric.deltaNLLNatPerToken,
                    metric.top1Agreement
                )
            )

        case "primary_evidence_sealed":
            guard let validationBlocks,
                  blockMetrics.count == validationBlocks,
                  layers.count == validationBlocks * 24,
                  nextLayerIndex == 0 else { throw orderError() }
            try message.requireKeys([
                "container_count", "container_bytes", "blocks",
                "prediction_tokens", "manifest_sha256"
            ])
            let reference = (
                containerCount: try message.factInteger(
                    "container_count", minimum: 1, maximum: 768
                ),
                containerBytes: try message.factInteger(
                    "container_bytes", minimum: 1, maximum: Int.max
                ),
                blocks: try message.factInteger(
                    "blocks", minimum: 1, maximum: 32
                ),
                predictionTokens: try message.factInteger(
                    "prediction_tokens", minimum: 1, maximum: 131_072
                )
            )
            guard reference.containerCount == validationBlocks * 24,
                  reference.blocks == validationBlocks,
                  reference.predictionTokens == validationBlocks * 128 else {
                throw orderError()
            }
            evidenceReference = reference
            manifestSHA256 = try message.factDigest("manifest_sha256")
            stage = .evidence
            statusMessage = "Primary containers and token metrics were sealed."
            record(message, label: "Evidence", detail: "Primary manifest sealed")

        case "result_sealed":
            guard evidenceReference != nil else { throw orderError() }
            try message.requireKeys(["result_sha256", "output_filename"])
            let filename = try message.factString("output_filename")
            guard let validationStartBlock, let validationBlocks,
                  filename == String(
                      format: "validation-%03d-%03d.json",
                      validationStartBlock,
                      validationStartBlock + validationBlocks - 1
                  ) else {
                throw orderError()
            }
            resultSHA256 = try message.factDigest("result_sha256")
            stage = .result
            statusMessage = "The canonical result JSON was sealed."
            record(message, label: "Result", detail: "Canonical result sealed")

        case "run_complete":
            guard resultSHA256 != nil else { throw orderError() }
            try message.requireKeys(["passed"])
            workerPassed = try message.factBoolean("passed")
            stage = .complete
            statusMessage = "Worker finished; Swift is verifying every retained byte."
            record(
                message,
                label: "Worker",
                detail: workerPassed == true ? "Metric gates PASS" : "Metric gates FAIL"
            )

        default:
            throw SecurityValidationError.invalid(
                "Live event type is not admitted."
            )
        }

        lastSequence = message.sequence
        lastEventSHA256 = message.sha256
    }

    mutating func reconcile(with result: RealLLMResult) throws {
        guard !isInvalid,
              stage == .complete,
              let validationBlocks,
              result.records.count == validationBlocks,
              result.protocolInfo.validationStartBlock == validationStartBlock,
              result.protocolInfo.validationBlocks == validationBlocks,
              result.protocolInfo.modelRepository == modelRepository,
              result.protocolInfo.modelRevision == modelRevision,
              result.protocolInfo.modelWeightsSHA256 == modelWeightsSHA256,
              result.protocolInfo.datasetRepository == datasetRepository,
              result.protocolInfo.datasetRevision == datasetRevision,
              result.protocolInfo.split == "validation",
              result.environment.device == device,
              result.environment.python == runtimePython,
              result.environment.torch == runtimeTorch,
              result.environment.transformers == runtimeTransformers,
              result.selectedTokenIdsSHA256 == selectedTokenIDsSHA256,
              result.resultSHA256 == resultSHA256,
              result.aggregate?.pass == workerPassed,
              result.primaryEvidence?.manifestSHA256 == manifestSHA256
        else {
            throw SecurityValidationError.invalid(
                "Live channel does not reconcile with the sealed result."
            )
        }
        for record in result.records {
            guard let live = blockMetrics[record.blockIndex],
                  live.denseBF16Bytes == record.denseBF16Bytes,
                  live.encodedFileBytes == record.encodedFileBytes,
                  live.predictionTokens == record.predictionTokens,
                  close(live.compressionRatioVsBF16,
                        Double(record.denseBF16Bytes) / Double(record.encodedFileBytes)),
                  close(live.deltaNLLNatPerToken,
                        record.deltaNLLNatPerToken),
                  close(live.top1Agreement, record.top1Agreement),
                  record.containerManifest.count == 24
            else {
                throw SecurityValidationError.invalid(
                    "Live block metrics differ from the sealed result."
                )
            }
            for container in record.containerManifest {
                let key = "\(record.blockIndex):\(container.layerIndex)"
                guard let layer = layers[key],
                      layer.containerBytes == container.containerBytes,
                      layer.containerSHA256 == container.containerSHA256,
                      (container.metadata.bits.map {
                          layer.bits == $0
                      } ?? true)
                else {
                    throw SecurityValidationError.invalid(
                        "Live layer bytes differ from primary evidence."
                    )
                }
            }
        }
        guard let reference = evidenceReference,
              let primary = result.primaryEvidence,
              reference.containerCount == primary.containerCount,
              reference.containerBytes == primary.containerBytes,
              reference.blocks == primary.blocks,
              reference.predictionTokens == primary.predictionTokens
        else {
            throw SecurityValidationError.invalid(
                "Live evidence totals differ from primary evidence."
            )
        }
        swiftVerificationPassed = true
        statusMessage = "Swift structural verification reconciled all live events."
    }

    private mutating func record(
        _ message: LiveProofEvent, label: String, detail: String
    ) {
        displayEvents.append(
            LiveProofDisplayEvent(
                sequence: message.sequence,
                label: label,
                detail: detail
            )
        )
        if displayEvents.count > 24 {
            displayEvents.removeFirst(displayEvents.count - 24)
        }
    }

    private func orderError() -> SecurityValidationError {
        .invalid("Live event is out of order or contradicts prior facts.")
    }

    private func close(_ left: Double, _ right: Double) -> Bool {
        left.isFinite && right.isFinite
            && abs(left - right)
                <= max(1e-12, 1e-12 * max(abs(left), abs(right)))
    }
}
