import SwiftUI

@main
struct AirBridgeMacApp: App {
    @StateObject private var airBridgeService = AirBridgeService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(airBridgeService)
                .frame(minWidth: 980, minHeight: 680)
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(after: .appInfo) {
                Button("打开接收文件夹") {
                    airBridgeService.openReceivedFolder()
                }
            }
        }
    }
}
