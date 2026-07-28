import Charts
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: BenchmarkStore
    @State private var section = "Live Run"
    private let sections = [
        "Live Run", "Compression Comparison", "Stability and Invariants",
        "Saved Runs", "Evidence Report"
    ]

    var body: some View {
        NavigationSplitView {
            List(selection: $section) {
                Section("Views") {
                    ForEach(sections, id: \.self) { Text($0).tag($0) }
                }
                Section("Architecture") {
                    ForEach([
                        "Input Generator", "Core LM", "Dense", "PCA",
                        "VoidToken", "Metrics", "Invariants", "Reporter"
                    ], id: \.self) { module in
                        HStack {
                            Circle().fill(statusColor).frame(width: 8, height: 8)
                            Text(module)
                            Spacer()
                            Text(store.moduleState().rawValue)
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Core LM")
        } detail: {
            VStack(spacing: 0) {
                ControlsView()
                Divider()
                Group {
                    switch section {
                    case "Compression Comparison": ComparisonView()
                    case "Stability and Invariants": StabilityView()
                    case "Saved Runs": SavedRunsView()
                    case "Evidence Report": EvidenceView()
                    default: LiveRunView()
                    }
                }
                Divider()
                LogView()
            }
        }
        .onAppear { store.reloadSavedRuns() }
        .task { await store.smokeRunIfRequested() }
        .alert("Benchmark Error", isPresented: Binding(
            get: { store.errorMessage != nil },
            set: { if !$0 { store.errorMessage = nil } }
        )) {
            Button("OK") { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
    }

    private var statusColor: Color {
        switch store.moduleState() {
        case .ready: .secondary
        case .running: .orange
        case .complete: .green
        }
    }
}

struct ControlsView: View {
    @EnvironmentObject private var store: BenchmarkStore
    @State private var showThresholds = false

    var body: some View {
        HStack {
            Stepper("Steps \(store.settings.steps)", value: $store.settings.steps, in: 20...10000, step: 20)
            Stepper("n \(store.settings.dimension)", value: $store.settings.dimension, in: 8...1024, step: 8)
            Stepper("Seed \(store.settings.seed)", value: $store.settings.seed, in: 0...9999)
            Picker("Input", selection: $store.settings.scenario) {
                ForEach(store.scenarios, id: \.self) { Text($0).tag($0) }
            }
            .frame(width: 205)
            Stepper("PCA \(store.settings.pcaComponents)", value: $store.settings.pcaComponents, in: 1...store.settings.dimension)
            Stepper("top-k \(store.settings.topK)", value: $store.settings.topK, in: 1...store.settings.dimension)
            Picker("qmax", selection: $store.settings.qmax) {
                Text("127").tag(127)
                Text("32767").tag(32767)
            }
            .frame(width: 100)
            Stepper(
                "KF \(store.settings.keyframeInterval)",
                value: $store.settings.keyframeInterval,
                in: 0...256,
                step: 8
            )
            Button("Thresholds") { showThresholds.toggle() }
                .popover(isPresented: $showThresholds) {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("PASS Thresholds").font(.headline)
                        Stepper(
                            "Minimum ratio \(store.settings.minimumCompressionRatio, specifier: "%.1f")×",
                            value: $store.settings.minimumCompressionRatio,
                            in: 1...20, step: 0.5
                        )
                        Stepper(
                            "Maximum NRMSE \(store.settings.maximumNormalizedRMSE, specifier: "%.2f")",
                            value: $store.settings.maximumNormalizedRMSE,
                            in: 0...2, step: 0.01
                        )
                        Stepper(
                            "Minimum cosine \(store.settings.minimumCosineSimilarity, specifier: "%.2f")",
                            value: $store.settings.minimumCosineSimilarity,
                            in: 0...1, step: 0.01
                        )
                        Stepper(
                            "Maximum energy drift \(store.settings.maximumEnergyDrift, specifier: "%.2f")",
                            value: $store.settings.maximumEnergyDrift,
                            in: 0...2, step: 0.01
                        )
                    }
                    .padding()
                    .frame(width: 350)
                }
            Spacer()
            if store.isRunning {
                Button("Stop", role: .destructive) { store.stop() }
            } else {
                Button("Run") { store.run() }.buttonStyle(.borderedProminent)
            }
            Button("Repeat") { store.repeatRun() }
                .disabled(store.result == nil || store.isRunning)
        }
        .controlSize(.small)
        .padding()
    }
}

struct LiveRunView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Header(title: "Live Run", verdict: store.result?.verdict)
            ProgressView(value: store.progress)
            if let result = store.result {
                HStack(spacing: 16) {
                    MetricCard(title: "Run", value: result.runId)
                    MetricCard(title: "Input digest", value: String((result.inputDigest ?? "—").prefix(12)))
                    MetricCard(title: "Violations", value: "\(result.invariants.violations)")
                    MetricCard(title: "Replay", value: result.invariants.deterministicReplay ? "Exact" : "Failed")
                }
                if let samples = result.timeSeries {
                    Chart {
                        ForEach(samples) { sample in
                            LineMark(
                                x: .value("Step", sample.step),
                                y: .value("State norm", sample.stateNorm)
                            )
                            .foregroundStyle(by: .value("Signal", "State norm"))
                            LineMark(
                                x: .value("Step", sample.step),
                                y: .value("Energy", sample.energy)
                            )
                            .foregroundStyle(by: .value("Signal", "Energy"))
                        }
                    }
                    .frame(minHeight: 210)
                }
                MethodTable(methods: result.methods)
            } else {
                ContentUnavailableView("No completed run", systemImage: "waveform.path.ecg",
                                       description: Text("Run the benchmark or open a saved JSON result."))
            }
            Spacer()
        }.padding(24)
    }
}

struct ComparisonView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        VStack(alignment: .leading) {
            Header(title: "Compression Comparison", verdict: store.result?.verdict)
            if let methods = store.result?.methods {
                Chart(methods) { method in
                    BarMark(x: .value("Method", method.name),
                            y: .value("Compression ratio", method.compressionRatio))
                    .foregroundStyle(by: .value("Method", method.name))
                }
                .chartYAxisLabel("Dense / payload bytes")
                .frame(height: 210)
                Chart(methods) { method in
                    BarMark(x: .value("Method", method.name),
                            y: .value("Payload bytes", method.payloadBytes))
                    .foregroundStyle(by: .value("Method", method.name))
                }
                .chartYAxisLabel("Actual payload bytes")
                .frame(height: 180)
                MethodTable(methods: methods)
            } else {
                ContentUnavailableView("No data", systemImage: "chart.bar")
            }
            Spacer()
        }.padding(24)
    }
}

struct StabilityView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Header(title: "Stability and Invariants", verdict: store.result?.verdict)
            if let result = store.result {
                HStack {
                    MetricCard(title: "Violations", value: "\(result.invariants.violations)")
                    MetricCard(title: "Replay", value: result.invariants.deterministicReplay ? "PASS" : "FAIL")
                }
                Chart(result.methods) { method in
                    BarMark(x: .value("Method", method.name),
                            y: .value("Energy drift", method.meanEnergyRelativeDrift ?? 0))
                }
                .chartYAxisLabel("Mean relative energy drift")
                .frame(height: 180)
                if let samples = result.timeSeries {
                    Chart {
                        ForEach(samples) { sample in
                            LineMark(x: .value("Step", sample.step),
                                     y: .value("PCA RMSE", sample.pcaRMSE))
                                .foregroundStyle(by: .value("Error", "PCA"))
                            LineMark(x: .value("Step", sample.step),
                                     y: .value("VoidToken RMSE", sample.voidTokenRMSE))
                                .foregroundStyle(by: .value("Error", "VoidToken"))
                        }
                    }
                    .chartYAxisLabel("Reconstruction RMSE")
                    .frame(height: 180)
                    Chart(samples) { sample in
                        LineMark(x: .value("Step", sample.step),
                                 y: .value("CSI", sample.csi))
                            .foregroundStyle(.purple)
                    }
                    .chartYAxisLabel("CSI")
                    .frame(height: 140)
                }
                ForEach(result.invariants.details, id: \.self) { Text("• \($0)") }
            } else {
                ContentUnavailableView("No data", systemImage: "checkmark.shield")
            }
            Spacer()
        }.padding(24)
    }
}

struct SavedRunsView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        VStack(alignment: .leading) {
            HStack {
                Text("Saved Runs").font(.largeTitle.bold())
                Spacer()
                Button("Open JSON…") { store.openResult() }
                Button("Reload") { store.reloadSavedRuns() }
            }
            Table(store.savedRuns) {
                TableColumn("Run") { run in
                    Button(run.runId) { store.select(run) }.buttonStyle(.plain)
                }
                TableColumn("Scenario") { Text($0.configuration.inputScenario) }
                TableColumn("n") { Text("\($0.configuration.dimension)") }
                TableColumn("Steps") { Text("\($0.configuration.steps)") }
                TableColumn("Verdict") { VerdictBadge(verdict: $0.verdict) }
            }
        }.padding(24)
    }
}

struct EvidenceView: View {
    @EnvironmentObject private var store: BenchmarkStore
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Evidence Report").font(.largeTitle.bold())
                Spacer()
                Button("Export Markdown…") { store.saveMarkdownReport() }
                    .disabled(store.result == nil)
            }
            if let result = store.result {
                VerdictBadge(verdict: result.verdict)
                Text(result.verdictReasons.isEmpty
                     ? "All configured thresholds were satisfied."
                     : result.verdictReasons.joined(separator: "\n"))
                    .textSelection(.enabled)
                MethodTable(methods: result.methods)
            } else {
                ContentUnavailableView("No evidence loaded", systemImage: "doc.text.magnifyingglass")
            }
            Spacer()
        }.padding(24)
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

struct MethodTable: View {
    let methods: [MethodResult]
    var body: some View {
        Table(methods) {
            TableColumn("Method", value: \.name)
            TableColumn("Payload") { Text(ByteCountFormatter.string(fromByteCount: Int64($0.payloadBytes), countStyle: .memory)) }
            TableColumn("Ratio") { Text(String(format: "%.3f×", $0.compressionRatio)) }
            TableColumn("NRMSE") { Text(String(format: "%.5f", $0.normalizedRMSE)) }
            TableColumn("Cosine") { Text(String(format: "%.5f", $0.cosineSimilarity)) }
            TableColumn("Encode") { Text(String(format: "%.3f ms", Double($0.encodeNanoseconds) / 1_000_000)) }
            TableColumn("Decode") { Text(String(format: "%.3f ms", Double($0.decodeNanoseconds) / 1_000_000)) }
            TableColumn("Steps/s") { Text(String(format: "%.1f", $0.stepsPerSecond)) }
            TableColumn("Peak memory") {
                Text($0.peakMemoryBytes.map {
                    ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .memory)
                } ?? "n/a")
            }
        }.frame(minHeight: 180)
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
