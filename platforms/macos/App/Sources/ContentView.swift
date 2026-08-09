import Charts
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: BenchmarkStore
    private let architectureModules = [
        "Qwen2.5-0.5B", "Prefill", "KV Cache", "VoidToken Codec",
        "Cache Rebuild", "Continuation", "Metrics", "Verifier"
    ]

    var body: some View {
        if store.portfolioCaptureIsPresentation {
            PortfolioCaptureView()
        } else if store.portfolioCaptureRequested {
            PortfolioCaptureView()
                .task { await store.automatedRunIfRequested() }
        } else {
            benchmarkWorkspace
        }
    }

    private var benchmarkWorkspace: some View {
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

struct PortfolioCaptureView: View {
    @EnvironmentObject private var store: BenchmarkStore

    private let watermark =
        "AUTOMATED PRESENTATION · NOT MACHINE EVIDENCE · "
        + "PUBLIC VALIDATION REGRESSION · NOT INDEPENDENT REPLICATION"

    var body: some View {
        if store.portfolioCaptureIsPreflight {
            VStack(spacing: 24) {
                Text(watermark)
                    .font(.system(.headline, design: .monospaced).bold())
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                Text(store.portfolioCaptureStatusCode)
                    .font(.system(size: 34, weight: .bold, design: .rounded))
            }
            .padding(48)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))
        } else if store.portfolioCaptureIsPresentation {
            VStack(spacing: 24) {
                Text(watermark)
                    .font(.system(.headline, design: .monospaced).bold())
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                Text("POST-PROOF EXPLANATORY OVERVIEW")
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                Text("FIXED MODEL-FREE PRESENTATION · NOT TELEMETRY")
                    .font(.headline.monospaced())
                    .foregroundStyle(.secondary)
                PortfolioCaptureModuleStates(
                    moduleState: "COMPLETE",
                    heavyReplayState: "PASS",
                    verifierState: "PASS"
                )
            }
            .padding(48)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))
        } else {
            VStack(alignment: .leading, spacing: 22) {
                Text(watermark)
                    .font(.system(.headline, design: .monospaced).bold())
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                Divider()
                HStack {
                    Text("Core LM · automated capture")
                        .font(.largeTitle.bold())
                    Spacer()
                    Text(store.portfolioCaptureStatusCode)
                        .font(.headline.monospaced().bold())
                }
                if let snapshot = store.portfolioCaptureSnapshot {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            PortfolioCaptureMetric(
                                label: "Compression ratio vs BF16",
                                value: BenchmarkStore.portfolioMetricDecimal(
                                    snapshot.compressionRatioVsBF16
                                )
                            )
                            PortfolioCaptureMetric(
                                label: "Delta NLL nat/token",
                                value: BenchmarkStore.portfolioMetricDecimal(
                                    snapshot.deltaNLLNatPerToken
                                )
                            )
                            PortfolioCaptureMetric(
                                label: "Top-1 agreement",
                                value: BenchmarkStore.portfolioMetricDecimal(
                                    snapshot.top1Agreement
                                )
                            )
                        }
                        Grid(
                            alignment: .leading,
                            horizontalSpacing: 24,
                            verticalSpacing: 8
                        ) {
                            PortfolioCaptureFieldRow(
                                label: "Source tag",
                                value: snapshot.sourceTag
                            )
                            PortfolioCaptureFieldRow(
                                label: "Source commit",
                                value: snapshot.sourceCommit
                            )
                            PortfolioCaptureFieldRow(
                                label: "Source tree",
                                value: snapshot.sourceTree
                            )
                            PortfolioCaptureFieldRow(
                                label: "Challenge SHA-256",
                                value: snapshot.challengeSHA256
                            )
                            PortfolioCaptureFieldRow(
                                label: "Run UUID",
                                value: snapshot.runIdentifier
                            )
                            PortfolioCaptureFieldRow(
                                label: "Result SHA-256",
                                value: snapshot.resultFileSHA256
                            )
                            PortfolioCaptureFieldRow(
                                label: "Canonical result SHA-256",
                                value: snapshot.resultSHA256
                            )
                            PortfolioCaptureFieldRow(
                                label: "Receipt SHA-256",
                                value: snapshot.receiptFileSHA256
                            )
                            PortfolioCaptureFieldRow(
                                label: "Metric verdict",
                                value: snapshot.metricVerdict
                            )
                            PortfolioCaptureFieldRow(
                                label: "Structural verifier",
                                value: snapshot.structuralVerdict
                            )
                            PortfolioCaptureFieldRow(
                                label: "Replay outcome",
                                value: snapshot.replayVerdict
                            )
                            PortfolioCaptureFieldRow(
                                label: "Terminal outcome",
                                value: snapshot.terminalVerdict
                            )
                        }
                        PortfolioCaptureModuleStates(
                            moduleState: snapshot.moduleState,
                            heavyReplayState: snapshot.heavyReplayState,
                            verifierState: snapshot.verifierState
                        )
                    }
                    .padding(22)
                    .background(
                        .quaternary.opacity(0.45),
                        in: RoundedRectangle(cornerRadius: 14)
                    )
                    .task(id: snapshot.runIdentifier) {
                        await store
                            .publishPortfolioCaptureReadinessFromRenderedView()
                    }
                } else {
                    Spacer()
                    Text(store.portfolioCaptureStatusCode)
                        .font(.system(size: 30, weight: .bold, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .center)
                    Spacer()
                }
                Spacer(minLength: 0)
            }
            .padding(34)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))
        }
    }
}

private struct PortfolioCaptureMetric: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.monospaced().bold())
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            .quaternary.opacity(0.45),
            in: RoundedRectangle(cornerRadius: 10)
        )
    }
}

private struct PortfolioCaptureModuleStates: View {
    let moduleState: String
    let heavyReplayState: String
    let verifierState: String

    var body: some View {
        Grid(horizontalSpacing: 20, verticalSpacing: 7) {
            GridRow {
                PortfolioCaptureStage(label: "Qwen model", state: moduleState)
                PortfolioCaptureStage(label: "KV cache", state: moduleState)
                PortfolioCaptureStage(label: "Compression", state: moduleState)
            }
            GridRow {
                PortfolioCaptureStage(
                    label: "Primary evidence", state: moduleState
                )
                PortfolioCaptureStage(
                    label: "Heavy replay", state: heavyReplayState
                )
                PortfolioCaptureStage(
                    label: "Verifier", state: verifierState
                )
            }
        }
    }
}

private struct PortfolioCaptureStage: View {
    let label: String
    let state: String

    var body: some View {
        HStack {
            Text(label).font(.caption.bold())
            Spacer()
            Text(state).font(.caption.monospaced().bold())
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity)
        .background(
            .quaternary.opacity(0.35),
            in: RoundedRectangle(cornerRadius: 8)
        )
    }
}

private struct PortfolioCaptureFieldRow: View {
    let label: String
    let value: String

    var body: some View {
        GridRow {
            Text(label)
                .font(.headline)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(.body, design: .monospaced).weight(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.55)
                .textSelection(.disabled)
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
                            Text("Regression gates").font(.headline)
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
                    if let url = store.realLLMResultURL,
                       let label = BenchmarkStore.publicResultLabel(for: url) {
                        Text("Run: \(label)")
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
