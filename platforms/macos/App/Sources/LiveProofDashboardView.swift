import SwiftUI

struct LiveProofDashboardView: View {
    @EnvironmentObject private var store: BenchmarkStore

    private let columns = Array(
        repeating: GridItem(.flexible(minimum: 34), spacing: 6),
        count: 12
    )

    var body: some View {
        let state = store.liveProofTelemetry
        VStack(alignment: .leading, spacing: 14) {
            Text(
                "LIVE REAL-MODEL TELEMETRY · PUBLIC VALIDATION REGRESSION · "
                    + "NOT PORTFOLIO EVIDENCE · NOT INDEPENDENT REPLICATION"
            )
            .font(.system(.caption, design: .monospaced).bold())
            .foregroundStyle(.orange)

            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(state.stage.rawValue)
                        .font(.title2.monospaced().bold())
                        .foregroundStyle(stageColor(state))
                    Text(state.statusMessage)
                        .foregroundStyle(.secondary)
                    Text(
                        "Hash-chained worker events are provisional until Swift "
                            + "reconciles them with the sealed result and containers. "
                            + "Missing, malformed, or reordered events are rejected."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                Spacer()
                modelBadge(state)
            }

            HStack(alignment: .top, spacing: 14) {
                processColumn(state)
                    .frame(minWidth: 360, maxWidth: .infinity)
                codeColumn
                    .frame(minWidth: 430, maxWidth: .infinity)
            }

            Text(
                "Manual repository Build, Verify, and Full System Proof controls: "
                    + "run ./corelm macos operator from a clean source checkout."
            )
            .font(.caption.monospaced())
            .foregroundStyle(.secondary)
        }
        .padding(16)
        .background(
            Color(nsColor: .controlBackgroundColor),
            in: RoundedRectangle(cornerRadius: 14)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(.orange.opacity(0.35), lineWidth: 1)
        }
    }

    @ViewBuilder
    private func modelBadge(_ state: LiveProofTelemetryState) -> some View {
        VStack(alignment: .trailing, spacing: 3) {
            Label(
                state.parameterCount == nil
                    ? "Pinned Qwen pending"
                    : state.swiftVerificationPassed
                        ? "Real Qwen run reconciled"
                        : "Worker reports Qwen loaded",
                systemImage: state.parameterCount == nil
                    ? "hourglass" : "brain.head.profile.fill"
            )
            .font(.headline)
            Text(state.modelRepository ?? "Qwen/Qwen2.5-0.5B")
                .font(.caption.monospaced())
            if let parameterCount = state.parameterCount {
                Text(
                    "\(parameterCount.formatted()) parameters · "
                        + "\((state.device ?? "mps").uppercased()) · eval mode"
                )
                .font(.caption.monospaced())
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
    }

    private func processColumn(
        _ state: LiveProofTelemetryState
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            GroupBox("Real KV-cache compression") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(
                            state.currentBlockIndex.map {
                                "Validation block \($0)"
                            } ?? "Waiting for first validation block"
                        )
                        .font(.headline)
                        Spacer()
                        Text(
                            state.expectedLayerCount == 0
                                ? "waiting for exact geometry"
                                : "\(state.completedLayerCount)/"
                                    + "\(state.expectedLayerCount) containers"
                        )
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                    }
                    LazyVGrid(columns: columns, spacing: 6) {
                        ForEach(0..<24, id: \.self) { layerIndex in
                            layerCell(
                                layerIndex,
                                completed: state.orderedLayersForCurrentBlock
                                    .contains { $0.layerIndex == layerIndex }
                            )
                        }
                    }
                    Text(
                        "Each filled layer is emitted after encode → serialize → parse "
                            + "and canonical write; Swift later re-reads and reconciles it."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                .padding(.top, 4)
            }

            GroupBox("Measured blocks — observations, not per-block verdicts") {
                VStack(alignment: .leading, spacing: 5) {
                    if state.orderedBlockMetrics.isEmpty {
                        Text("No completed block metrics yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(state.orderedBlockMetrics.suffix(8)) { metric in
                            HStack {
                                Text("B\(metric.blockIndex)")
                                    .font(.caption.monospaced().bold())
                                Spacer()
                                Text(
                                    String(
                                        format: "%.3f×  ΔNLL %+.6f  top-1 %.4f  %d predictions",
                                        metric.compressionRatioVsBF16,
                                        metric.deltaNLLNatPerToken,
                                        metric.top1Agreement,
                                        metric.predictionTokens
                                    )
                                )
                                .font(.caption.monospaced())
                            }
                        }
                    }
                }
                .padding(.top, 4)
            }

            GroupBox("Structured event trail") {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(state.displayEvents.suffix(8)) { event in
                        HStack(alignment: .firstTextBaseline) {
                            Text(String(format: "%03d", event.sequence))
                                .foregroundStyle(.secondary)
                            Text(event.label).bold()
                            Text(event.detail).foregroundStyle(.secondary)
                        }
                        .font(.caption.monospaced())
                    }
                    if state.displayEvents.isEmpty {
                        Text("Waiting for the first hash-chained worker event.")
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    private var codeColumn: some View {
        GroupBox("Verified code for the current confirmed stage") {
            if let snippet = store.currentLiveCodeSnippet {
                VStack(alignment: .leading, spacing: 7) {
                    HStack {
                        Text("RealLLM/\(snippet.filename)")
                            .font(.headline.monospaced())
                        Spacer()
                        Text("source SHA-256 \(snippet.sourceSHA256.prefix(16))…")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    ScrollView([.horizontal, .vertical]) {
                        Text(snippet.numberedText)
                            .font(.system(size: 11, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(minHeight: 310)
                    Text(
                        "Read-only excerpt from the verified worker source bundled "
                            + "with this app; highlighting follows confirmed events."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                .padding(.top, 4)
            } else if store.liveProofTelemetry.stage == .idle {
                ContentUnavailableView(
                    "Waiting for the first confirmed event",
                    systemImage: "hourglass",
                    description: Text(
                        "No source excerpt is selected before runtime_ready is accepted."
                    )
                )
                .frame(minHeight: 310)
            } else {
                ContentUnavailableView(
                    "Verified source unavailable",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text(
                        "The benchmark continues independently; no substitute code is shown."
                    )
                )
                .frame(minHeight: 310)
            }
        }
    }

    private func layerCell(_ index: Int, completed: Bool) -> some View {
        Text("L\(index)")
            .font(.caption2.monospaced().bold())
            .frame(maxWidth: .infinity, minHeight: 26)
            .background(
                completed ? Color.cyan.opacity(0.25) : Color.secondary.opacity(0.08),
                in: RoundedRectangle(cornerRadius: 5)
            )
            .foregroundStyle(completed ? .primary : .secondary)
    }

    private func stageColor(_ state: LiveProofTelemetryState) -> Color {
        if state.stage == .invalid || state.workerPassed == false {
            .red
        } else if state.swiftVerificationPassed && state.workerPassed == true {
            .green
        } else if state.stage == .idle {
            .secondary
        } else {
            .orange
        }
    }
}
