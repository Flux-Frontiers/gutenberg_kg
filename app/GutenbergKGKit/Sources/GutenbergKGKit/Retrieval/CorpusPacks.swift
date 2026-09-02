// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Finding an installed corpus and checking it before trusting it.
//
// The failure this guards against is not a crash: a pack built with one
// embedder and searched with another returns ranked, fluent, wrong passages.
// So the manifest names the embedder, and nothing opens until they agree.

import Foundation

/// `manifest.json`, as `gutenkg export-swift` writes it.
public struct PackManifest: Codable, Sendable {
    public struct Embedder: Codable, Sendable {
        public let model: String
        public let dim: Int
        public let normalized: Bool
    }

    public struct Pack: Codable, Sendable {
        public struct Sidecar: Codable, Sendable {
            public let name: String
            public let bytes: Int
            public let sha256: String
        }

        public let name: String
        public let bytes: Int
        public let sha256: String
        public let passages: Int
        public let vectors: Int
        public let sidecar: Sidecar?

        enum CodingKeys: String, CodingKey {
            case name, bytes, sha256, passages, vectors, sidecar
        }
    }

    public let packVersion: Int
    public let generated: String
    public let embedder: Embedder
    public let vectorDtype: String
    public let rrfK: Int
    public let packs: [Pack]
    public let totalBytes: Int

    enum CodingKeys: String, CodingKey {
        case generated, embedder, packs
        case packVersion = "pack_version"
        case vectorDtype = "vector_dtype"
        case rrfK = "rrf_k"
        case totalBytes = "total_bytes"
    }

    /// The newest pack format this build understands.
    public static let supportedVersion = 1
}

/// An installed corpus: the packs, their vectors, and the embedder that matches.
public final class CorpusPacks: @unchecked Sendable {

    public enum PacksError: Error, LocalizedError {
        case notInstalled(URL)
        case unreadableManifest(String)
        case unsupportedVersion(Int)
        case noPassagePacks

        public var errorDescription: String? {
            switch self {
            case .notInstalled(let url):
                return "No corpus at \(url.path). Build one with `gutenkg export-swift`."
            case .unreadableManifest(let message):
                return "manifest.json could not be read: \(message)"
            case .unsupportedVersion(let version):
                return
                    "This corpus is pack format \(version); this app reads \(PackManifest.supportedVersion). Update one of them."
            case .noPassagePacks:
                return "The corpus has a manifest but no passage packs."
            }
        }
    }

    public let directory: URL
    public let manifest: PackManifest
    public let embedder: BGEEmbedder
    /// Passage packs in search order — books first, then diaries.
    public let packs: [PassagePack]
    /// `core.pack`, when it is present.
    public let catalog: CatalogPack?

    /// Open an installed corpus and check it end to end.
    ///
    /// :param directory: The folder holding the packs, the manifest, and the
    ///     converted embedder.
    /// :throws: ``PacksError``, ``BGEEmbedder/EmbedderError``, or a store error
    ///     — each of which names what to do about it.
    public init(directory: URL) throws {
        let manifestURL = directory.appendingPathComponent("manifest.json")
        guard let data = try? Data(contentsOf: manifestURL) else {
            throw PacksError.notInstalled(directory)
        }
        let manifest: PackManifest
        do {
            manifest = try JSONDecoder().decode(PackManifest.self, from: data)
        } catch {
            throw PacksError.unreadableManifest(error.localizedDescription)
        }
        guard manifest.packVersion <= PackManifest.supportedVersion else {
            throw PacksError.unsupportedVersion(manifest.packVersion)
        }

        // The embedder is checked against the manifest before any pack opens:
        // a mismatch here is the difference between "no results" and "wrong
        // results", and only one of those is survivable.
        let embedder = try BGEEmbedder(
            directory: directory, requiredModel: manifest.embedder.model)

        var packs: [PassagePack] = []
        for entry in manifest.packs where entry.name != "core.pack" {
            let url = directory.appendingPathComponent(entry.name)
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            packs.append(
                try PassagePack(contentsOf: url, expectedDimension: manifest.embedder.dim))
        }
        guard !packs.isEmpty else { throw PacksError.noPassagePacks }

        let coreURL = directory.appendingPathComponent("core.pack")
        let catalog =
            FileManager.default.fileExists(atPath: coreURL.path)
            ? try? CatalogPack(contentsOf: coreURL) : nil

        self.directory = directory
        self.manifest = manifest
        self.embedder = embedder
        self.packs = packs
        self.catalog = catalog
    }

    /// Where an installed corpus lives by default.
    ///
    /// Application Support, excluded from backup: the packs are a gigabyte of
    /// reproducible data, and putting them in iCloud backups would be rude.
    ///
    /// :returns: The default install directory, created if needed.
    public static func defaultDirectory() -> URL? {
        guard
            var url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
                .first
        else { return nil }
        url.appendPathComponent("Corpus", isDirectory: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            var resource = URLResourceValues()
            resource.isExcludedFromBackup = true
            try? url.setResourceValues(resource)
        }
        return url
    }

    /// Open the default corpus if one is installed, else nil.
    ///
    /// :param progress: Optional callback for the reason it could not open,
    ///     so the settings screen can show it instead of a silent absence.
    /// :returns: The corpus, or nil.
    public static func installed(reportingFailure progress: ((String) -> Void)? = nil)
        -> CorpusPacks?
    {
        guard let directory = defaultDirectory() else { return nil }
        do {
            return try CorpusPacks(directory: directory)
        } catch {
            // "Not installed" is the normal state before a download, not a
            // fault worth reporting.
            if case PacksError.notInstalled = error { return nil }
            progress?(error.localizedDescription)
            return nil
        }
    }
}
