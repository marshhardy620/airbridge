import Foundation

enum LocalNetwork {
    static func currentIPv4Address() -> String? {
        var address: String?
        var interfaces: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&interfaces) == 0, let first = interfaces else {
            return nil
        }
        defer { freeifaddrs(interfaces) }

        var pointer: UnsafeMutablePointer<ifaddrs>? = first
        while let current = pointer {
            defer { pointer = current.pointee.ifa_next }
            let interface = current.pointee
            guard let socketAddress = interface.ifa_addr else { continue }
            let family = socketAddress.pointee.sa_family
            guard family == UInt8(AF_INET) else { continue }
            let name = String(cString: interface.ifa_name)
            guard name == "en0" || name == "en1" || name == "bridge100" else { continue }

            var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            getnameinfo(
                socketAddress,
                socklen_t(socketAddress.pointee.sa_len),
                &hostname,
                socklen_t(hostname.count),
                nil,
                0,
                NI_NUMERICHOST
            )
            let candidate = String(cString: hostname)
            if !candidate.hasPrefix("127.") {
                address = candidate
                break
            }
        }
        return address
    }

    static func nearbyIPv4Hosts(from address: String, radius: Int) -> [String] {
        let parts = address.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4, parts[0] != 127 else { return [] }

        let scanRadius = max(0, min(radius, 4))
        let thirdOctets = max(0, parts[2] - scanRadius)...min(254, parts[2] + scanRadius)
        let prefixes: [String]
        if parts[0] == 10 || (parts[0] == 172 && (16...31).contains(parts[1])) || (parts[0] == 192 && parts[1] == 168) {
            prefixes = thirdOctets.map { "\(parts[0]).\(parts[1]).\($0)" }
        } else {
            prefixes = ["\(parts[0]).\(parts[1]).\(parts[2])"]
        }

        var hosts: [String] = []
        for prefix in prefixes {
            for last in 1..<255 {
                let host = "\(prefix).\(last)"
                if host != address {
                    hosts.append(host)
                }
            }
        }
        return hosts
    }
}

struct MultipartFormData {
    private let boundary: String
    private(set) var body = Data()

    init(boundary: String) {
        self.boundary = boundary
    }

    func field(_ name: String, _ value: String) -> MultipartFormData {
        var copy = self
        copy.body.append(Data("--\(boundary)\r\n".utf8))
        copy.body.append(Data("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".utf8))
        copy.body.append(Data(value.utf8))
        copy.body.append(Data("\r\n".utf8))
        return copy
    }

    func file(_ name: String, filename: String, data: Data) -> MultipartFormData {
        var copy = self
        copy.body.append(Data("--\(boundary)\r\n".utf8))
        copy.body.append(Data("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".utf8))
        copy.body.append(Data("Content-Type: application/octet-stream\r\n\r\n".utf8))
        copy.body.append(data)
        copy.body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return copy
    }
}
