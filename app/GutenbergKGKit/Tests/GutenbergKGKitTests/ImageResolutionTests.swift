// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Render size: that the app asks for one at all, that it is the same set of
// presets chat.py offers, and that the choice survives a relaunch.
//
// The defect this covers is silent rather than visible. The app used to send
// no size, so the worker fell back to its own 1536x1024 default -- the
// largest of the three, on a phone, which is what made a render time out.
// Nothing in the UI said which size was being used, so nothing looked wrong.

import Foundation
import Testing

@testable import KnowledgePressUI

@MainActor
@Suite("Illustration resolution")
struct ImageResolutionTests {

    private func withScratchDefaults(_ body: (UserDefaults) throws -> Void) rethrows {
        let name = "ImageResolutionTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        let previous = AppModel.defaults
        AppModel.defaults = defaults
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: name)
        }
        try body(defaults)
    }

    @Test("the presets are chat.py's, pixel for pixel")
    func presetsMatchStreamlit() {
        // chat.py's _RESOLUTION_SIZES. If either side changes, this fails and
        // one of the two is wrong.
        #expect(ImageResolution.preview.size == "768x512")
        #expect(ImageResolution.standard.size == "1152x768")
        #expect(ImageResolution.full.size == "1536x1024")
        #expect(ImageResolution.allCases.count == 3)
    }

    @Test("every preset is 3:2, like the ones it mirrors")
    func everyPresetIsThreeByTwo() throws {
        for resolution in ImageResolution.allCases {
            let parts = resolution.size.split(separator: "x").compactMap { Int($0) }
            let (width, height) = (try #require(parts.first), try #require(parts.last))
            #expect(width * 2 == height * 3, "\(resolution.size) is not 3:2")
        }
    }

    @Test("the default is the fastest preset, not the worker's largest")
    func defaultIsPreview() {
        withScratchDefaults { _ in
            #expect(AppModel.initialImageResolution() == .preview)
            #expect(AppModel().imageResolution == .preview)
            // The size the worker would have picked on its own.
            #expect(ImageResolution.preview.size != "1536x1024")
        }
    }

    @Test("a chosen resolution survives being read back into a new model")
    func resolutionPersists() {
        withScratchDefaults { _ in
            let first = AppModel()
            first.imageResolution = .full

            // A fresh model is what a relaunch produces.
            let second = AppModel()
            #expect(second.imageResolution == .full)
        }
    }

    @Test("an unrecognised stored value falls back rather than failing")
    func unknownStoredValueFallsBack() {
        withScratchDefaults { defaults in
            defaults.set("enormous", forKey: AppModel.imageResolutionKey)
            #expect(AppModel.initialImageResolution() == .preview)
        }
    }

    @Test("labels name the pixels, so the picker does not need a legend")
    func labelsCarryTheirDimensions() {
        #expect(ImageResolution.preview.label.contains("768"))
        #expect(ImageResolution.standard.label.contains("1152"))
        #expect(ImageResolution.full.label.contains("1536"))
    }
}
