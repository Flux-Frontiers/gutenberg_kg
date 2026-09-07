// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// About screen. Reached differently per platform, on purpose — iOS/iPadOS
// present it as a sheet from a Settings row, the ordinary place a phone app
// keeps version/legal info; macOS replaces the system-supplied "About"
// command in the app menu, the ordinary place a Mac app keeps it. See
// RootViews.swift's `AdaptiveRootView` doc comment for the same reasoning
// applied to layout.

import SwiftUI

public struct AboutView: View {
    @Environment(AppModel.self) private var model

    public init() {}

    public var body: some View {
        VStack(spacing: 20) {
            if let appIconImage {
                appIconImage
                    .resizable()
                    .scaledToFit()
                    .frame(width: 96, height: 96)
                    .clipShape(RoundedRectangle(cornerRadius: 21, style: .continuous))
                    .shadow(radius: 4)
            }

            VStack(spacing: 4) {
                Text("The Knowledge Press")
                    .font(.title2.bold())
                Text(AppVersion.display)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Text("A local, source-grounded way to ask better questions of great books.")
                .font(.callout)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .frame(maxWidth: 320)

            Divider()

            VStack(spacing: 6) {
                Text(model.statsCaption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Link(
                    "github.com/Flux-Frontiers/gutenberg_kg",
                    destination: URL(string: "https://github.com/Flux-Frontiers/gutenberg_kg")!
                )
                .font(.caption)
            }

            Spacer(minLength: 0)

            Text("© 2026 Eric G. Suchanek, PhD — Flux-Frontiers\nElastic License 2.0 · texts are public domain")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        #if os(macOS)
            .frame(width: 360, height: 420)
        #endif
    }
}
