import CryptoKit
import Darwin
import Foundation
import Security

enum SecurityValidationError: LocalizedError {
    case invalid(String)

    var errorDescription: String? {
        switch self {
        case let .invalid(message):
            message
        }
    }
}

enum SecurityValidation {
    static let maximumSyntheticResultBytes = 2 * 1024 * 1024
    static let maximumRealLLMResultBytes = 4 * 1024 * 1024
    static let maximumSavedResultFiles = 256
    static let maximumLogEntries = 500
    static let maximumLogEntryCharacters = 8_192

    static func isLowercaseSHA256(_ value: String) -> Bool {
        value.utf8.count == 64
            && value.utf8.allSatisfy {
                (48...57).contains($0) || (97...102).contains($0)
            }
    }

    static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map {
            String(format: "%02x", $0)
        }.joined()
    }

    static func sanitizedChildEnvironment(
        additions: [String: String] = [:]
    ) -> [String: String] {
        let inherited = ProcessInfo.processInfo.environment
        var environment: [String: String] = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"
        ]
        for key in ["HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE"] {
            if let value = inherited[key], !value.isEmpty {
                environment[key] = value
            }
        }
        for (key, value) in additions {
            environment[key] = value
        }
        return environment
    }

    static func ensurePrivateDirectory(_ url: URL) throws {
        let parent = url.deletingLastPathComponent()
        try validateDirectory(parent, requireCurrentOwner: true)

        var fileStatus = stat()
        let status = url.path.withCString { lstat($0, &fileStatus) }
        if status != 0 {
            guard errno == ENOENT else {
                throw posixError("Could not inspect directory", path: url.path)
            }
            try FileManager.default.createDirectory(
                at: url,
                withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700]
            )
        }

        try validateDirectory(url, requireCurrentOwner: true)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700],
            ofItemAtPath: url.path
        )
        try validateDirectory(url, requireCurrentOwner: true)
    }

    static func validateDirectory(
        _ url: URL,
        requireCurrentOwner: Bool
    ) throws {
        guard url.isFileURL, url.path.hasPrefix("/") else {
            throw SecurityValidationError.invalid(
                "Directory path must be an absolute file URL."
            )
        }
        var fileStatus = stat()
        guard url.path.withCString({ lstat($0, &fileStatus) }) == 0 else {
            throw posixError("Could not inspect directory", path: url.path)
        }
        guard (fileStatus.st_mode & S_IFMT) == S_IFDIR else {
            throw SecurityValidationError.invalid(
                "Expected a non-symlink directory at \(url.path)."
            )
        }
        let currentUser = getuid()
        if requireCurrentOwner {
            guard fileStatus.st_uid == currentUser else {
                throw SecurityValidationError.invalid(
                    "Directory is not owned by the current user: \(url.path)."
                )
            }
        } else {
            guard fileStatus.st_uid == currentUser || fileStatus.st_uid == 0 else {
                throw SecurityValidationError.invalid(
                    "Directory has an unexpected owner: \(url.path)."
                )
            }
        }
        guard (fileStatus.st_mode & 0o022) == 0 else {
            throw SecurityValidationError.invalid(
                "Directory is group- or world-writable: \(url.path)."
            )
        }
    }

    static func validateExecutable(
        _ declaredURL: URL,
        expectedSHA256: String?
    ) throws -> URL {
        let url = declaredURL.standardizedFileURL
        guard url.isFileURL, url.path.hasPrefix("/") else {
            throw SecurityValidationError.invalid(
                "Executable path must be absolute."
            )
        }
        try validateDirectoryChainWithoutSymlinks(
            from: url.deletingLastPathComponent()
        )

        var declaredStatus = stat()
        guard url.path.withCString({ lstat($0, &declaredStatus) }) == 0 else {
            throw posixError("Could not inspect executable", path: url.path)
        }
        let declaredKind = declaredStatus.st_mode & S_IFMT
        guard declaredKind == S_IFREG || declaredKind == S_IFLNK else {
            throw SecurityValidationError.invalid(
                "Executable is neither a regular file nor a controlled symlink."
            )
        }

        let resolved = url.resolvingSymlinksInPath().standardizedFileURL
        try validateDirectoryChainWithoutSymlinks(
            from: resolved.deletingLastPathComponent()
        )
        var resolvedStatus = stat()
        guard resolved.path.withCString({ lstat($0, &resolvedStatus) }) == 0,
              (resolvedStatus.st_mode & S_IFMT) == S_IFREG else {
            throw SecurityValidationError.invalid(
                "Executable does not resolve to a regular file."
            )
        }
        let currentUser = getuid()
        guard resolvedStatus.st_uid == currentUser
                || resolvedStatus.st_uid == 0 else {
            throw SecurityValidationError.invalid(
                "Executable has an unexpected owner."
            )
        }
        guard (resolvedStatus.st_mode & 0o022) == 0,
              access(resolved.path, X_OK) == 0 else {
            throw SecurityValidationError.invalid(
                "Executable has unsafe permissions or is not executable."
            )
        }
        if let expectedSHA256 {
            let bytes = try readRegularFile(
                at: resolved,
                maximumBytes: 256 * 1024 * 1024,
                requireCurrentOwner: false
            )
            guard sha256Hex(bytes) == expectedSHA256 else {
                throw SecurityValidationError.invalid(
                    "Pinned Python executable digest mismatch."
                )
            }
        }
        return url
    }

    static func validateRegularFileInside(
        _ candidate: URL,
        root: URL
    ) throws -> URL {
        let canonicalRoot = root.resolvingSymlinksInPath().standardizedFileURL
        let canonicalCandidate = candidate.standardizedFileURL
        let rootPrefix = canonicalRoot.path.hasSuffix("/")
            ? canonicalRoot.path : canonicalRoot.path + "/"
        guard canonicalCandidate.path.hasPrefix(rootPrefix) else {
            throw SecurityValidationError.invalid(
                "Resource path escapes the application bundle."
            )
        }
        try validateDirectoryChainWithoutSymlinks(
            from: canonicalCandidate.deletingLastPathComponent(),
            stoppingAt: canonicalRoot
        )
        var fileStatus = stat()
        guard canonicalCandidate.path.withCString({
            lstat($0, &fileStatus)
        }) == 0,
        (fileStatus.st_mode & S_IFMT) == S_IFREG,
        (fileStatus.st_mode & 0o022) == 0 else {
            throw SecurityValidationError.invalid(
                "Bundled resource is missing, symlinked, or writable by other users."
            )
        }
        return canonicalCandidate
    }

    static func validateBundleSignature(_ bundleURL: URL) throws {
        var staticCode: SecStaticCode?
        let createStatus = SecStaticCodeCreateWithPath(
            bundleURL as CFURL,
            [],
            &staticCode
        )
        guard createStatus == errSecSuccess, let staticCode else {
            throw SecurityValidationError.invalid(
                "Could not inspect the application code signature."
            )
        }
        let validationStatus = SecStaticCodeCheckValidity(
            staticCode,
            SecCSFlags(rawValue: kSecCSStrictValidate),
            nil
        )
        guard validationStatus == errSecSuccess else {
            throw SecurityValidationError.invalid(
                "Application code signature or sealed resources are invalid."
            )
        }
    }

    static func requirePathAbsentInValidatedDirectory(_ url: URL) throws {
        try validateDirectory(
            url.deletingLastPathComponent(),
            requireCurrentOwner: true
        )
        var fileStatus = stat()
        let status = url.path.withCString { lstat($0, &fileStatus) }
        guard status != 0, errno == ENOENT else {
            throw SecurityValidationError.invalid(
                "Output path already exists or cannot be inspected."
            )
        }
    }

    static func readRegularFile(
        at url: URL,
        maximumBytes: Int,
        requireCurrentOwner: Bool = true
    ) throws -> Data {
        guard maximumBytes >= 0, url.isFileURL else {
            throw SecurityValidationError.invalid("Invalid file read request.")
        }
        let descriptor = url.path.withCString {
            Darwin.open($0, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        }
        guard descriptor >= 0 else {
            throw posixError("Could not open regular file", path: url.path)
        }
        defer { _ = Darwin.close(descriptor) }

        var fileStatus = stat()
        guard fstat(descriptor, &fileStatus) == 0,
              (fileStatus.st_mode & S_IFMT) == S_IFREG else {
            throw SecurityValidationError.invalid(
                "Input is not a regular non-symlink file."
            )
        }
        if requireCurrentOwner {
            guard fileStatus.st_uid == getuid() else {
                throw SecurityValidationError.invalid(
                    "Input file is not owned by the current user."
                )
            }
        }
        guard (fileStatus.st_mode & 0o022) == 0 else {
            throw SecurityValidationError.invalid(
                "Input file is group- or world-writable."
            )
        }
        guard fileStatus.st_size >= 0,
              UInt64(fileStatus.st_size) <= UInt64(maximumBytes) else {
            throw SecurityValidationError.invalid(
                "Input file exceeds the allowed size."
            )
        }

        var result = Data()
        result.reserveCapacity(Int(fileStatus.st_size))
        var buffer = [UInt8](repeating: 0, count: 64 * 1024)
        while true {
            let remaining = maximumBytes - result.count
            guard remaining >= 0 else {
                throw SecurityValidationError.invalid(
                    "Input file exceeded the allowed size while reading."
                )
            }
            let requested = min(buffer.count, remaining + 1)
            let count = Darwin.read(descriptor, &buffer, requested)
            if count == 0 {
                break
            }
            guard count > 0 else {
                if errno == EINTR {
                    continue
                }
                throw posixError("Could not read input file", path: url.path)
            }
            result.append(contentsOf: buffer.prefix(count))
            guard result.count <= maximumBytes else {
                throw SecurityValidationError.invalid(
                    "Input file exceeded the allowed size while reading."
                )
            }
        }
        return result
    }

    static func verifiedCanonicalResultDigest(from data: Data) throws -> String {
        guard data.count <= maximumRealLLMResultBytes else {
            throw SecurityValidationError.invalid(
                "Real-LLM result exceeds the allowed size."
            )
        }
        var parser = CanonicalJSONParser(data: data)
        let root = try parser.parse()
        guard case var .object(fields) = root,
              case let .string(claimed)? = fields.removeValue(
                  forKey: "resultSHA256"
              ),
              isLowercaseSHA256(claimed) else {
            throw SecurityValidationError.invalid(
                "Canonical result digest is missing or malformed."
            )
        }
        let computed = try canonicalResultDigestExcludingEmbeddedClaim(
            from: data
        )
        guard computed == claimed else {
            throw SecurityValidationError.invalid(
                "Canonical result digest does not match the result bytes."
            )
        }
        return claimed
    }

    static func canonicalResultDigestExcludingEmbeddedClaim(
        from data: Data
    ) throws -> String {
        guard data.count <= maximumRealLLMResultBytes else {
            throw SecurityValidationError.invalid(
                "Real-LLM result exceeds the allowed size."
            )
        }
        var parser = CanonicalJSONParser(data: data)
        let root = try parser.parse()
        guard case var .object(fields) = root else {
            throw SecurityValidationError.invalid(
                "Canonical result must be a JSON object."
            )
        }
        fields.removeValue(forKey: "resultSHA256")
        let canonical = try CanonicalJSONValue.object(fields).serialized()
        return sha256Hex(Data(canonical.utf8))
    }

    static func checkedAdd(_ left: Int, _ right: Int) throws -> Int {
        let (value, overflow) = left.addingReportingOverflow(right)
        guard !overflow else {
            throw SecurityValidationError.invalid(
                "Integer overflow in result totals."
            )
        }
        return value
    }

    private static func validateDirectoryChainWithoutSymlinks(
        from start: URL,
        stoppingAt stop: URL? = nil
    ) throws {
        var current = start.standardizedFileURL
        let stopPath = stop?.standardizedFileURL.path
        while true {
            try validateDirectory(current, requireCurrentOwner: false)
            if current.path == stopPath || current.path == "/" {
                break
            }
            let parent = current.deletingLastPathComponent()
            guard parent.path != current.path else { break }
            current = parent
        }
    }

    private static func posixError(
        _ operation: String,
        path: String
    ) -> SecurityValidationError {
        let message = String(cString: strerror(errno))
        return .invalid("\(operation) at \(path): \(message).")
    }
}

final class BoundedOutputBuffer: @unchecked Sendable {
    private let limit: Int
    private let lock = NSLock()
    private var bytes = Data()
    private var wasTruncated = false

    init(limit: Int = 64 * 1024) {
        self.limit = limit
    }

    func append(_ data: Data) {
        guard !data.isEmpty else { return }
        lock.lock()
        defer { lock.unlock() }
        let remaining = max(0, limit - bytes.count)
        if remaining > 0 {
            bytes.append(data.prefix(remaining))
        }
        if data.count > remaining {
            wasTruncated = true
        }
    }

    func text(fallback: String) -> String {
        lock.lock()
        defer { lock.unlock() }
        var value = String(data: bytes, encoding: .utf8) ?? fallback
        if wasTruncated {
            value += "\n[output truncated]"
        }
        return value
    }
}

private indirect enum CanonicalJSONValue {
    case object([String: CanonicalJSONValue])
    case array([CanonicalJSONValue])
    case string(String)
    case number(String)
    case boolean(Bool)
    case null

    func serialized() throws -> String {
        switch self {
        case let .object(fields):
            let keys = fields.keys.sorted(by: unicodeScalarLess)
            let entries = try keys.map { key in
                try quote(key) + ":" + fields[key]!.serialized()
            }
            return "{" + entries.joined(separator: ",") + "}"
        case let .array(values):
            return "[" + (try values.map { try $0.serialized() })
                .joined(separator: ",") + "]"
        case let .string(value):
            return try quote(value)
        case let .number(value):
            return value
        case let .boolean(value):
            return value ? "true" : "false"
        case .null:
            return "null"
        }
    }

    private func quote(_ value: String) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes]
        return String(data: try encoder.encode(value), encoding: .utf8)!
    }

    private func unicodeScalarLess(_ left: String, _ right: String) -> Bool {
        left.unicodeScalars.lexicographicallyPrecedes(right.unicodeScalars) {
            $0.value < $1.value
        }
    }
}

private struct CanonicalJSONParser {
    private let bytes: [UInt8]
    private var index = 0
    private var nodes = 0

    init(data: Data) {
        bytes = Array(data)
    }

    mutating func parse() throws -> CanonicalJSONValue {
        skipWhitespace()
        let value = try parseValue(depth: 0)
        skipWhitespace()
        guard index == bytes.count else {
            throw error("Trailing bytes after JSON value.")
        }
        return value
    }

    private mutating func parseValue(
        depth: Int
    ) throws -> CanonicalJSONValue {
        guard depth <= 64 else {
            throw error("JSON nesting is too deep.")
        }
        nodes += 1
        guard nodes <= 100_000, index < bytes.count else {
            throw error("JSON is empty or too complex.")
        }
        switch bytes[index] {
        case 0x7B:
            return try parseObject(depth: depth + 1)
        case 0x5B:
            return try parseArray(depth: depth + 1)
        case 0x22:
            return .string(try parseString())
        case 0x74:
            try consumeLiteral("true")
            return .boolean(true)
        case 0x66:
            try consumeLiteral("false")
            return .boolean(false)
        case 0x6E:
            try consumeLiteral("null")
            return .null
        case 0x2D, 0x30...0x39:
            return .number(try parseNumber())
        default:
            throw error("Unexpected JSON token.")
        }
    }

    private mutating func parseObject(
        depth: Int
    ) throws -> CanonicalJSONValue {
        index += 1
        skipWhitespace()
        var fields: [String: CanonicalJSONValue] = [:]
        if consumeIf(0x7D) {
            return .object(fields)
        }
        while true {
            guard index < bytes.count, bytes[index] == 0x22 else {
                throw error("JSON object key must be a string.")
            }
            let key = try parseString()
            guard fields[key] == nil else {
                throw error("Duplicate JSON object key.")
            }
            skipWhitespace()
            try consume(0x3A, message: "Missing colon after JSON key.")
            skipWhitespace()
            fields[key] = try parseValue(depth: depth)
            skipWhitespace()
            if consumeIf(0x7D) {
                return .object(fields)
            }
            try consume(0x2C, message: "Missing comma in JSON object.")
            skipWhitespace()
        }
    }

    private mutating func parseArray(
        depth: Int
    ) throws -> CanonicalJSONValue {
        index += 1
        skipWhitespace()
        var values: [CanonicalJSONValue] = []
        if consumeIf(0x5D) {
            return .array(values)
        }
        while true {
            values.append(try parseValue(depth: depth))
            skipWhitespace()
            if consumeIf(0x5D) {
                return .array(values)
            }
            try consume(0x2C, message: "Missing comma in JSON array.")
            skipWhitespace()
        }
    }

    private mutating func parseString() throws -> String {
        let start = index
        index += 1
        while index < bytes.count {
            let byte = bytes[index]
            if byte == 0x22 {
                index += 1
                let token = Data(bytes[start..<index])
                do {
                    return try JSONDecoder().decode(String.self, from: token)
                } catch {
                    throw self.error("Invalid JSON string.")
                }
            }
            guard byte >= 0x20 else {
                throw error("Unescaped control byte in JSON string.")
            }
            if byte == 0x5C {
                index += 1
                guard index < bytes.count else {
                    throw error("Truncated JSON escape.")
                }
                if bytes[index] == 0x75 {
                    guard index + 4 < bytes.count else {
                        throw error("Truncated Unicode escape.")
                    }
                    for offset in 1...4 where !isHex(bytes[index + offset]) {
                        throw error("Invalid Unicode escape.")
                    }
                    index += 4
                } else if ![0x22, 0x5C, 0x2F, 0x62, 0x66, 0x6E, 0x72, 0x74]
                    .contains(bytes[index]) {
                    throw error("Invalid JSON escape.")
                }
            }
            index += 1
        }
        throw error("Unterminated JSON string.")
    }

    private mutating func parseNumber() throws -> String {
        let start = index
        if consumeIf(0x2D) {
            guard index < bytes.count else {
                throw error("Truncated JSON number.")
            }
        }
        if consumeIf(0x30) {
            if index < bytes.count, isDigit(bytes[index]) {
                throw error("Leading zero in JSON number.")
            }
        } else {
            guard index < bytes.count, (0x31...0x39).contains(bytes[index]) else {
                throw error("Invalid JSON integer.")
            }
            while index < bytes.count, isDigit(bytes[index]) {
                index += 1
            }
        }

        var isFloatingPoint = false
        if consumeIf(0x2E) {
            isFloatingPoint = true
            guard index < bytes.count, isDigit(bytes[index]) else {
                throw error("Missing JSON fractional digits.")
            }
            while index < bytes.count, isDigit(bytes[index]) {
                index += 1
            }
        }
        if index < bytes.count, bytes[index] == 0x65 || bytes[index] == 0x45 {
            isFloatingPoint = true
            index += 1
            if index < bytes.count, bytes[index] == 0x2B || bytes[index] == 0x2D {
                index += 1
            }
            guard index < bytes.count, isDigit(bytes[index]) else {
                throw error("Missing JSON exponent digits.")
            }
            while index < bytes.count, isDigit(bytes[index]) {
                index += 1
            }
        }

        guard let raw = String(bytes: bytes[start..<index], encoding: .utf8) else {
            throw error("Invalid JSON number encoding.")
        }
        if isFloatingPoint {
            guard let value = Double(raw), value.isFinite else {
                throw error("Non-finite JSON number.")
            }
            return String(value)
        }
        return raw == "-0" ? "0" : raw
    }

    private mutating func consumeLiteral(_ literal: StaticString) throws {
        let literalBytes = Array(String(describing: literal).utf8)
        guard index + literalBytes.count <= bytes.count,
              Array(bytes[index..<(index + literalBytes.count)])
                == literalBytes else {
            throw error("Invalid JSON literal.")
        }
        index += literalBytes.count
    }

    private mutating func consume(_ byte: UInt8, message: String) throws {
        guard consumeIf(byte) else {
            throw error(message)
        }
    }

    private mutating func consumeIf(_ byte: UInt8) -> Bool {
        guard index < bytes.count, bytes[index] == byte else {
            return false
        }
        index += 1
        return true
    }

    private mutating func skipWhitespace() {
        while index < bytes.count,
              [0x20, 0x09, 0x0A, 0x0D].contains(bytes[index]) {
            index += 1
        }
    }

    private func isDigit(_ byte: UInt8) -> Bool {
        (0x30...0x39).contains(byte)
    }

    private func isHex(_ byte: UInt8) -> Bool {
        (0x30...0x39).contains(byte)
            || (0x41...0x46).contains(byte)
            || (0x61...0x66).contains(byte)
    }

    private func error(_ message: String) -> SecurityValidationError {
        .invalid("\(message) (byte \(index)).")
    }
}
