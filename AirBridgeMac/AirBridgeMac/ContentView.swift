import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var service: AirBridgeService
    @State private var messageText = ""
    @State private var manualAddress = ""
    @State private var isImportingFiles = false

    var body: some View {
        NavigationSplitView {
            deviceList
                .navigationSplitViewColumnWidth(min: 260, ideal: 310, max: 360)
        } detail: {
            chatSurface
        }
        .fileImporter(isPresented: $isImportingFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            Task {
                switch result {
                case .success(let urls):
                    await service.sendFiles(urls)
                case .failure(let error):
                    service.statusText = "选择文件失败：\(error.localizedDescription)"
                }
            }
        }
    }

    private var deviceList: some View {
        List {
            Section("本机") {
                VStack(alignment: .leading, spacing: 8) {
                    Label(service.deviceName, systemImage: "macbook.and.iphone")
                        .font(.headline)
                    Text(service.localURL)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .padding(.vertical, 4)
            }

            Section("附近设备") {
                if service.devices.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("暂无设备", systemImage: "dot.radiowaves.left.and.right")
                            .font(.headline)
                        Text("AirBridge 会用广播和邻近网段扫描寻找 Windows、iOS 和 macOS 设备。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 10)
                } else {
                    ForEach(service.devices) { peer in
                        Button {
                            service.select(peer)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "laptopcomputer.and.iphone")
                                    .foregroundStyle(.green)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(peer.name)
                                        .font(.body.weight(.semibold))
                                    Text(peer.endpoint)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if service.selectedPeerID == peer.id {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.green)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Section("手动添加") {
                TextField("例如 192.168.1.8:8765", text: $manualAddress)
                    .textFieldStyle(.roundedBorder)
                Button("添加设备") {
                    Task {
                        await service.addManualPeer(manualAddress)
                        manualAddress = ""
                    }
                }
            }
        }
        .navigationTitle("AirBridge")
    }

    private var chatSurface: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        if service.events.isEmpty {
                            VStack(spacing: 12) {
                                Image(systemName: "paperplane")
                                    .font(.largeTitle)
                                    .foregroundStyle(.secondary)
                                Text("还没有传输记录")
                                    .font(.headline)
                                Text("选择设备后可以发送消息或文件。")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.top, 100)
                        } else {
                            ForEach(service.events) { event in
                                EventBubble(event: event)
                                    .id(event.id)
                            }
                        }
                    }
                    .padding()
                }
                .onChange(of: service.events) { _, events in
                    if let last = events.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }
            Divider()
            composer
        }
        .navigationTitle(service.selectedPeer?.name ?? "选择设备")
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.left.arrow.right.circle.fill")
                .font(.title2)
                .foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 3) {
                Text(service.selectedPeer?.name ?? "未选择设备")
                    .font(.headline)
                Text(service.statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                service.openReceivedFolder()
            } label: {
                Label("打开接收文件夹", systemImage: "folder")
            }
        }
        .padding()
    }

    private var composer: some View {
        VStack(spacing: 10) {
            HStack(alignment: .bottom, spacing: 10) {
                TextField("输入消息...", text: $messageText, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                Button {
                    let text = messageText
                    messageText = ""
                    Task { await service.sendMessage(text) }
                } label: {
                    Image(systemName: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
            }
            HStack {
                Button {
                    isImportingFiles = true
                } label: {
                    Label("选择文件", systemImage: "paperclip")
                }
                .buttonStyle(.bordered)
                Spacer()
                Text("Windows、iPhone/iPad、Mac 需在可互访的局域网内")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.bar)
    }
}

private struct EventBubble: View {
    let event: TransferEvent

    var body: some View {
        HStack {
            if event.direction == .sent {
                Spacer(minLength: 80)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("\(event.direction == .sent ? "我" : event.peerName) · \(event.createdAt.airBridgeShortTime)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                payload
            }
            .padding(12)
            .background(event.direction == .sent ? Color.green.opacity(0.16) : Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            if event.direction == .received {
                Spacer(minLength: 80)
            }
        }
    }

    @ViewBuilder
    private var payload: some View {
        switch event.payload {
        case .message(let text):
            Text(text)
                .textSelection(.enabled)
        case .file(let name, let url, let size):
            HStack(spacing: 10) {
                Image(systemName: "doc.fill")
                    .foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name)
                        .font(.body.weight(.semibold))
                    Text(size.airBridgeFileSize)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let url {
                    Button {
                        NSWorkspace.shared.open(url)
                    } label: {
                        Image(systemName: "arrow.up.forward.app")
                    }
                    .buttonStyle(.borderless)
                }
            }
        case .status(let text):
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AirBridgeService())
}
