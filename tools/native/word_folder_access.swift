import AppKit
import Foundation

private let manifestLimit = 1_048_576
private let manifestName = "lod-pane.xml"

private func canonical(_ url: URL) -> URL {
    url.standardizedFileURL.resolvingSymlinksInPath()
}

private func wordDocumentsURL(home: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
    home.appendingPathComponent("Library/Containers/com.microsoft.Word/Data/Documents", isDirectory: true)
}

private func allowedFolder(_ selected: URL, documents: URL) -> URL? {
    let selectedPath = canonical(selected).path
    let documentsPath = canonical(documents).path
    let wefPath = URL(fileURLWithPath: documentsPath, isDirectory: true)
        .appendingPathComponent("wef", isDirectory: true).path
    guard selectedPath == documentsPath || selectedPath == wefPath else { return nil }
    return URL(fileURLWithPath: selectedPath, isDirectory: true)
}

private func jsonLine(_ object: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
        FileHandle.standardOutput.write(Data("{\"ok\":false,\"error\":\"Could not encode response.\"}\n".utf8))
        return
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}

private func failure(_ error: Error) -> [String: Any] {
    ["ok": false, "error": error.localizedDescription]
}

private enum AccessError: LocalizedError {
    case invalidSelection
    case invalidCommand
    case invalidData
    case tooLarge
    case conflict
    case unexpectedFile

    var errorDescription: String? {
        switch self {
        case .invalidSelection: return "Choose the Word Documents folder or its wef folder."
        case .invalidCommand: return "Invalid folder access command."
        case .invalidData: return "The manifest data is invalid."
        case .tooLarge: return "The manifest exceeds the 1 MiB limit."
        case .conflict: return "The Word manifest changed during setup; it was left untouched."
        case .unexpectedFile: return "The Word manifest path is not a regular file."
        }
    }
}

private final class FolderSession {
    let selectedFolder: URL
    let documentsFolder: URL
    private var originalSnapshot: Data??
    private var hasMutation = false
    private var expectedCurrent: Data??

    init(selectedFolder: URL, documentsFolder: URL) throws {
        guard let allowed = allowedFolder(selectedFolder, documents: documentsFolder) else {
            throw AccessError.invalidSelection
        }
        self.selectedFolder = allowed
        self.documentsFolder = canonical(documentsFolder)
    }

    private var wefFolder: URL {
        if selectedFolder.path == documentsFolder.path {
            return documentsFolder.appendingPathComponent("wef", isDirectory: true)
        }
        return selectedFolder
    }

    private var manifestURL: URL {
        wefFolder.appendingPathComponent(manifestName, isDirectory: false)
    }

    private func checkedWefFolder(create: Bool) throws -> URL {
        if create && !FileManager.default.fileExists(atPath: wefFolder.path) {
            try FileManager.default.createDirectory(at: wefFolder, withIntermediateDirectories: false)
        }
        let expected = documentsFolder.appendingPathComponent("wef", isDirectory: true)
        guard canonical(wefFolder).path == expected.path else { throw AccessError.invalidSelection }
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: wefFolder.path, isDirectory: &isDirectory), !isDirectory.boolValue {
            throw AccessError.invalidSelection
        }
        return wefFolder
    }

    func currentData() throws -> Data? {
        _ = try checkedWefFolder(create: false)
        let url = manifestURL
        let attributes: [FileAttributeKey: Any]
        do {
            attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        } catch let error as NSError {
            if error.domain == NSCocoaErrorDomain &&
                (error.code == NSFileReadNoSuchFileError || error.code == NSFileNoSuchFileError) { return nil }
            throw error
        }
        guard attributes[.type] as? FileAttributeType == .typeRegular else { throw AccessError.unexpectedFile }
        guard (attributes[.size] as? NSNumber)?.intValue ?? 0 <= manifestLimit else { throw AccessError.tooLarge }
        return try Data(contentsOf: url)
    }

    func read() throws -> [String: Any] {
        let data = try currentData()
        if originalSnapshot == nil { originalSnapshot = .some(data) }
        var response: [String: Any] = ["ok": true]
        response["data"] = data?.base64EncodedString() as Any? ?? NSNull()
        return response
    }

    private func decode(_ value: Any?) throws -> Data? {
        guard let value = value else { throw AccessError.invalidCommand }
        if value is NSNull { return nil }
        guard let encoded = value as? String, let data = Data(base64Encoded: encoded) else {
            throw AccessError.invalidData
        }
        guard data.count <= manifestLimit else { throw AccessError.tooLarge }
        return data
    }

    func write(_ value: Any?) throws -> [String: Any] {
        guard let data = try decode(value) else { throw AccessError.invalidData }
        _ = try checkedWefFolder(create: true)
        try data.write(to: manifestURL, options: .atomic)
        hasMutation = true
        expectedCurrent = .some(data)
        return ["ok": true]
    }

    func remove(_ value: Any?) throws -> [String: Any] {
        guard let expected = try decode(value) else { throw AccessError.invalidData }
        guard let actual = try currentData() else { return ["ok": true] }
        guard actual == expected else { throw AccessError.conflict }
        try FileManager.default.removeItem(at: manifestURL)
        hasMutation = true
        expectedCurrent = .some(nil)
        return ["ok": true]
    }

    func restore(_ value: Any?) throws -> [String: Any] {
        let snapshot = try decode(value)
        guard let original = originalSnapshot else { throw AccessError.invalidCommand }
        guard snapshot == original else { throw AccessError.invalidData }
        let actual = try currentData()
        if hasMutation {
            guard actual == expectedCurrent! else { throw AccessError.conflict }
        } else {
            guard actual == original else { throw AccessError.conflict }
            return ["ok": true]
        }
        if let snapshot = snapshot {
            _ = try checkedWefFolder(create: true)
            try snapshot.write(to: manifestURL, options: .atomic)
        } else if actual != nil {
            try FileManager.default.removeItem(at: manifestURL)
        }
        hasMutation = true
        expectedCurrent = .some(snapshot)
        return ["ok": true]
    }

    func perform(_ object: [String: Any]) -> [String: Any]? {
        guard let action = object["action"] as? String else { return failure(AccessError.invalidCommand) }
        let allowedKeys: Set<String> = action == "read" || action == "quit" ? ["action"] : ["action", "data"]
        guard Set(object.keys).isSubset(of: allowedKeys) else { return failure(AccessError.invalidCommand) }
        do {
            switch action {
            case "read": return try read()
            case "write": return try write(object["data"])
            case "remove": return try remove(object["data"])
            case "restore": return try restore(object["data"])
            case "quit": return ["ok": true]
            default: return failure(AccessError.invalidCommand)
            }
        } catch {
            return failure(error)
        }
    }
}

private func runSelfTest() throws {
    let temporary = FileManager.default.temporaryDirectory
        .appendingPathComponent("lod-word-folder-test-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: temporary) }
    let documents = temporary.appendingPathComponent("Documents", isDirectory: true)
    try FileManager.default.createDirectory(at: documents, withIntermediateDirectories: true)
    let selected = try FolderSession(selectedFolder: documents, documentsFolder: documents)
    let outside = temporary.appendingPathComponent("Other", isDirectory: true)
    guard allowedFolder(outside, documents: documents) == nil else { throw AccessError.invalidSelection }

    let original = Data("old manifest".utf8)
    let updated = Data("new manifest".utf8)
    let otherFile = documents.appendingPathComponent("wef/keep.txt")
    try FileManager.default.createDirectory(at: otherFile.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data("keep".utf8).write(to: otherFile)
    guard (try selected.read())["data"] as? NSNull != nil else { throw AccessError.invalidData }
    _ = try selected.write(updated.base64EncodedString())
    guard try selected.currentData() == updated else { throw AccessError.invalidData }
    do {
        _ = try selected.remove(original.base64EncodedString())
        throw AccessError.invalidData
    } catch AccessError.conflict {
        // Mismatched expected bytes must not remove the manifest.
    }
    _ = try selected.restore(NSNull())
    guard try selected.currentData() == nil else { throw AccessError.invalidData }
    try original.write(to: documents.appendingPathComponent("wef/" + manifestName))
    let second = try FolderSession(selectedFolder: documents, documentsFolder: documents)
    _ = try second.read()
    _ = try second.write(updated.base64EncodedString())
    _ = try second.restore(original.base64EncodedString())
    guard try second.currentData() == original,
          try Data(contentsOf: otherFile) == Data("keep".utf8) else { throw AccessError.invalidData }
    _ = try second.remove(original.base64EncodedString())
    guard try second.currentData() == nil else { throw AccessError.invalidData }
    print("PASS: folder allowlist, snapshot/write/remove/restore, conflict protection, and unrelated-file preservation.")
}

private func runPickerSession() -> Int32 {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    app.activate(ignoringOtherApps: true)

    let documents = wordDocumentsURL()
    let panel = NSOpenPanel()
    panel.title = "Allow LOD pane to register in Word"
    panel.message = "Choose Word's Documents folder, or its existing wef folder. LOD pane only reads and writes wef/lod-pane.xml."
    panel.prompt = "Allow Access"
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    panel.canCreateDirectories = true
    panel.directoryURL = documents

    guard panel.runModal() == .OK, let selected = panel.url else {
        jsonLine(["ok": false, "error": "Word folder access cancelled."])
        return 2
    }

    do {
        // Open panels already grant access. Unsandboxed apps may return false
        // here because no additional security-scope token is needed.
        let scoped = selected.startAccessingSecurityScopedResource()
        defer { if scoped { selected.stopAccessingSecurityScopedResource() } }
        let session = try FolderSession(selectedFolder: selected, documentsFolder: documents)
        jsonLine(["ok": true])
        while let line = readLine() {
            guard let data = line.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                jsonLine(failure(AccessError.invalidCommand))
                continue
            }
            let response = session.perform(object) ?? ["ok": false, "error": "Invalid command."]
            jsonLine(response)
            if object["action"] as? String == "quit", response["ok"] as? Bool == true { return 0 }
        }
        return 0
    } catch {
        jsonLine(failure(error))
        return 1
    }
}

if CommandLine.arguments.dropFirst().first == "--self-test" {
    do {
        try runSelfTest()
        exit(0)
    } catch {
        fputs("FAIL: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
} else {
    exit(runPickerSession())
}
