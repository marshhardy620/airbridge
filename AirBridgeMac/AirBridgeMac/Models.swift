import Foundation

struct NearbyDevice: Identifiable, Hashable {
    let id: String
    let name: String
    let host: String
    let port: Int
    let url: String
    let source: String
    let lastSeen: Date

    var endpoint: String {
        "\(host):\(port)"
    }
}

struct TransferEvent: Identifiable, Hashable {
    enum Direction: Hashable {
        case sent
        case received
    }

    enum Payload: Hashable {
        case message(String)
        case file(name: String, url: URL?, size: Int64)
        case status(String)
    }

    let id = UUID()
    let peerName: String
    let direction: Direction
    let payload: Payload
    let createdAt = Date()
}

extension Date {
    var airBridgeShortTime: String {
        formatted(date: .omitted, time: .shortened)
    }
}

extension Int64 {
    var airBridgeFileSize: String {
        ByteCountFormatter.string(fromByteCount: self, countStyle: .file)
    }
}

struct AirBridgePeerPayload: Codable {
    let app: String
    let version: String
    let id: String
    let name: String
    let host: String
    let port: Int
    let url: String
    let ts: Int64
}

struct AirBridgeStatePayload: Codable {
    struct AppDevice: Codable {
        let id: String
        let name: String
        let host: String
        let port: Int
        let url: String
        let receivedDir: String
    }

    let app: String
    let version: String
    let device: AppDevice
    let peers: [NearbyDevicePayload]
    let inbox: [String]
}

struct NearbyDevicePayload: Codable {
    let id: String
    let name: String
    let host: String
    let port: Int
    let url: String
    let lastSeen: Int64
    let source: String
}
