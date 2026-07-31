import CryptoKit
import Darwin
import Foundation

private struct PythonRuntimeManifest: Decodable {
    let entries: [PythonRuntimeEntry]
    let fileCount: Int
    let pythonDeclaredPath: String
    let pythonExecutableSHA256: String
    let pythonResolvedPath: String
    let pythonVersion: String
    let roots: [PythonRuntimeRoot]
    let schemaVersion: String
    let symlinkCount: Int
    let totalBytes: Int64
}

private struct PythonRuntimeRoot: Decodable {
    let path: String
    let role: String
}

private struct PythonRuntimeEntry: Decodable {
    let kind: String
    let path: String
    let root: Int
    let sha256: String?
    let size: Int64?
    let target: String?

    var key: String {
        "\(root):\(path)"
    }
}

struct PythonRuntimeIdentity {
    let declaredURL: URL
    let executableSHA256: String
    let resolvedURL: URL
    let version: String
}

extension SecurityValidation {
    static let maximumPythonRuntimeManifestBytes = 32 * 1024 * 1024
    private static let maximumPythonRuntimeEntries = 100_000
    private static let maximumPythonRuntimeBytes: Int64 =
        8 * 1024 * 1024 * 1024

    static func pythonRuntimeIdentity(
        from manifestURL: URL
    ) throws -> PythonRuntimeIdentity {
        let manifest = try decodePythonRuntimeManifest(at: manifestURL)
        guard manifest.schemaVersion
                == "corelm-python-runtime-manifest-v1",
              isLowercaseSHA256(manifest.pythonExecutableSHA256),
              validPython312Version(manifest.pythonVersion) else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest identity is invalid."
            )
        }
        let declared = URL(fileURLWithPath: manifest.pythonDeclaredPath)
            .standardizedFileURL
        let resolved = URL(fileURLWithPath: manifest.pythonResolvedPath)
            .standardizedFileURL
        guard declared.path == manifest.pythonDeclaredPath,
              resolved.path == manifest.pythonResolvedPath,
              declared.path.hasPrefix("/"),
              resolved.path.hasPrefix("/") else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest paths are invalid."
            )
        }
        return PythonRuntimeIdentity(
            declaredURL: declared,
            executableSHA256: manifest.pythonExecutableSHA256,
            resolvedURL: resolved,
            version: manifest.pythonVersion
        )
    }

    static func validatePythonRuntimeManifest(
        at manifestURL: URL,
        expectedPythonURL: URL
    ) throws {
        let manifest = try decodePythonRuntimeManifest(at: manifestURL)

        guard manifest.schemaVersion
                == "corelm-python-runtime-manifest-v1",
              manifest.roots.count == 2,
              manifest.roots.map(\.role)
                == ["base-prefix", "virtual-environment"],
              manifest.entries.count <= maximumPythonRuntimeEntries,
              manifest.fileCount >= 1,
              manifest.symlinkCount >= 0,
              manifest.fileCount + manifest.symlinkCount
                == manifest.entries.count,
              manifest.totalBytes > 0,
              manifest.totalBytes <= maximumPythonRuntimeBytes,
              isLowercaseSHA256(manifest.pythonExecutableSHA256),
              validPython312Version(manifest.pythonVersion) else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest header is invalid."
            )
        }

        let expectedDeclared = expectedPythonURL.standardizedFileURL
        let expectedResolved = expectedDeclared
            .resolvingSymlinksInPath().standardizedFileURL
        guard manifest.pythonDeclaredPath == expectedDeclared.path,
              manifest.pythonResolvedPath == expectedResolved.path else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest names a different executable "
                    + "(declared \(manifest.pythonDeclaredPath) vs "
                    + "\(expectedDeclared.path), resolved "
                    + "\(manifest.pythonResolvedPath) vs "
                    + "\(expectedResolved.path))."
            )
        }

        let roots = try manifest.roots.map { declared -> URL in
            let root = URL(fileURLWithPath: declared.path)
                .standardizedFileURL
            guard root.path == declared.path,
                  root.path.hasPrefix("/"),
                  root.path != "/" else {
                throw SecurityValidationError.invalid(
                    "Python runtime manifest contains an unsafe root."
                )
            }
            try validateRuntimeDirectory(root)
            return root
        }
        let firstPrefix = roots[0].path + "/"
        let secondPrefix = roots[1].path + "/"
        guard !firstPrefix.hasPrefix(secondPrefix),
              !secondPrefix.hasPrefix(firstPrefix) else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest roots overlap."
            )
        }

        var expectedKeys = Set<String>()
        var previousKey: String?
        var countedFiles = 0
        var countedSymlinks = 0
        var countedBytes: Int64 = 0
        var executableDigest: String?
        for entry in manifest.entries {
            guard entry.root >= 0, entry.root < roots.count,
                  validRuntimeRelativePath(entry.path),
                  previousKey == nil || previousKey! < entry.key,
                  expectedKeys.insert(entry.key).inserted else {
                throw SecurityValidationError.invalid(
                    "Python runtime manifest entries are unsafe or unsorted."
                )
            }
            previousKey = entry.key
            let candidate = roots[entry.root]
                .appendingPathComponent(entry.path)
                .standardizedFileURL
            let rootPrefix = roots[entry.root].path + "/"
            guard candidate.path.hasPrefix(rootPrefix) else {
                throw SecurityValidationError.invalid(
                    "Python runtime entry escapes its declared root."
                )
            }

            switch entry.kind {
            case "file":
                guard let size = entry.size,
                      size >= 0,
                      let expectedDigest = entry.sha256,
                      isLowercaseSHA256(expectedDigest),
                      entry.target == nil else {
                    throw SecurityValidationError.invalid(
                        "Python runtime file entry is malformed."
                    )
                }
                let digest = try sha256RuntimeFile(
                    at: candidate,
                    expectedSize: size
                )
                guard digest == expectedDigest else {
                    throw SecurityValidationError.invalid(
                        "Python runtime file digest mismatch: \(entry.path)."
                    )
                }
                countedFiles += 1
                let (newTotal, overflow) = countedBytes
                    .addingReportingOverflow(size)
                guard !overflow, newTotal <= maximumPythonRuntimeBytes else {
                    throw SecurityValidationError.invalid(
                        "Python runtime byte total overflowed."
                    )
                }
                countedBytes = newTotal
                if candidate.path == expectedResolved.path {
                    executableDigest = digest
                }
            case "symlink":
                guard entry.sha256 == nil,
                      entry.size == nil,
                      let target = entry.target,
                      !target.isEmpty,
                      try runtimeSymlinkTarget(at: candidate) == target else {
                    throw SecurityValidationError.invalid(
                        "Python runtime symlink mismatch: \(entry.path)."
                    )
                }
                if runtimeSymlinkCanBeLoaded(entry.path) {
                    try validateRuntimeSymlinkResolution(
                        at: candidate,
                        roots: roots
                    )
                }
                countedSymlinks += 1
            default:
                throw SecurityValidationError.invalid(
                    "Python runtime manifest has an unsupported entry kind."
                )
            }
        }
        guard countedFiles == manifest.fileCount,
              countedSymlinks == manifest.symlinkCount,
              countedBytes == manifest.totalBytes,
              executableDigest == manifest.pythonExecutableSHA256 else {
            throw SecurityValidationError.invalid(
                "Python runtime manifest totals are inconsistent."
            )
        }

        var actualKeys = Set<String>()
        for (rootIndex, root) in roots.enumerated() {
            let enumerator = FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: nil,
                options: [],
                errorHandler: { _, _ in false }
            )
            guard let enumerator else {
                throw SecurityValidationError.invalid(
                    "Could not enumerate the Python runtime."
                )
            }
            while let item = enumerator.nextObject() as? URL {
                let relative = String(
                    item.path.dropFirst(root.path.count + 1)
                )
                var itemStatus = stat()
                guard item.path.withCString({
                    lstat($0, &itemStatus)
                }) == 0 else {
                    throw SecurityValidationError.invalid(
                        "Python runtime changed during enumeration."
                    )
                }
                let kind = itemStatus.st_mode & S_IFMT
                if kind == S_IFDIR {
                    try validateRuntimeDirectory(item)
                    if item.lastPathComponent == "__pycache__" {
                        enumerator.skipDescendants()
                    }
                    continue
                }
                if kind == S_IFLNK {
                    enumerator.skipDescendants()
                }
                guard kind == S_IFREG || kind == S_IFLNK,
                      actualKeys.insert("\(rootIndex):\(relative)")
                        .inserted else {
                    throw SecurityValidationError.invalid(
                        "Python runtime contains an unsupported entry."
                    )
                }
            }
        }
        guard actualKeys == expectedKeys else {
            let missing = expectedKeys.subtracting(actualKeys)
                .sorted().first ?? "none"
            let unexpected = actualKeys.subtracting(expectedKeys)
                .sorted().first ?? "none"
            throw SecurityValidationError.invalid(
                "Python runtime contains missing or unmanifested files "
                    + "(missing \(missing), unexpected \(unexpected))."
            )
        }
    }

    private static func decodePythonRuntimeManifest(
        at manifestURL: URL
    ) throws -> PythonRuntimeManifest {
        let bytes = try readRegularFile(
            at: manifestURL,
            maximumBytes: maximumPythonRuntimeManifestBytes,
            requireCurrentOwner: false
        )
        do {
            return try JSONDecoder().decode(
                PythonRuntimeManifest.self,
                from: bytes
            )
        } catch {
            throw SecurityValidationError.invalid(
                "Python runtime manifest is not valid JSON."
            )
        }
    }

    private static func validRuntimeRelativePath(_ value: String) -> Bool {
        guard !value.isEmpty, !value.hasPrefix("/"),
              !value.utf8.contains(0) else {
            return false
        }
        return value.split(separator: "/", omittingEmptySubsequences: false)
            .allSatisfy { component in
                !component.isEmpty && component != "." && component != ".."
            }
    }

    private static func validPython312Version(_ value: String) -> Bool {
        let components = value.split(separator: ".", omittingEmptySubsequences: false)
        return components.count == 3
            && components[0] == "3"
            && components[1] == "12"
            && components[2].allSatisfy(\.isNumber)
            && !components[2].isEmpty
    }

    private static func validateRuntimeDirectory(_ url: URL) throws {
        var directoryStatus = stat()
        guard url.path.withCString({
            lstat($0, &directoryStatus)
        }) == 0,
        (directoryStatus.st_mode & S_IFMT) == S_IFDIR,
        (directoryStatus.st_mode & 0o022) == 0,
        directoryStatus.st_uid == getuid() || directoryStatus.st_uid == 0 else {
            throw SecurityValidationError.invalid(
                "Python runtime directory is unsafe: \(url.path)."
            )
        }
    }

    private static func sha256RuntimeFile(
        at url: URL,
        expectedSize: Int64
    ) throws -> String {
        let descriptor = url.path.withCString {
            Darwin.open($0, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        }
        guard descriptor >= 0 else {
            throw SecurityValidationError.invalid(
                "Could not open Python runtime file: \(url.path)."
            )
        }
        defer { _ = Darwin.close(descriptor) }

        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              (opened.st_mode & S_IFMT) == S_IFREG,
              opened.st_size == expectedSize,
              (opened.st_mode & 0o022) == 0,
              opened.st_uid == getuid() || opened.st_uid == 0 else {
            throw SecurityValidationError.invalid(
                "Python runtime file has unsafe metadata: \(url.path)."
            )
        }

        var hasher = SHA256()
        var buffer = [UInt8](repeating: 0, count: 1024 * 1024)
        while true {
            let count = Darwin.read(descriptor, &buffer, buffer.count)
            if count == 0 {
                break
            }
            guard count > 0 else {
                if errno == EINTR {
                    continue
                }
                throw SecurityValidationError.invalid(
                    "Could not hash Python runtime file: \(url.path)."
                )
            }
            hasher.update(data: Data(buffer.prefix(count)))
        }
        var finished = stat()
        guard fstat(descriptor, &finished) == 0,
              opened.st_dev == finished.st_dev,
              opened.st_ino == finished.st_ino,
              opened.st_size == finished.st_size,
              opened.st_mtimespec.tv_sec == finished.st_mtimespec.tv_sec,
              opened.st_mtimespec.tv_nsec == finished.st_mtimespec.tv_nsec,
              opened.st_ctimespec.tv_sec == finished.st_ctimespec.tv_sec,
              opened.st_ctimespec.tv_nsec == finished.st_ctimespec.tv_nsec else {
            throw SecurityValidationError.invalid(
                "Python runtime file changed while hashing: \(url.path)."
            )
        }
        return hasher.finalize().map {
            String(format: "%02x", $0)
        }.joined()
    }

    private static func runtimeSymlinkTarget(at url: URL) throws -> String {
        var linkStatus = stat()
        guard url.path.withCString({ lstat($0, &linkStatus) }) == 0,
              (linkStatus.st_mode & S_IFMT) == S_IFLNK,
              linkStatus.st_size >= 0,
              linkStatus.st_size <= 16 * 1024 else {
            throw SecurityValidationError.invalid(
                "Python runtime symlink is invalid."
            )
        }
        var buffer = [CChar](
            repeating: 0,
            count: max(1, Int(linkStatus.st_size) + 1)
        )
        let count = url.path.withCString {
            readlink($0, &buffer, buffer.count - 1)
        }
        guard count >= 0, count < buffer.count else {
            throw SecurityValidationError.invalid(
                "Could not read Python runtime symlink."
            )
        }
        return String(
            decoding: buffer.prefix(count).map { UInt8(bitPattern: $0) },
            as: UTF8.self
        )
    }

    private static func runtimeSymlinkCanBeLoaded(_ path: String) -> Bool {
        path.hasPrefix("bin/")
            || (
                path.hasPrefix("lib/")
                    && !path.hasPrefix("lib/pkgconfig/")
            )
    }

    private static func validateRuntimeSymlinkResolution(
        at url: URL,
        roots: [URL]
    ) throws {
        let resolved = url.resolvingSymlinksInPath().standardizedFileURL
        let contained = roots.contains { root in
            resolved.path == root.path
                || resolved.path.hasPrefix(root.path + "/")
        }
        var status = stat()
        guard contained,
              !resolved.pathComponents.contains("__pycache__"),
              resolved.path.withCString({ lstat($0, &status) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG
                || (status.st_mode & S_IFMT) == S_IFDIR else {
            throw SecurityValidationError.invalid(
                "Loadable Python runtime symlink escapes the manifested roots."
            )
        }
    }
}
