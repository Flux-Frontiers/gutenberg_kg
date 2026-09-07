// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The version string shown in Settings. Reads the real Info.plist when one
// exists (a packaged .app or a device build) and falls back to a literal
// otherwise, because `swift run KnowledgePress` — the fastest feedback loop,
// per RUNBOOK.md — runs a bare SwiftPM executable with no Info.plist at all.

import Foundation

enum AppVersion {
    /// Mirrors `MARKETING_VERSION` in `app/ios/project.yml` and
    /// `app/macos/project.yml`. Keep in sync by hand — this is the only
    /// version string a bare `swift run` can ever see.
    static let fallback = "1.0"

    /// "v1.0" from a packaged build, "v1.0 (dev)" from `swift run`.
    ///
    /// Deliberately ignores `CFBundleVersion` (the build number):
    /// `CURRENT_PROJECT_VERSION` is hardcoded to "1" in both project.yml
    /// files and nothing increments it, so showing it would print "(1)" on
    /// every build forever rather than distinguishing anything. Revisit if
    /// the build number ever starts being wired to something real (a git
    /// commit count, a CI build number).
    static var display: String {
        let short = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        guard let short, !short.isEmpty else {
            return "v\(fallback) (dev)"
        }
        return "v\(short)"
    }
}
