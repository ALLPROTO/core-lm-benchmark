import SwiftUI

@main
struct CoreLMBenchmarkApp: App {
    @StateObject private var store = BenchmarkStore()

    var body: some Scene {
        WindowGroup("Core LM Benchmark") {
            ContentView()
                .environmentObject(store)
                .frame(minWidth: 1120, minHeight: 720)
        }
        .commands {
            CommandGroup(after: .newItem) {
                Button("Open Benchmark Result…") { store.openResult() }
                    .keyboardShortcut("o")
            }
        }
    }
}
