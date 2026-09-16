// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// The Knowledge Press — macOS shell.
// Run from app/GutenbergKGKit with:  swift run KnowledgePress
//
// Answers come from Apple Foundation Models when the Mac can run them
// (macOS 26 on Apple silicon), and passages from the corpus packs when they
// are installed — `gutenkg export-swift` builds them. With no packs the app
// falls back to the worker, so `make up` at the repo root is needed then.

import AppKit
import GutenbergKGKit
import KnowledgePressUI
import SwiftUI

@main
struct KnowledgePressApp: App {
    @State private var model = AppModel()
    @Environment(\.openWindow) private var openWindow

    init() {
        // `KnowledgePress --ask "question" [--corpus all] [--engine privateCloud]`
        // answers once on stdout and exits. Run the binary inside the bundle
        // directly, not via `open`, so stdout is the terminal; the bundle is
        // what carries the provisioning profile Private Cloud Compute needs,
        // which is the whole reason this exists -- `swift run` cannot.
        if let ask = HeadlessAsk(arguments: CommandLine.arguments) {
            NSApplication.shared.setActivationPolicy(.prohibited)
            Task { @MainActor in
                let model = AppModel()
                await model.loadCorpusPacks()
                let result = await model.answerHeadless(
                    ask.question, corpus: ask.corpus, engine: ask.engine, tuning: ask.tuning)
                print(result.render())
                exit(result.failure == nil ? 0 : 1)
            }
            return
        }
        // Running via `swift run` (no app bundle): become a regular foreground
        // app so the window appears and takes focus.
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    var body: some Scene {
        WindowGroup("The Knowledge Press") {
            SplashOverlay {
                MacRootView()
                    .environment(model)
            }
            .frame(minWidth: 900, minHeight: 600)
            .task {
                model.prewarmOnDevice()
                await model.loadCorpusPacks()
                await model.refreshSidebar()
            }
        }
        .commands {
            // Replaces the system-supplied "About KnowledgePress" (which
            // would otherwise show a generic panel with no build-specific
            // info) with the same AboutView the iOS row presents.
            CommandGroup(replacing: .appInfo) {
                Button("About The Knowledge Press") { openWindow(id: "about") }
            }
            CommandGroup(after: .newItem) {
                Button("New Chat") { model.newConversation() }
                    .keyboardShortcut("n")
                    .disabled(!model.canStartNewChat)
            }
            // Replaces the system Help item, which would otherwise look for a
            // help book this app does not ship and open a browser to nothing.
            CommandGroup(replacing: .help) {
                Button("The Knowledge Press Help") { openWindow(id: "help") }
                    .keyboardShortcut("?", modifiers: [.command])
            }
        }

        // The standard Settings window, which is what makes Cmd-comma and
        // the app menu work without wiring either by hand. Engine and scope
        // are omitted: MacRootView's sidebar owns them.
        Settings {
            SettingsView(showsEngineAndScope: false)
                .environment(model)
                .frame(width: 420, height: 560)
        }

        Window("About The Knowledge Press", id: "about") {
            AboutView()
                .environment(model)
        }
        .windowResizability(.contentSize)

        // A window rather than a sheet: help is something to keep open beside
        // Settings while changing a control, not something to dismiss before
        // acting on what it said.
        Window("The Knowledge Press Help", id: "help") {
            HelpView()
                .environment(model)
                .frame(minWidth: 520, minHeight: 480)
        }
    }
}

/// The `--ask` command line, or nil when the app was launched normally.
///
///     --ask QUESTION [--corpus all] [--engine privateCloud|onDevice]
///           [--temperature 0.2] [--greedy] [--cap N]
///           [--instructions guide|workerParity] [--permissive]
///
/// Any tuning flag makes the run use `SynthesisTuning.default` plus the
/// flags given, ignoring what the app has stored; with none, the stored
/// settings apply, as they would in the chat.
struct HeadlessAsk {
    let question: String
    var corpus = "all"
    var engine = AnswerEngine.privateCloud
    var tuning: SynthesisTuning?

    init?(arguments: [String]) {
        func value(after flag: String) -> String? {
            guard let i = arguments.firstIndex(of: flag), i + 1 < arguments.count else { return nil }
            return arguments[i + 1]
        }
        func fail(_ message: String) -> Never {
            FileHandle.standardError.write(Data((message + "\n").utf8))
            exit(2)
        }
        guard let question = value(after: "--ask") else { return nil }
        self.question = question
        if let c = value(after: "--corpus") { corpus = c }
        if let e = value(after: "--engine") {
            guard let parsed = AnswerEngine(rawValue: e) else {
                fail("unknown --engine; one of: \(AnswerEngine.allCases.map(\.rawValue))")
            }
            engine = parsed
        }

        var tuned = SynthesisTuning.default
        var any = false
        if let t = value(after: "--temperature") {
            guard let parsed = Double(t), (0...1).contains(parsed) else { fail("--temperature wants 0...1") }
            tuned.temperature = parsed
            any = true
        }
        if arguments.contains("--greedy") { tuned.greedy = true; any = true }
        if let c = value(after: "--cap") {
            guard let parsed = Int(c), parsed >= 1 else { fail("--cap wants a positive integer") }
            tuned.maxPassagesPerSource = parsed
            any = true
        }
        if let i = value(after: "--instructions") {
            guard let parsed = SynthesisTuning.Instructions(rawValue: i) else {
                fail("unknown --instructions; one of: \(SynthesisTuning.Instructions.allCases.map(\.rawValue))")
            }
            tuned.instructions = parsed
            any = true
        }
        if arguments.contains("--permissive") { tuned.permissiveGuardrails = true; any = true }
        if any { tuning = tuned }
    }
}
