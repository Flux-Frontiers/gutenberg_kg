// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// The version string shown in Settings. Reads the real Info.plist when one
// exists (a packaged .app or a device build) and falls back to a literal
// otherwise, because `swift run KnowledgePress` — the fastest feedback loop,
// per RUNBOOK.md — runs a bare SwiftPM executable with no Info.plist at all.

import Foundation

enum AppVersion {
    /// Mirrors `MARKETING_VERSION` in `app/ios/project.yml` and
    /// `app/macos/project.yml`, which track the gutenberg-kg package version.
    /// tests/test_app_version.py fails when any of the four differ -- this is
    /// the only version string a bare `swift run` can ever see.
    static let fallback = "1.23.0"

    /// "v1.0" from a packaged build, "v1.0 (dev)" from `swift run`.
    ///
    /// Leaves out `CFBundleVersion` (the build number). The Makefile sets it
    /// to the git commit count, but Xcode's own Run button does not, so it
    /// would read "1" on those builds and mean nothing.
    static var display: String {
        let short = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        guard let short, !short.isEmpty else {
            return "v\(fallback) (dev)"
        }
        return "v\(short)"
    }
}
