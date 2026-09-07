// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// A short launch splash: logo fade-in, name, tagline, then fade to the real
// UI. Loads Resources/AppIcon-1024.png from this package's own bundle rather
// than either app target's Assets.xcassets, so one image serves both shells.

import SwiftUI

#if canImport(UIKit)
    import UIKit
#elseif canImport(AppKit)
    import AppKit
#endif

/// The bundled 1024pt app icon, loaded once. `nil` only if the resource copy
/// in Package.swift and this name ever drift apart. Shared with AboutView.swift
/// rather than loaded twice.
let appIconImage: Image? = {
    guard let url = Bundle.module.url(forResource: "AppIcon-1024", withExtension: "png") else {
        return nil
    }
    #if canImport(UIKit)
        guard let image = UIImage(contentsOfFile: url.path) else { return nil }
        return Image(uiImage: image)
    #elseif canImport(AppKit)
        guard let image = NSImage(contentsOf: url) else { return nil }
        return Image(nsImage: image)
    #else
        return nil
    #endif
}()

/// Wraps `content` with a splash overlay that fades out after a short hold.
///
/// The hold is fixed rather than tied to `AppModel.loadCorpusPacks()` —
/// corpus load time varies with storage speed and this is meant to read as
/// a brand moment, not a progress indicator. A slow first launch still shows
/// "connecting…" in Settings once the splash clears, same as it always has.
public struct SplashOverlay<Content: View>: View {
    @State private var showSplash = true
    @State private var logoOpacity: Double = 0
    private let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        ZStack {
            content
            if showSplash {
                SplashView()
                    .opacity(logoOpacity)
                    .onAppear {
                        withAnimation(.easeIn(duration: 0.4)) { logoOpacity = 1 }
                        Task {
                            try? await Task.sleep(for: .seconds(2.5))
                            withAnimation(.easeOut(duration: 0.5)) { logoOpacity = 0 }
                            try? await Task.sleep(for: .seconds(0.5))
                            showSplash = false
                        }
                    }
            }
        }
    }
}

private struct SplashView: View {
    var body: some View {
        VStack(spacing: 16) {
            if let appIconImage {
                appIconImage
                    .resizable()
                    .scaledToFit()
                    .frame(width: 120, height: 120)
                    .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
                    .shadow(radius: 8)
            }
            VStack(spacing: 4) {
                Text("The Knowledge Press")
                    .font(.title2.bold())
                Text("A local, source-grounded way to ask better questions of great books.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 280)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.background)
    }
}
