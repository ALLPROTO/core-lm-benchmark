import Foundation

enum Verdict: String, Codable {
    case pass = "PASS"
    case fail = "FAIL"
    case inconclusive = "INCONCLUSIVE"
}

enum ModuleState: String {
    case ready = "Ready"
    case running = "Running"
    case complete = "Complete"
}
