import Charts
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: BenchmarkStore
    private let architectureModules = [
        "Qwen2.5-0.5B", "Prefill", "KV Cache", "VoidToken Codec",
        "Cache Rebuild", "Continuation", "Metrics", "Verifier"
    ]

    var body: some View {
        NavigationSplitView {
            List {
                Section("Proof") {
                    Label("Compression Proof", systemImage: "checkmark.shield")
                }
                Section("Architecture") {
                    ForEach(architectureModules, id: \.self) { module in
                        HStack {
                            Circle().fill(statusColor).frame(width: 8, height: 8)
                            Text(module)
                            Spacer()
                            Text(currentModuleState.rawValue)
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Core LM")
        } detail: {
            VStack(spacing: 0) {
                RealLLMControlsView()
                Divider()
                RealLLMView()
                Divider()
                LogView()
            }
        }
        .onAppear { store.reloadLatestRealLLMResult() }
        .task { await store.automatedRunIfRequested() }
        .alert("Benchmark Error", isPresented: Binding(
            get: { store.errorMessage != nil },
            set: { if !$0 { store.errorMessage = nil } }
        )) {
            Button("OK") { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
    }

    private var currentModuleState: ModuleState {
        store.realLLMModuleState()
    }

    private var statusColor: Color {
        switch currentModuleState {
        case .ready: .secondary
        case .running: .orange
        case .complete: .green
        }
    }
}

struct RealLLMControlsView: View {
    @EnvironmentObject private var store: BenchmarkStore

    var body: some View {
        HStack(spacing: 16) {
            Label("Qwen2.5-0.5B", systemImage: "brain")
                .font(.headline)
            Text("VoidToken · frozen profile · Apple MPS")
                .foregroundStyle(.secondary)
            #if DEBUG
            Stepper(
                "Start \(store.realLLMSettings.validationStartBlock)",
                value: $store.realLLMSettings.validationStartBlock,
                in: 64...512,
                step: 8
            )
            Stepper(
                "Blocks \(store.realLLMSettings.validationBlocks)",
                value: $store.realLLMSettings.validationBlocks,
                in: 1...32
            )
            #else
            Text(
                "Validation blocks "
                    + "\(CompressionProofRunPolicy.registeredStartBlock)–"
                    + "\(CompressionProofRunPolicy.registeredEndBlock)"
            )
                .foregroundStyle(.secondary)
            #endif
            Spacer()
            Button("Show Result") { store.revealRealLLMResult() }
                .disabled(store.realLLMResultURL == nil)
            if store.isRunning {
                Button("Stop", role: .destructive) { store.stop() }
            } else {
                Button("Run Compression Proof") { store.runRealLLM() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .controlSize(.small)
        .padding()
    }
}

struct RealLLMView: View {
    @EnvironmentObject private var store: BenchmarkStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(
                    title: "Compression Proof",
                    verdict: store.realLLMResult?.verdict
                )
                Text(
                    "Pinned Qwen2.5-0.5B · real KV-cache replay · "
                        + "registered validation slice"
                )
                .foregroundStyle(.secondary)
                ProgressView(value: store.progress)

                if let result = store.realLLMResult,
                   let aggregate = result.aggregate {
                    let blockDomain = result.protocolInfo.validationStartBlock...(
                        result.protocolInfo.validationStartBlock
                            + result.protocolInfo.validationBlocks - 1
                    )
                    HStack(spacing: 12) {
                        MetricCard(
                            title: "Compression",
                            value: String(
                                format: "%.6f×",
                                aggregate.compressionRatioVsBF16
                            )
                        )
                        MetricCard(
                            title: "ΔNLL",
                            value: String(
                                format: "%+.9f",
                                aggregate.deltaNLLNatPerToken
                            )
                        )
                        MetricCard(
                            title: "Top-1 agreement",
                            value: String(
                                format: "%.4f%%",
                                aggregate.top1Agreement * 100
                            )
                        )
                        MetricCard(
                            title: "Mean KL",
                            value: String(
                                format: "%.7f",
                                aggregate.meanKLDivergenceNat
                            )
                        )
                    }
                    HStack(spacing: 12) {
                        MetricCard(
                            title: "Model / device",
                            value: "Qwen2.5 · \(result.environment.device.uppercased())"
                        )
                        MetricCard(
                            title: "Blocks / predictions",
                            value: "\(aggregate.blocks) / \(aggregate.predictionTokens)"
                        )
                        MetricCard(
                            title: "Stored bytes",
                            value: ByteCountFormatter.string(
                                fromByteCount: Int64(aggregate.encodedFileBytes),
                                countStyle: .memory
                            )
                        )
                        MetricCard(
                            title: "Verifier",
                            value: store.realLLMVerified ? "PASS" : "FAIL"
                        )
                    }

                    HStack(alignment: .top, spacing: 22) {
                        VStack(alignment: .leading, spacing: 9) {
                            Text("Scientific gates").font(.headline)
                            RealLLMGateRow(
                                title: "Compression ≥ 2×",
                                passed: aggregate.gates.compression
                            )
                            RealLLMGateRow(
                                title: "ΔNLL ≤ 0.01",
                                passed: aggregate.gates.deltaNLL
                            )
                            RealLLMGateRow(
                                title: "Top-1 ≥ 99%",
                                passed: aggregate.gates.top1Agreement
                            )
                            RealLLMGateRow(
                                title: "Exact structural replay",
                                passed: result.baselines.allSatisfy {
                                    $0.exactRebuildMaxAbsLogitDifference == 0
                                        && $0.layoutRebuildMaxAbsLogitDifference == 0
                                        && $0.exactRebuildTop1Identical
                                        && $0.layoutRebuildTop1Identical
                                }
                            )
                            RealLLMGateRow(
                                title: "Swift structural verification",
                                passed: store.realLLMVerified
                            )
                        }
                        .frame(width: 285, alignment: .leading)

                        Chart(result.records, id: \.blockIndex) { record in
                            LineMark(
                                x: .value("Block", record.blockIndex),
                                y: .value(
                                    "Top-1",
                                    record.top1Agreement * 100
                                )
                            )
                            .symbol(.circle)
                            RuleMark(y: .value("Gate", 99.0))
                                .foregroundStyle(.orange)
                                .lineStyle(StrokeStyle(dash: [5]))
                        }
                        .chartYAxisLabel("Top-1 agreement (%)")
                        .chartXScale(domain: blockDomain)
                        .chartYScale(domain: 98.0...100.05)
                        .frame(minHeight: 190)

                        Chart(result.records, id: \.blockIndex) { record in
                            BarMark(
                                x: .value("Block", record.blockIndex),
                                y: .value(
                                    "ΔNLL",
                                    record.deltaNLLNatPerToken
                                ),
                                width: .fixed(14)
                            )
                            .foregroundStyle(
                                record.deltaNLLNatPerToken <= 0.01
                                    ? .green : .red
                            )
                        }
                        .chartYAxisLabel("ΔNLL")
                        .chartXScale(domain: blockDomain)
                        .frame(minHeight: 190)
                    }

                    Text(store.realLLMVerificationMessage)
                        .font(.headline)
                        .foregroundStyle(
                            store.realLLMVerified ? .green : .red
                        )
                    Text("Result SHA-256: \(result.resultSHA256)")
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                    if let url = store.realLLMResultURL {
                        Text(url.path)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                } else if store.isRunning {
                    ContentUnavailableView(
                        "Compression proof is running",
                        systemImage: "cpu",
                        description: Text(
                            "The app is loading Qwen, rebuilding KV caches, "
                                + "and measuring each validation block."
                        )
                    )
                } else {
                    ContentUnavailableView(
                        "No proof run yet",
                        systemImage: "brain",
                        description: Text(
                            "Run the pinned Qwen2.5-0.5B compression proof on Apple MPS."
                        )
                    )
                }
            }
            .padding(24)
        }
    }
}

struct RealLLMGateRow: View {
    let title: String
    let passed: Bool

    var body: some View {
        Label(
            title,
            systemImage: passed
                ? "checkmark.circle.fill" : "xmark.circle.fill"
        )
        .foregroundStyle(passed ? .green : .red)
    }
}

struct LogView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        ScrollView {
            Text(store.log.suffix(8).joined(separator: "\n"))
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading).padding(10)
        }
        .frame(height: 90).background(.black.opacity(0.04))
    }
}

struct Header: View {
    let title: String
    let verdict: Verdict?
    var body: some View {
        HStack {
            Text(title).font(.largeTitle.bold())
            Spacer()
            VerdictBadge(verdict: verdict ?? .inconclusive)
        }
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.bold()).lineLimit(1)
        }
        .padding().frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct VerdictBadge: View {
    let verdict: Verdict
    var body: some View {
        Text(verdict.rawValue).font(.headline.monospaced().bold())
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(color.opacity(0.15), in: Capsule()).foregroundStyle(color)
    }
    private var color: Color {
        switch verdict {
        case .pass: .green
        case .fail: .red
        case .inconclusive: .orange
        }
    }
}
