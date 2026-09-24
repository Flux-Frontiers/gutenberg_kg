// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// The image-backend picker: that Auto keeps the rule from before the picker
// existed, that an explicit choice wins, that the choice survives a relaunch,
// and that the worker's report decodes. chat.py's _resolve_image_backend has
// the same cases in tests/test_chat_worker_ops.py.

import Foundation
import Testing

@testable import GutenbergKGKit
@testable import KnowledgePressUI

@MainActor
@Suite("Image backend choice")
struct ImageBackendChoiceTests {

    private func withScratchDefaults(_ body: (UserDefaults) throws -> Void) rethrows {
        let name = "ImageBackendChoiceTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        let previous = AppModel.defaults
        AppModel.defaults = defaults
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: name)
        }
        try body(defaults)
    }

    private func resolve(_ choice: String, _ provider: String, local: Bool = true) -> String {
        AppModel.resolveImageBackend(choice: choice, textBackend: provider, localAvailable: local)
    }

    @Test("Auto follows the provider: cloud with cloud, local with local")
    func autoFollowsProvider() {
        #expect(resolve(AppModel.imageAuto, "openai") == "openai")
        #expect(resolve(AppModel.imageAuto, "omlx") == AppModel.imageLocal)
        #expect(resolve("", "ollama") == AppModel.imageLocal)
    }

    @Test("Auto without a local server leaves it to the worker")
    func autoWithoutLocalServer() {
        #expect(resolve(AppModel.imageAuto, "omlx", local: false) == "")
        #expect(resolve(AppModel.imageAuto, "", local: true) == "")
    }

    @Test("an explicit choice wins over the provider")
    func explicitChoiceWins() {
        #expect(resolve("mflux-serve", "openai") == "mflux-serve")
        #expect(resolve("openai", "omlx") == "openai")
    }

    @Test("the default is Auto, and a choice survives a relaunch")
    func choicePersists() {
        withScratchDefaults { _ in
            let first = AppModel()
            #expect(first.imageBackendChoice == AppModel.imageAuto)
            first.imageBackendChoice = "openai"
            #expect(AppModel().imageBackendChoice == "openai")
        }
    }

    @Test("the worker's report decodes, key never included")
    func reportDecodes() throws {
        let json = """
        {"output": {"default": "mflux-serve", "backends": [
          {"key": "mflux-serve", "label": "Local", "available": true, "detail": "http://h:8090"},
          {"key": "openai", "label": "OpenAI", "available": false, "detail": "no OpenAI key on the worker"}
        ]}}
        """
        let list: ImageBackendList = try WorkerClient.decodePayload(
            Data(json.utf8), decoder: JSONDecoder())
        #expect(list.defaultBackend == "mflux-serve")
        #expect(list.backends.map(\.key) == ["mflux-serve", "openai"])
        #expect(list.backends.filter(\.available).map(\.key) == ["mflux-serve"])
    }
}
