// swift-tools-version: 6.0
// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
import PackageDescription

let package = Package(
    name: "GutenbergKGKit",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "GutenbergKGKit", targets: ["GutenbergKGKit"])
    ],
    targets: [
        .target(name: "GutenbergKGKit"),
        .testTarget(name: "GutenbergKGKitTests", dependencies: ["GutenbergKGKit"]),
    ]
)
