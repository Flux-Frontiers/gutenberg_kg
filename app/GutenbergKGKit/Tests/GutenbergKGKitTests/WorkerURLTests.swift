// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The worker address: where it starts, and that it survives a relaunch.
//
// Both of these shipped wrong. The address was a plain stored property with
// no backing store, so anything typed in Settings reverted to the default on
// the next launch -- and the default was `http://localhost:8000` on every
// platform, which on a phone names the phone. Together that meant an iPhone
// spent every query dialling itself and reporting that it could not reach a
// server the reader had never named.

import Foundation
import Testing

@testable import KnowledgePressUI

@MainActor
@Suite("Worker address")
struct WorkerURLTests {

    /// A scratch defaults domain per test, so nothing touches the real one
    /// and tests cannot see each other's writes.
    private func scratchDefaults() -> (UserDefaults, String) {
        let name = "WorkerURLTests.\(UUID().uuidString)"
        return (UserDefaults(suiteName: name)!, name)
    }

    private func withScratchDefaults(_ body: (UserDefaults) throws -> Void) rethrows {
        let (defaults, name) = scratchDefaults()
        let previous = AppModel.defaults
        AppModel.defaults = defaults
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: name)
        }
        try body(defaults)
    }

    @Test("a typed address survives being read back into a new model")
    func addressPersists() {
        withScratchDefaults { _ in
            let first = AppModel()
            first.workerURLString = "http://egsmac.local:8000"

            // A fresh model is what a relaunch produces.
            let second = AppModel()
            #expect(second.workerURLString == "http://egsmac.local:8000")
        }
    }

    @Test("the stored value is what a later launch reads, not the default")
    func storedValueBeatsTheDefault() {
        withScratchDefaults { defaults in
            defaults.set("http://192.168.1.42:8000", forKey: AppModel.workerURLKey)
            #expect(AppModel.initialWorkerURL() == "http://192.168.1.42:8000")
        }
    }

    @Test("an empty stored value falls through to the platform default")
    func emptyStoredValueIsIgnored() {
        withScratchDefaults { defaults in
            defaults.set("", forKey: AppModel.workerURLKey)
            #if os(macOS)
                #expect(AppModel.initialWorkerURL() == "http://localhost:8000")
            #else
                #expect(AppModel.initialWorkerURL().isEmpty)
            #endif
        }
    }

    /// The heart of it: `localhost` must never be the starting address on a
    /// device where it means the device itself.
    @Test("the default never points a phone at itself")
    func defaultIsPlatformHonest() {
        withScratchDefaults { _ in
            let initial = AppModel.initialWorkerURL()
            #if os(macOS)
                #expect(initial == "http://localhost:8000")
            #else
                #expect(initial.isEmpty)
                #expect(!initial.contains("localhost"))
            #endif
        }
    }

    @Test("the placeholder shows a real example rather than a format")
    func placeholderIsConcrete() {
        #if os(macOS)
            #expect(AppModel.workerURLPlaceholder == "http://localhost:8000")
        #else
            #expect(AppModel.workerURLPlaceholder.contains(".local"))
            #expect(!AppModel.workerURLPlaceholder.contains("localhost"))
        #endif
    }

    @Test("whitespace is not an address")
    func whitespaceIsNotConfigured() {
        withScratchDefaults { _ in
            let model = AppModel()
            model.workerURLString = "   \n "
            #expect(!model.hasWorkerURL)

            model.workerURLString = "http://egsmac.local:8000"
            #expect(model.hasWorkerURL)
        }
    }

    @Test("probing with no address says so instead of blaming a server")
    func probeWithoutAddressIsExplicit() async {
        let (defaults, name) = scratchDefaults()
        let previous = AppModel.defaults
        AppModel.defaults = defaults
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: name)
        }

        let model = AppModel()
        model.workerURLString = ""
        await model.probeWorker()
        #expect(model.workerProbe == .unreachable("No address set."))
    }
}
