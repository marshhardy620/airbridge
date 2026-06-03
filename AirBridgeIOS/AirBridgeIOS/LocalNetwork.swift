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
            let family = interface.ifa_addr.pointee.sa_family
            guard family == UInt8(AF_INET) else { continue }
            let name = String(cString: interface.ifa_name)
            guard name == "en0" || name == "en1" || name == "pdp_ip0" else { continue }

            var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            getnameinfo(
                interface.ifa_addr,
                socklen_t(interface.ifa_addr.pointee.sa_len),
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
