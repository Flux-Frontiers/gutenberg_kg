// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Knowledge Press — iPhone and iPad shell.
//
// Everything except this file lives in the KnowledgePressUI package target,
// shared with the Mac app. Answers are written by Apple Foundation Models on
// the device itself, and passages come from the installed corpus packs — with
// both in place the app answers with the network off.
//
// `AdaptiveRootView` picks the iPad's permanent sidebar or the iPhone's
// tabs-plus-sheet shell at launch; see RootViews.swift for why one file
// serves both idioms.

import KnowledgePressUI
import SwiftUI

@main
struct KnowledgePressApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            SplashOverlay {
                AdaptiveRootView()
                    .environment(model)
            }
            .task {
                // Load model weights while the reader is still reading the
                // suggestions, so the first answer starts without a pause.
                model.prewarmOnDevice()
                // Opening the corpus compiles the Core ML embedder, so it
                // happens off the main actor before the first question.
                await model.loadCorpusPacks()
                await model.refreshSidebar()
            }
        }
    }
}
