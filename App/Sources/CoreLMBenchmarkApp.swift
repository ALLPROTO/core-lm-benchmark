import AppKit
import SwiftUI

@MainActor
final class CoreLMBenchmarkAppDelegate: NSObject, NSApplicationDelegate {
    weak var store: BenchmarkStore?

    func applicationWillTerminate(_ notification: Notification) {
        store?.terminateForApplicationExit()
    }
}

@main
struct CoreLMBenchmarkApp: App {
    @StateObject private var store = BenchmarkStore()
    @NSApplicationDelegateAdaptor(CoreLMBenchmarkAppDelegate.self)
    private var appDelegate

    var body: some Scene {
        WindowGroup("Core LM Benchmark") {
            ContentView()
                .environmentObject(store)
                .frame(minWidth: 1120, minHeight: 720)
                .onAppear {
                    appDelegate.store = store
                }
        }
        .commands {
            CommandGroup(after: .newItem) {
                Button("Open Benchmark Result…") { store.openResult() }
                    .keyboardShortcut("o")
            }
        }
    }
}
