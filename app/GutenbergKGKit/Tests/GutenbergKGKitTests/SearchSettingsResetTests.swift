// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Resetting the three search sliders.
//
// The numbers live in one place now. Before `SearchDefaults` they were
// written inline on the properties, so a reset would have had to restate
// them -- two copies that drift the first time one is tuned, and the reset
// would then quietly restore the older pair.

import Testing

@testable import KnowledgePressUI

@MainActor
@Suite("Search settings reset")
struct SearchSettingsResetTests {

    @Test("a fresh model already reads as default")
    func freshModelIsDefault() {
        #expect(AppModel().searchSettingsAreDefault)
    }

    @Test("reset restores all three sliders")
    func resetRestoresEverySlider() {
        let model = AppModel()
        model.resultCount = 3
        model.minScore = 0.85
        model.semanticFloor = 0.7
        #expect(model.searchSettingsAreDefault == false)

        model.resetSearchSettings()

        #expect(model.resultCount == AppModel.SearchDefaults.resultCount)
        #expect(model.minScore == AppModel.SearchDefaults.minScore)
        #expect(model.semanticFloor == AppModel.SearchDefaults.semanticFloor)
        #expect(model.searchSettingsAreDefault)
    }

    @Test("one changed slider is enough to enable the button")
    func anySingleChangeIsNotDefault() {
        let model = AppModel()
        model.semanticFloor = 0.7
        #expect(model.searchSettingsAreDefault == false)
    }

    @Test("reset leaves the corpus scope alone")
    func resetDoesNotTouchScope() {
        let model = AppModel()
        model.corpus = "world-literature"
        model.resultCount = 3

        model.resetSearchSettings()

        // Scope is persisted precisely because it is a lens, not a
        // preference; a button about sliders must not undo the reader's
        // narrowing.
        #expect(model.corpus == "world-literature")
    }
}
