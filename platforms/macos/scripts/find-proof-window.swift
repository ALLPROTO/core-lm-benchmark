import AppKit
import CoreGraphics
import CryptoKit
import Darwin
import Foundation

private let requiredBundleIdentifier = "com.corelm.benchmark"
private let maximumCoordinateMagnitude = 1_000_000.0
private let maximumDimension = 100_000.0
private let maximumExecutableBytes: off_t = 512 * 1_024 * 1_024

private enum ResolverFailure: Error, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let value):
            return value
        }
    }
}

private struct Arguments {
    let pid: pid_t
    let bundleIdentifier: String
}

private struct CanonicalBounds: Encodable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

private struct CanonicalWindow: Encodable {
    let schemaVersion: Int
    let mode: String
    let pid: Int32
    let bundleIdentifier: String
    let windowID: UInt32
    let ownerName: String
    let bounds: CanonicalBounds
    let executablePath: String?
    let executableSHA256: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case mode
        case pid
        case bundleIdentifier = "bundle_identifier"
        case windowID = "window_id"
        case ownerName = "owner_name"
        case bounds
        case executablePath = "executable_path"
        case executableSHA256 = "executable_sha256"
    }
}

private struct ExecutableEvidence {
    let path: String
    let sha256: String
}

private func fail(_ message: String) -> Never {
    let data = Data("ERROR find-proof-window: \(message)\n".utf8)
    FileHandle.standardError.write(data)
    exit(EXIT_FAILURE)
}

private func parseArguments(_ rawArguments: [String]) throws -> Arguments {
    guard rawArguments.count == 4 else {
        throw ResolverFailure.message(
            "expected exactly --pid <positive-int> --bundle-id \(requiredBundleIdentifier)"
        )
    }

    var parsedPID: pid_t?
    var parsedBundleIdentifier: String?
    var index = 0
    while index < rawArguments.count {
        let flag = rawArguments[index]
        let value = rawArguments[index + 1]
        switch flag {
        case "--pid":
            guard parsedPID == nil,
                  !value.isEmpty,
                  value.utf8.allSatisfy({ (48...57).contains($0) }),
                  let candidate = pid_t(value),
                  candidate > 0 else {
                throw ResolverFailure.message("--pid must be supplied once as a positive integer")
            }
            parsedPID = candidate
        case "--bundle-id":
            guard parsedBundleIdentifier == nil, value == requiredBundleIdentifier else {
                throw ResolverFailure.message(
                    "--bundle-id must be supplied once as \(requiredBundleIdentifier)"
                )
            }
            parsedBundleIdentifier = value
        default:
            throw ResolverFailure.message("unknown argument: \(flag)")
        }
        index += 2
    }

    guard let pid = parsedPID, let bundleIdentifier = parsedBundleIdentifier else {
        throw ResolverFailure.message("both required arguments must be supplied exactly once")
    }
    return Arguments(pid: pid, bundleIdentifier: bundleIdentifier)
}

private func runScreenCapturePreflight() -> Never {
    if #available(macOS 10.15, *) {
        guard CGPreflightScreenCaptureAccess() else {
            fail("screen capture access is not authorized")
        }
        FileHandle.standardOutput.write(
            Data("{\"screen_capture_authorized\":true}\n".utf8)
        )
        exit(EXIT_SUCCESS)
    }
    fail("screen capture preflight is unavailable on this macOS version")
}

private func requiredNumber(_ value: Any?, field: String) throws -> NSNumber {
    guard let number = value as? NSNumber,
          CFGetTypeID(number) != CFBooleanGetTypeID() else {
        throw ResolverFailure.message("window metadata has invalid \(field)")
    }
    return number
}

private func requiredInteger(_ value: Any?, field: String) throws -> Int64 {
    let number = try requiredNumber(value, field: field)
    let doubleValue = number.doubleValue
    guard doubleValue.isFinite,
          doubleValue.rounded(.towardZero) == doubleValue,
          doubleValue >= Double(Int64.min),
          doubleValue <= Double(Int64.max) else {
        throw ResolverFailure.message("window metadata has non-integral \(field)")
    }
    return number.int64Value
}

private func requiredDouble(_ value: Any?, field: String) throws -> Double {
    let result = try requiredNumber(value, field: field).doubleValue
    guard result.isFinite else {
        throw ResolverFailure.message("window metadata has non-finite \(field)")
    }
    return result == 0 ? 0 : result
}

private func requireRunningApplication(
    pid: pid_t,
    bundleIdentifier: String
) throws -> NSRunningApplication {
    guard let application = NSRunningApplication(processIdentifier: pid),
          !application.isTerminated,
          application.processIdentifier == pid,
          application.bundleIdentifier == bundleIdentifier else {
        throw ResolverFailure.message(
            "PID \(pid) is not a running \(bundleIdentifier) application"
        )
    }
    return application
}

private func executableEvidence(
    for application: NSRunningApplication
) -> ExecutableEvidence? {
    guard let executableURL = application.executableURL,
          executableURL.isFileURL else {
        return nil
    }
    let path = executableURL.standardizedFileURL.path
    guard path.hasPrefix("/"),
          !path.utf8.contains(0),
          path.utf8.count <= Int(MAXPATHLEN) else {
        return nil
    }

    let descriptor = path.withCString {
        Darwin.open($0, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
    }
    guard descriptor >= 0 else {
        return nil
    }
    defer {
        Darwin.close(descriptor)
    }

    var before = stat()
    guard fstat(descriptor, &before) == 0,
          (before.st_mode & S_IFMT) == S_IFREG,
          before.st_size > 0,
          before.st_size <= maximumExecutableBytes else {
        return nil
    }

    var hasher = SHA256()
    var buffer = [UInt8](repeating: 0, count: 1 << 20)
    while true {
        let count = Darwin.read(descriptor, &buffer, buffer.count)
        if count == 0 {
            break
        }
        if count < 0 {
            if errno == EINTR {
                continue
            }
            return nil
        }
        hasher.update(data: Data(buffer[0..<count]))
    }

    var after = stat()
    guard fstat(descriptor, &after) == 0,
          before.st_dev == after.st_dev,
          before.st_ino == after.st_ino,
          before.st_size == after.st_size,
          before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
          before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
          before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
          before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else {
        return nil
    }

    let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
    return ExecutableEvidence(path: path, sha256: digest)
}

private func validatedBounds(_ value: Any?) throws -> CanonicalBounds {
    guard let dictionary = value as? [String: Any] else {
        throw ResolverFailure.message("window metadata has invalid bounds")
    }
    let x = try requiredDouble(dictionary["X"], field: "bounds.X")
    let y = try requiredDouble(dictionary["Y"], field: "bounds.Y")
    let width = try requiredDouble(dictionary["Width"], field: "bounds.Width")
    let height = try requiredDouble(dictionary["Height"], field: "bounds.Height")

    guard abs(x) <= maximumCoordinateMagnitude,
          abs(y) <= maximumCoordinateMagnitude,
          width > 0,
          height > 0,
          width <= maximumDimension,
          height <= maximumDimension,
          (x + width).isFinite,
          (y + height).isFinite,
          abs(x + width) <= maximumCoordinateMagnitude + maximumDimension,
          abs(y + height) <= maximumCoordinateMagnitude + maximumDimension else {
        throw ResolverFailure.message("window bounds are outside the safe finite range")
    }

    return CanonicalBounds(x: x, y: y, width: width, height: height)
}

private func resolveWindow(arguments: Arguments) throws -> CanonicalWindow {
    let initialApplication = try requireRunningApplication(
        pid: arguments.pid,
        bundleIdentifier: arguments.bundleIdentifier
    )

    let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    guard let records = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
        as? [[String: Any]] else {
        throw ResolverFailure.message("CoreGraphics did not return a window list")
    }

    var matches: [CanonicalWindow] = []
    for record in records {
        let ownerPID = try requiredInteger(
            record[kCGWindowOwnerPID as String],
            field: "owner PID"
        )
        guard ownerPID == Int64(arguments.pid) else {
            continue
        }

        let layer = try requiredInteger(
            record[kCGWindowLayer as String],
            field: "layer"
        )
        let alpha = try requiredDouble(
            record[kCGWindowAlpha as String],
            field: "alpha"
        )
        guard let isOnscreen = record[kCGWindowIsOnscreen as String] as? NSNumber,
              CFGetTypeID(isOnscreen) == CFBooleanGetTypeID() else {
            throw ResolverFailure.message("window metadata has invalid on-screen state")
        }
        guard layer == 0, alpha > 0, alpha <= 1, isOnscreen.boolValue else {
            continue
        }

        let rawWindowID = try requiredInteger(
            record[kCGWindowNumber as String],
            field: "window ID"
        )
        guard rawWindowID > 0, rawWindowID <= Int64(UInt32.max) else {
            throw ResolverFailure.message("window ID is outside the valid CGWindowID range")
        }
        guard let ownerName = record[kCGWindowOwnerName as String] as? String,
              !ownerName.isEmpty,
              ownerName.utf8.count <= 512 else {
            throw ResolverFailure.message("window metadata has invalid owner name")
        }
        let bounds = try validatedBounds(record[kCGWindowBounds as String])
        matches.append(
            CanonicalWindow(
                schemaVersion: 1,
                mode: "MACOS_WINDOW_ID_ONLY",
                pid: arguments.pid,
                bundleIdentifier: arguments.bundleIdentifier,
                windowID: UInt32(rawWindowID),
                ownerName: ownerName,
                bounds: bounds,
                executablePath: nil,
                executableSHA256: nil
            )
        )
    }

    guard matches.count == 1, let match = matches.first else {
        throw ResolverFailure.message(
            "expected exactly one eligible window for PID \(arguments.pid); found \(matches.count)"
        )
    }

    let finalApplication = try requireRunningApplication(
        pid: arguments.pid,
        bundleIdentifier: arguments.bundleIdentifier
    )
    guard initialApplication.executableURL == finalApplication.executableURL else {
        throw ResolverFailure.message("application executable changed during resolution")
    }
    let executable = executableEvidence(for: finalApplication)
    return CanonicalWindow(
        schemaVersion: match.schemaVersion,
        mode: match.mode,
        pid: match.pid,
        bundleIdentifier: match.bundleIdentifier,
        windowID: match.windowID,
        ownerName: match.ownerName,
        bounds: match.bounds,
        executablePath: executable?.path,
        executableSHA256: executable?.sha256
    )
}

do {
    let rawArguments = Array(CommandLine.arguments.dropFirst())
    if rawArguments == ["--preflight"] {
        runScreenCapturePreflight()
    }
    let arguments = try parseArguments(rawArguments)
    let window = try resolveWindow(arguments: arguments)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    var encoded = try encoder.encode(window)
    encoded.append(0x0A)
    FileHandle.standardOutput.write(encoded)
} catch {
    fail(String(describing: error))
}
