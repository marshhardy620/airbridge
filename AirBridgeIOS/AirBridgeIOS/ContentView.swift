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
        } detail: {
            chatSurface
        }
        .fileImporter(isPresented: $isImportingFiles, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            Task {
                switch result {
                case .success(let urls):
                    await service.sendFiles(urls)
                case .failure(let error):
                    service.statusText = "File selection failed: \(error.localizedDescription)"
                }
            }
        }
    }

    private var deviceList: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Label(service.deviceName, systemImage: "iphone.gen3")
                        .font(.headline)
                    Text(service.localURL)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .padding(.vertical, 4)
            } header: {
                Text("This Device")
            }

            Section {
                if service.devices.isEmpty {
                    ContentUnavailableView("No Devices", systemImage: "dot.radiowaves.left.and.right", description: Text("Connect Windows AirBridge and this device to the same Wi-Fi."))
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
            } header: {
                Text("Nearby Devices")
            }

            Section("Add Manually") {
                TextField("e.g. 192.168.1.8:8765", text: $manualAddress)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                Button("Add Device") {
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
                            ContentUnavailableView("No transfer history yet", systemImage: "paperplane", description: Text("Select a device to send messages or files."))
                                .padding(.top, 80)
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
        .navigationTitle(service.selectedPeer?.name ?? "Select Device")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.left.arrow.right.circle.fill")
                .font(.title2)
                .foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 3) {
                Text(service.selectedPeer?.name ?? "No device selected")
                    .font(.headline)
                Text(service.statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                service.openReceivedFolder()
            } label: {
                Label("Received Files", systemImage: "folder")
            }
            .labelStyle(.iconOnly)
        }
        .padding()
    }

    private var composer: some View {
        VStack(spacing: 10) {
            HStack(alignment: .bottom, spacing: 10) {
                TextField("Type a message...", text: $messageText, axis: .vertical)
                    .lineLimit(1...4)
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
                    Label("Choose Files", systemImage: "paperclip")
                }
                .buttonStyle(.bordered)
                Spacer()
                Text("Windows and iPhone/iPad must be on the same Wi-Fi")
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
                Spacer(minLength: 50)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("\(event.direction == .sent ? "Me" : event.peerName) · \(event.createdAt.airBridgeShortTime)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                payload
            }
            .padding(12)
            .background(event.direction == .sent ? Color.green.opacity(0.16) : Color(.secondarySystemGroupedBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            if event.direction == .received {
                Spacer(minLength: 50)
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
                    ShareLink(item: url) {
                        Image(systemName: "square.and.arrow.up")
                    }
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
