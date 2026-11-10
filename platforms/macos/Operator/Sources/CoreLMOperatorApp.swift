import AppKit
import SwiftUI

@MainActor
final class OperatorAppDelegate: NSObject, NSApplicationDelegate {
    weak var store: OperatorStore?

    func applicationShouldTerminate(
        _ sender: NSApplication
    ) -> NSApplication.TerminateReply {
        guard store?.isRunning == true else {
            return .terminateNow
        }
        store?.beginApplicationTermination()
        return .terminateLater
    }
}

@main
@MainActor
struct CoreLMOperatorApp: App {
    @StateObject private var store: OperatorStore
    @NSApplicationDelegateAdaptor(OperatorAppDelegate.self)
    private var appDelegate

    init() {
        do {
            let configuration = try OperatorLaunchConfiguration(
                arguments: CommandLine.arguments
            )
            _store = StateObject(
                wrappedValue: OperatorStore(configuration: configuration)
            )
        } catch {
            let message = "CORE LM OPERATOR FAIL: \(error.localizedDescription)\n"
            FileHandle.standardError.write(Data(message.utf8))
            exit(EXIT_FAILURE)
        }
    }

    var body: some Scene {
        WindowGroup("Core LM Operator") {
            OperatorContentView()
                .environmentObject(store)
                .onAppear {
                    appDelegate.store = store
                }
        }
    }
}
