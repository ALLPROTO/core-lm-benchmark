import AppKit
import Foundation
import SwiftUI

@MainActor
final class OperatorStore: ObservableObject {
    static let classification =
        "MANUAL OPERATOR · NOT PORTFOLIO EVIDENCE · "
        + "NOT INDEPENDENT REPLICATION"

    @Published private(set) var state: OperatorState = .idle
    @Published private(set) var statusMessage = "Ready."
    @Published private(set) var logText = "No operator command has run."
    @Published private(set) var builtApplicationAvailable = false

    let project: OperatorProject
    private let configuration: OperatorLaunchConfiguration
    private let runner: OperatorCommandRunner
    private var commandHandle: OperatorCommandHandle?
    private var currentRunID: UUID?
    private var lastOutputSequence: UInt64 = 0
    private var terminationPending = false

    init(
        configuration: OperatorLaunchConfiguration,
        runner: OperatorCommandRunner = OperatorCommandRunner()
    ) {
        self.configuration = configuration
        project = configuration.project
        self.runner = runner
        refreshBuiltApplicationAvailability()
    }

    var isRunning: Bool {
        state.isRunning
    }

    func start(_ action: OperatorAction) {
        guard !isRunning else {
            reportPublicError("Another canonical operator action is still running.")
            return
        }
        if action == .openBuiltApplication {
            do {
                _ = try project.validatedBuiltApplication()
            } catch {
                refreshBuiltApplicationAvailability()
                reportPublicError(error.localizedDescription)
                return
            }
        }
        state = .running(action)
        statusMessage = action.runningDescription
        logText = ""
        lastOutputSequence = 0
        do {
            let handle = try runner.run(
                action: action,
                configuration: configuration,
                onOutput: { [weak self] snapshot in
                    Task { @MainActor [weak self] in
                        self?.apply(snapshot)
                    }
                },
                completion: { [weak self] result in
                    Task { @MainActor [weak self] in
                        self?.finish(action: action, result: result)
                    }
                }
            )
            commandHandle = handle
            currentRunID = handle.runID
        } catch {
            commandHandle = nil
            currentRunID = nil
            let publicError = sanitized(error.localizedDescription)
            state = .failed(action, publicError)
            statusMessage = publicError
        }
    }

    func refreshBuiltApplicationAvailability() {
        builtApplicationAvailable =
            (try? project.validatedBuiltApplication()) != nil
    }

    func beginApplicationTermination() {
        guard isRunning else {
            NSApplication.shared.reply(toApplicationShouldTerminate: true)
            return
        }
        terminationPending = true
        statusMessage =
            "Stopping the dedicated command process group before quitting."
        commandHandle?.cancel()
    }

    private func apply(_ snapshot: OperatorOutputSnapshot) {
        guard snapshot.runID == currentRunID,
              snapshot.sequence > lastOutputSequence else {
            return
        }
        lastOutputSequence = snapshot.sequence
        logText = snapshot.text
    }

    private func finish(
        action: OperatorAction,
        result: OperatorCommandResult
    ) {
        guard result.runID == currentRunID else { return }
        currentRunID = nil
        commandHandle = nil
        lastOutputSequence = max(lastOutputSequence, result.finalSequence)
        logText = result.output
        refreshBuiltApplicationAvailability()
        do {
            if let integrityError = result.integrityError {
                throw OperatorValidationError.invalid(integrityError)
            }
            var outcome = try OperatorTerminalClassifier.outcome(
                action: action,
                exitStatus: result.exitStatus,
                observation: result.terminalObservation,
                modelInventoryOutput: result.standardOutput,
                builtApplicationAvailable: builtApplicationAvailable
            )
            if action == .openBuiltApplication {
                let application = try project.validatedBuiltApplication()
                guard NSWorkspace.shared.open(application) else {
                    throw OperatorValidationError.invalid(
                        "macOS declined to open the canonical built application."
                    )
                }
                outcome = .applicationOpened
            }
            state = .succeeded(action, outcome)
            statusMessage = outcome.publicMessage
        } catch {
            let publicError = sanitized(error.localizedDescription)
            state = .failed(action, publicError)
            statusMessage = publicError
        }
        if terminationPending {
            terminationPending = false
            NSApplication.shared.reply(toApplicationShouldTerminate: true)
        }
    }

    private func reportPublicError(_ message: String) {
        statusMessage = sanitized(message)
    }

    private func sanitized(_ message: String) -> String {
        OperatorLogSanitizer.sanitize(
            message,
            home: FileManager.default.homeDirectoryForCurrentUser.path,
            hostname: ProcessInfo.processInfo.hostName
        )
    }
}
