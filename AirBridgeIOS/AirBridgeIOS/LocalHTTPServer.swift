import Foundation
import Network

final class LocalHTTPServer {
    private weak var service: AirBridgeService?
    private let queue = DispatchQueue(label: "airbridge.ios.http")
    private var listener: NWListener?
    private(set) var port: Int

    init(startingAt preferredPort: Int, service: AirBridgeService) throws {
        self.port = preferredPort
        self.service = service
        self.listener = try Self.makeListener(startingAt: preferredPort, resolvedPort: &port)
    }

    func start() throws {
        guard let listener else { return }
        listener.newConnectionHandler = { [weak self] connection in
            self?.handle(connection)
        }
        listener.start(queue: queue)
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    private static func makeListener(startingAt preferredPort: Int, resolvedPort: inout Int) throws -> NWListener {
        var lastError: Error?
        for candidate in preferredPort...(preferredPort + 100) {
            do {
                let listener = try NWListener(using: .tcp, on: NWEndpoint.Port(rawValue: UInt16(candidate))!)
                resolvedPort = candidate
                return listener
            } catch {
                lastError = error
            }
        }
        throw lastError ?? URLError(.cannotOpenFile)
    }

    private func handle(_ connection: NWConnection) {
        var data = Data()
        connection.stateUpdateHandler = { state in
            if case .failed = state {
                connection.cancel()
            }
        }
        connection.start(queue: queue)

        func receiveMore() {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 1024 * 256) { chunk, _, isComplete, error in
                if let chunk {
                    data.append(chunk)
                }
                if error != nil || isComplete {
                    connection.cancel()
                    return
                }
                if let request = HTTPRequest(data: data), request.isComplete {
                    self.route(request, on: connection)
                } else {
                    receiveMore()
                }
            }
        }

        receiveMore()
    }

    private func route(_ request: HTTPRequest, on connection: NWConnection) {
        Task { @MainActor in
            guard let service else {
                self.respond(status: 500, body: Data(), connection: connection)
                return
            }

            do {
                switch (request.method, request.path) {
                case ("GET", "/api/state"):
                    let body = try JSONEncoder().encode(service.statePayload())
                    self.respondJSON(status: 200, body: body, connection: connection)

                case ("POST", "/api/inbox/message"):
                    let object = try JSONSerialization.jsonObject(with: request.body) as? [String: Any]
                    let fromName = object?["fromName"] as? String ?? object?["from_name"] as? String ?? "Nearby device"
                    let text = object?["text"] as? String ?? ""
                    service.receiveMessage(fromName: fromName, text: text)
                    self.respondJSON(status: 200, object: ["ok": true], connection: connection)

                case ("POST", "/api/inbox/file"):
                    guard let upload = MultipartUpload(request: request) else {
                        self.respondJSON(status: 400, object: ["ok": false, "error": "Invalid multipart body"], connection: connection)
                        return
                    }
                    try service.receiveFile(fromName: upload.fromName, filename: upload.filename, data: upload.fileData)
                    self.respondJSON(status: 200, object: ["ok": true, "filename": upload.filename, "size": upload.fileData.count], connection: connection)

                default:
                    self.respondJSON(status: 404, object: ["ok": false, "error": "Not found"], connection: connection)
                }
            } catch {
                self.respondJSON(status: 500, object: ["ok": false, "error": error.localizedDescription], connection: connection)
            }
        }
    }

    private func respondJSON(status: Int, object: [String: Any], connection: NWConnection) {
        let body = (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
        respondJSON(status: status, body: body, connection: connection)
    }

    private func respondJSON(status: Int, body: Data, connection: NWConnection) {
        respond(status: status, body: body, contentType: "application/json; charset=utf-8", connection: connection)
    }

    private func respond(status: Int, body: Data, contentType: String = "text/plain; charset=utf-8", connection: NWConnection) {
        let reason = status == 200 ? "OK" : status == 204 ? "No Content" : status == 400 ? "Bad Request" : status == 404 ? "Not Found" : "Server Error"
        let header = "HTTP/1.1 \(status) \(reason)\r\n"
            + "Content-Type: \(contentType)\r\n"
            + "Content-Length: \(body.count)\r\n"
            + "Access-Control-Allow-Origin: *\r\n"
            + "Access-Control-Allow-Methods: GET,POST,OPTIONS\r\n"
            + "Access-Control-Allow-Headers: Content-Type\r\n"
            + "Connection: close\r\n"
            + "\r\n"
        var response = Data(header.utf8)
        response.append(body)
        connection.send(content: response, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}

struct HTTPRequest {
    let method: String
    let path: String
    let headers: [String: String]
    let body: Data
    let isComplete: Bool

    init?(data: Data) {
        guard let separator = data.range(of: Data("\r\n\r\n".utf8)) else { return nil }
        let headerData = data[..<separator.lowerBound]
        guard let headerText = String(data: headerData, encoding: .utf8) else { return nil }
        let lines = headerText.components(separatedBy: "\r\n")
        guard let first = lines.first else { return nil }
        let parts = first.split(separator: " ", maxSplits: 2).map(String.init)
        guard parts.count >= 2 else { return nil }

        var parsedHeaders: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let key = String(line[..<colon]).lowercased()
            let value = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
            parsedHeaders[key] = value
        }

        let bodyStart = separator.upperBound
        let expectedLength = Int(parsedHeaders["content-length"] ?? "0") ?? 0
        let availableLength = data.distance(from: bodyStart, to: data.endIndex)
        method = parts[0]
        path = parts[1]
        headers = parsedHeaders
        body = availableLength > 0 ? Data(data[bodyStart...].prefix(expectedLength)) : Data()
        isComplete = availableLength >= expectedLength
    }
}

struct MultipartUpload {
    let fromName: String
    let filename: String
    let fileData: Data

    init?(request: HTTPRequest) {
        guard let contentType = request.headers["content-type"],
              let boundaryRange = contentType.range(of: "boundary=") else {
            return nil
        }
        let boundary = String(contentType[boundaryRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
        let marker = Data("--\(boundary)".utf8)
        let chunks = request.body.components(separatedBy: marker)

        var fields: [String: String] = [:]
        var foundFilename = "file"
        var foundData = Data()

        for chunk in chunks {
            guard let headerEnd = chunk.range(of: Data("\r\n\r\n".utf8)) else { continue }
            let headerData = chunk[..<headerEnd.lowerBound]
            guard let headerText = String(data: headerData, encoding: .utf8) else { continue }
            var partBody = Data(chunk[headerEnd.upperBound...])
            if partBody.hasSuffix(Data("\r\n".utf8)) {
                partBody.removeLast(2)
            }
            if partBody.hasSuffix(Data("\r\n--".utf8)) {
                partBody.removeLast(4)
            }

            guard let name = Self.capture(#"name="([^"]+)""#, in: headerText) else { continue }
            if name == "file" {
                foundFilename = Self.capture(#"filename="([^"]+)""#, in: headerText) ?? "file"
                foundData = partBody
            } else if let value = String(data: partBody, encoding: .utf8) {
                fields[name] = value
            }
        }

        guard !foundData.isEmpty else { return nil }
        fromName = fields["from_name"] ?? fields["fromName"] ?? "Nearby device"
        filename = foundFilename
        fileData = foundData
    }

    private static func capture(_ pattern: String, in text: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else {
            return nil
        }
        return String(text[range])
    }
}

private extension Data {
    func components(separatedBy separator: Data) -> [Data] {
        guard !separator.isEmpty else { return [self] }
        var parts: [Data] = []
        var start = startIndex
        while let range = self[start...].range(of: separator) {
            parts.append(Data(self[start..<range.lowerBound]))
            start = range.upperBound
        }
        parts.append(Data(self[start...]))
        return parts
    }
}
