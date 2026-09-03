// swift-tools-version: 6.0
// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
import PackageDescription

// iOS 18 / macOS 14 are the deployment floors so the thin client still builds
// on current systems; the Foundation Models path is gated to 26 at the call
// site (see Synthesis/OnDeviceSynthesis.swift) rather than raised here, and
// Private Cloud Compute to 27 (see Synthesis/PrivateCloudSynthesis.swift).
let package = Package(
    name: "GutenbergKGKit",
    platforms: [.macOS(.v14), .iOS(.v18)],
    products: [
        .library(name: "GutenbergKGKit", targets: ["GutenbergKGKit"]),
        .library(name: "KnowledgePressUI", targets: ["KnowledgePressUI"]),
        .executable(name: "KnowledgePress", targets: ["KnowledgePress"]),
    ],
    targets: [
        .target(name: "GutenbergKGKit"),
        // Shared SwiftUI. Both shells — the macOS executable below and the
        // iOS app target in app/ios — build their window from this.
        .target(name: "KnowledgePressUI", dependencies: ["GutenbergKGKit"]),
        .executableTarget(name: "KnowledgePress", dependencies: ["KnowledgePressUI"]),
        .testTarget(
            name: "GutenbergKGKitTests",
            dependencies: ["GutenbergKGKit"],
            // The real bge-small vocabulary and the tokens Python's
            // BertTokenizer produces from it — see TokenizerParityTests.
            resources: [.copy("Fixtures")]),
    ]
)
