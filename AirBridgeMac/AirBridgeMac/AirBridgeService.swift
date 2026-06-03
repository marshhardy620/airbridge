import AppKit
import Foundation
import Network
import SwiftUI
import UniformTypeIdentifiers

final class AirBridgeService: ObservableObject {
    @Published private(set) var devices: [NearbyDevice] = []
    @Published private(set) var events: [TransferEvent] = []
    @Published var selectedPeerID: String?
    @Published var statusText = "Starting AirBridge..."

    private let appName = "AirBridge"
    private let appVersion = "0.1.0"
    private let discoveryPort: UInt16 = 45678
    private let preferredHTTPPort = 8765
    private let deviceID = UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12).description
    private let queue = DispatchQueue(label: "airbridge.mac.network", qos: .userInitiated)
    private var discoverySocket: Int32 = -1
    private var isRunning = false
    private var broadcastTimer: DispatchSourceTimer?
    private var scanTimer: DispatchSourceTimer?
    private var httpServer: LocalHTTPServer?
    private let receivedDirectory: URL

    init() {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        receivedDirectory = (downloads ?? FileManager.default.homeDirectoryForCurrentUser)
            .appendingPathComponent("AirBridge Received", isDirectory: true)
        try? FileManager.default.createDirectory(at: receivedDirectory, withIntermediateDirectories: true)
        start()
    }

    deinit {
        stop()
    }

    var deviceName: String {
        Host.current().localizedName ?? "Mac-\(deviceID.prefix(4))"
    }

    var host: String {
        LocalNetwork.currentIPv4Address() ?? "127.0.0.1"
    }

    var port: Int {
        httpServer?.port ?? preferredHTTPPort
    }

    var localURL: String {
        "http://\(host):\(port)"
    }

    var selectedPeer: NearbyDevice? {
        guard let selectedPeerID else { return nil }
        return devices.first { $0.id == selectedPeerID }
    }

    func start() {
        guard !isRunning else { return }
        isRunning = true
        do {
            httpServer = try LocalHTTPServer(startingAt: preferredHTTPPort, service: self)
            try httpServer?.start()
            startDiscovery()
            startNearbySubnetScan()
            statusText = "Finding nearby devices..."
        } catch {
            statusText = "Startup failed: \(error.localizedDescription)"
        }
    }

    func stop() {
        isRunning = false
        broadcastTimer?.cancel()
        broadcastTimer = nil
        scanTimer?.cancel()
        scanTimer = nil
        if discoverySocket >= 0 {
            close(discoverySocket)
            discoverySocket = -1
        }
        httpServer?.stop()
    }

    func select(_ peer: NearbyDevice) {
        selectedPeerID = peer.id
        statusText = "Selected \(peer.name)"
    }

    func addManualPeer(_ rawText: String) async {
        var value = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        if !value.hasPrefix("http://") && !value.hasPrefix("https://") {
            value = "http://\(value)"
        }
        guard let url = URL(string: value), let host = url.host else {
            statusText = "Invalid address"
            return
        }
        let port = url.port ?? 80
        do {
            let stateURL = URL(string: "http://\(host):\(port)/api/state")!
            let (data, _) = try await URLSession.shared.data(from: stateURL)
            let state = try JSONDecoder().decode(AirBridgeStatePayload.self, from: data)
            let peer = NearbyDevice(
                id: state.device.id,
                name: state.device.name,
                host: state.device.host,
                port: state.device.port,
                url: state.device.url,
                source: "manual",
                lastSeen: Date()
            )
            upsert(peer)
            selectedPeerID = peer.id
            statusText = "Device added"
        } catch {
            statusText = "Add failed: \(error.localizedDescription)"
        }
    }

    func sendMessage(_ text: String) async {
        guard let peer = selectedPeer else {
            statusText = "Select a device first"
            return
        }
        let cleanText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanText.isEmpty else {
            statusText = "Enter a message first"
            return
        }
        do {
            let url = URL(string: "http://\(peer.host):\(peer.port)/api/inbox/message")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: [
                "fromId": deviceID,
                "fromName": deviceName,
                "text": cleanText,
                "createdAt": Int64(Date().timeIntervalSince1970 * 1000)
            ])
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            events.append(TransferEvent(peerName: peer.name, direction: .sent, payload: .message(cleanText)))
            statusText = "Message sent"
        } catch {
            statusText = "Message send failed: \(error.localizedDescription)"
        }
    }

    func sendFiles(_ urls: [URL]) async {
        guard let peer = selectedPeer else {
            statusText = "Select a device first"
            return
        }
        for url in urls {
            await sendFile(url, to: peer)
        }
    }

    func openReceivedFolder() {
        NSWorkspace.shared.open(receivedDirectory)
    }

    func receiveMessage(fromName: String, text: String) {
        events.append(TransferEvent(peerName: fromName, direction: .received, payload: .message(text)))
        statusText = "Received message from \(fromName)"
    }

    func receiveFile(fromName: String, filename: String, data: Data) throws {
        let destination = uniqueURL(for: receivedDirectory.appendingPathComponent(filename))
        try data.write(to: destination, options: .atomic)
        events.append(
            TransferEvent(
                peerName: fromName,
                direction: .received,
                payload: .file(name: destination.lastPathComponent, url: destination, size: Int64(data.count))
            )
        )
        statusText = "File saved"
    }

    func statePayload() -> AirBridgeStatePayload {
        AirBridgeStatePayload(
            app: appName,
            version: appVersion,
            device: .init(
                id: deviceID,
                name: deviceName,
                host: host,
                port: port,
                url: localURL,
                receivedDir: receivedDirectory.path
            ),
            peers: devices.map {
                NearbyDevicePayload(
                    id: $0.id,
                    name: $0.name,
                    host: $0.host,
                    port: $0.port,
                    url: $0.url,
                    lastSeen: Int64($0.lastSeen.timeIntervalSince1970 * 1000),
                    source: $0.source
                )
            },
            inbox: []
        )
    }

    private func sendFile(_ url: URL, to peer: NearbyDevice) async {
        do {
            let data = try Data(contentsOf: url)
            let boundary = "airbridge-\(UUID().uuidString)"
            var request = URLRequest(url: URL(string: "http://\(peer.host):\(peer.port)/api/inbox/file")!)
            request.httpMethod = "POST"
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.httpBody = MultipartFormData(boundary: boundary)
                .field("from_id", deviceID)
                .field("from_name", deviceName)
                .field("created_at", "\(Int64(Date().timeIntervalSince1970 * 1000))")
                .file("file", filename: url.lastPathComponent, data: data)
                .body
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            events.append(
                TransferEvent(
                    peerName: peer.name,
                    direction: .sent,
                    payload: .file(name: url.lastPathComponent, url: url, size: Int64(data.count))
                )
            )
            statusText = "File sent"
        } catch {
            statusText = "File send failed: \(error.localizedDescription)"
        }
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    private func startDiscovery() {
        queue.async { [weak self] in
            guard let self else { return }
            self.configureDiscoverySocket()
            self.listenForPeers()
        }

        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now(), repeating: .milliseconds(2500))
        timer.setEventHandler { [weak self] in
            self?.broadcastPresence()
        }
        timer.resume()
        broadcastTimer = timer
    }

    private func startNearbySubnetScan() {
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 3, repeating: .seconds(35))
        timer.setEventHandler { [weak self] in
            self?.scanNearbySubnets()
        }
        timer.resume()
        scanTimer = timer
    }

    private func configureDiscoverySocket() {
        discoverySocket = socket(AF_INET, SOCK_DGRAM.rawValue, IPPROTO_UDP)
        guard discoverySocket >= 0 else { return }
        var yes: Int32 = 1
        setsockopt(discoverySocket, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        setsockopt(discoverySocket, SOL_SOCKET, SO_BROADCAST, &yes, socklen_t(MemoryLayout<Int32>.size))

        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = discoveryPort.bigEndian
        address.sin_addr = in_addr(s_addr: INADDR_ANY.bigEndian)
        withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                _ = bind(discoverySocket, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
    }

    private func broadcastPresence() {
        guard discoverySocket >= 0 else { return }
        let payload = AirBridgePeerPayload(
            app: appName,
            version: appVersion,
            id: deviceID,
            name: deviceName,
            host: host,
            port: port,
            url: localURL,
            ts: Int64(Date().timeIntervalSince1970 * 1000)
        )
        guard let data = try? JSONEncoder().encode(payload) else { return }
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = discoveryPort.bigEndian
        address.sin_addr.s_addr = inet_addr("255.255.255.255")
        data.withUnsafeBytes { rawBuffer in
            withUnsafePointer(to: &address) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    _ = sendto(discoverySocket, rawBuffer.baseAddress, data.count, 0, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
        }
    }

    private func listenForPeers() {
        var buffer = [UInt8](repeating: 0, count: 4096)
        while isRunning && discoverySocket >= 0 {
            var remote = sockaddr_in()
            var remoteLength = socklen_t(MemoryLayout<sockaddr_in>.size)
            let count = buffer.withUnsafeMutableBytes { rawBuffer in
                withUnsafeMutablePointer(to: &remote) { pointer in
                    pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                        recvfrom(discoverySocket, rawBuffer.baseAddress, buffer.count, 0, $0, &remoteLength)
                    }
                }
            }
            guard count > 0 else { continue }
            let data = Data(buffer.prefix(Int(count)))
            guard let payload = try? JSONDecoder().decode(AirBridgePeerPayload.self, from: data),
                  payload.app == appName,
                  payload.id != deviceID else {
                continue
            }
            let remoteHost = String(cString: inet_ntoa(remote.sin_addr))
            let peer = NearbyDevice(
                id: payload.id,
                name: payload.name.isEmpty ? "Nearby device" : payload.name,
                host: payload.host.hasPrefix("127.") ? remoteHost : payload.host,
                port: payload.port,
                url: payload.url,
                source: "auto",
                lastSeen: Date()
            )
            DispatchQueue.main.async {
                self.upsert(peer)
            }
        }
    }

    private func scanNearbySubnets() {
        let hosts = LocalNetwork.nearbyIPv4Hosts(from: host, radius: 1)
        let ports = [port, 8765, 8766, 8767].uniqued()
        for targetHost in hosts {
            for targetPort in ports {
                probe(host: targetHost, port: targetPort)
            }
        }
    }

    private func probe(host: String, port: Int) {
        guard let url = URL(string: "http://\(host):\(port)/api/state") else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 0.45
        URLSession.shared.dataTask(with: request) { data, _, _ in
            guard let data,
                  let payload = try? JSONDecoder().decode(AirBridgeStatePayload.self, from: data),
                  payload.app == self.appName,
                  payload.device.id != self.deviceID else {
                return
            }
            let peer = NearbyDevice(
                id: payload.device.id,
                name: payload.device.name,
                host: payload.device.host.hasPrefix("127.") ? host : payload.device.host,
                port: payload.device.port,
                url: payload.device.url,
                source: "scan",
                lastSeen: Date()
            )
            DispatchQueue.main.async {
                self.upsert(peer)
            }
        }.resume()
    }

    private func upsert(_ peer: NearbyDevice) {
        if let index = devices.firstIndex(where: { $0.id == peer.id }) {
            devices[index] = peer
        } else {
            devices.append(peer)
        }
        devices.removeAll { Date().timeIntervalSince($0.lastSeen) > 20 && $0.source != "manual" }
        devices.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        if selectedPeerID == nil {
            selectedPeerID = devices.first?.id
        }
        if devices.isEmpty {
            statusText = "Finding nearby devices..."
        }
    }

    private func uniqueURL(for url: URL) -> URL {
        if !FileManager.default.fileExists(atPath: url.path) {
            return url
        }
        let directory = url.deletingLastPathComponent()
        let stem = url.deletingPathExtension().lastPathComponent
        let ext = url.pathExtension
        for index in 1..<10_000 {
            let name = ext.isEmpty ? "\(stem) (\(index))" : "\(stem) (\(index)).\(ext)"
            let candidate = directory.appendingPathComponent(name)
            if !FileManager.default.fileExists(atPath: candidate.path) {
                return candidate
            }
        }
        return directory.appendingPathComponent("\(UUID().uuidString)-\(url.lastPathComponent)")
    }
}

private extension Array where Element: Hashable {
    func uniqued() -> [Element] {
        var seen = Set<Element>()
        return filter { seen.insert($0).inserted }
    }
}
