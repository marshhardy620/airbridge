import SwiftUI

@main
struct AirBridgeIOSApp: App {
    @StateObject private var airBridgeService = AirBridgeService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(airBridgeService)
        }
    }
}
