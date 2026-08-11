import SwiftUI

struct OperatorContentView: View {
    @EnvironmentObject private var store: OperatorStore

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Core LM Operator Control Center")
                    .font(.largeTitle.bold())
                Text(OperatorStore.classification)
                    .font(.headline.monospaced().bold())
                    .foregroundStyle(.orange)
                Text(
                    "Source-only controls for canonical repository commands. "
                    + "This window is not part of CoreLMBenchmark.app."
                )
                .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                Button("Verify Repository") {
                    store.start(.verifyRepository)
                }
                Button("Build App") {
                    store.start(.buildApp)
                }
                Button("Full System Proof") {
                    store.start(.fullSystemProof)
                }
                .buttonStyle(.borderedProminent)
                Divider().frame(height: 24)
                Button("Open Built App") {
                    store.start(.openBuiltApplication)
                }
                .disabled(
                    store.isRunning || !store.builtApplicationAvailable
                )
            }
            .disabled(store.isRunning)

            HStack(spacing: 12) {
                if store.isRunning {
                    ProgressView().controlSize(.small)
                }
                Text(store.statusMessage)
                    .font(.headline)
                Spacer()
            }

            Text(
                "Operator actions are serialized. Normal Quit safely terminates "
                + "the dedicated command process group, waits for bounded cleanup, "
                + "then closes this source-only Control Center."
            )
            .font(.caption)
            .foregroundStyle(.secondary)

            GroupBox("Sanitized bounded command output") {
                ScrollView([.horizontal, .vertical]) {
                    Text(store.logText)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                        .padding(8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(24)
        .frame(minWidth: 940, minHeight: 620)
        .onAppear {
            store.refreshBuiltApplicationAvailability()
        }
    }
}
