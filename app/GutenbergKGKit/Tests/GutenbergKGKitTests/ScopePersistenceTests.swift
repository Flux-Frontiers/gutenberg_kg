// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The genre scope: that a narrowed corpus survives a relaunch.
//
// This is the same defect WorkerURLTests describes, left in a second
// property. `corpus` was a plain stored value, so every launch reset the
// scope to "all" -- the worst setting for a focused question, because an
// unscoped search spreads the on-device context budget over every book plus
// the diaries and leaves only a handful of passages for the answer. The
// reader's narrowing was discarded silently, and the only symptom was a
// worse answer.

import Foundation
import Testing

@testable import KnowledgePressUI

@MainActor
@Suite("Corpus scope persistence")
struct ScopePersistenceTests {

    /// A scratch defaults domain per test, so nothing touches the real one
    /// and tests cannot see each other's writes.
    private func withScratchDefaults(_ body: (UserDefaults) throws -> Void) rethrows {
        let name = "ScopePersistenceTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        let previous = AppModel.defaults
        AppModel.defaults = defaults
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: name)
        }
        try body(defaults)
    }

    @Test("a chosen scope survives being read back into a new model")
    func scopePersists() {
        withScratchDefaults { _ in
            let first = AppModel()
            first.corpus = "world-literature"

            // A fresh model is what a relaunch produces.
            let second = AppModel()
            #expect(second.corpus == "world-literature")
        }
    }

    @Test("the stored scope is what a later launch reads, not the default")
    func storedScopeBeatsTheDefault() {
        withScratchDefaults { defaults in
            defaults.set("philosophy", forKey: AppModel.corpusKey)
            #expect(AppModel.initialCorpus() == "philosophy")
        }
    }

    @Test("an empty stored scope falls through to the whole corpus")
    func emptyStoredScopeIsIgnored() {
        withScratchDefaults { defaults in
            defaults.set("", forKey: AppModel.corpusKey)
            #expect(AppModel.initialCorpus() == "all")
        }
    }

    @Test("with nothing stored the scope is the whole corpus")
    func defaultScopeIsEverything() {
        withScratchDefaults { _ in
            #expect(AppModel.initialCorpus() == "all")
        }
    }
}
