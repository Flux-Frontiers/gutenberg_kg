// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The dense channel: a memory-mapped `.vectors` sidecar and an exhaustive
// cosine scan over it.
//
// Exhaustive is not a compromise. sqlite-vec's vec0 is brute force too — it
// was chosen over LanceDB's ANN index precisely because it is exact
// (recall@10 = 1.0 against 0.825) — so doing the same arithmetic here with
// Accelerate costs nothing but removes an entire C dependency from the app.

import Accelerate
import Foundation

/// Exact cosine search over the packed corpus vectors.
///
/// The file is mapped, never read into the heap: a 140 MB int8 sidecar becomes
/// pages the kernel can evict under pressure rather than 140 MB of resident
/// memory. Row `i` of the file is the passage whose `vector_index` is `i`.
public final class VectorIndex: @unchecked Sendable {

    /// How the sidecar stores each component.
    public enum Precision: UInt8, Sendable {
        case int8 = 0
        case float32 = 1

        var stride: Int { self == .int8 ? 1 : 4 }
    }

    public enum IndexError: Error, LocalizedError {
        case notASidecar(URL)
        case unknownPrecision(UInt8)
        case truncated(URL, expected: Int, actual: Int)
        case dimensionMismatch(expected: Int, found: Int)

        public var errorDescription: String? {
            switch self {
            case .notASidecar(let url):
                return "\(url.lastPathComponent) is not a GutenbergKG vector file."
            case .unknownPrecision(let code):
                return "Unsupported vector precision (\(code)). Rebuild the packs."
            case .truncated(let url, let expected, let actual):
                return
                    "\(url.lastPathComponent) is \(actual) bytes, expected \(expected) — the download did not finish."
            case .dimensionMismatch(let expected, let found):
                return "The corpus holds \(found)-dimensional vectors; the embedder produces \(expected)."
            }
        }
    }

    /// `GKGVEC01`, matching `export_swift.VECTOR_MAGIC`.
    static let magic: [UInt8] = Array("GKGVEC01".utf8)
    static let headerBytes = 32

    public let dimension: Int
    public let count: Int
    public let precision: Precision

    private let data: Data
    /// Reciprocal row norms, computed once at open. Quantisation makes each
    /// row's norm differ slightly from 127, and the reference implementation
    /// divides by the real norm — so this is a parity requirement, not an
    /// optimisation.
    private let inverseNorms: [Float]

    /// Map a sidecar and precompute its row norms.
    ///
    /// :param url: A `.vectors` file beside its pack.
    /// :param expectedDimension: The embedder's output width; a mismatch is
    ///     rejected here rather than producing meaningless scores later.
    /// :throws: ``IndexError`` when the file is not a sidecar, is truncated, or
    ///     does not match the embedder.
    public init(contentsOf url: URL, expectedDimension: Int) throws {
        let mapped = try Data(contentsOf: url, options: .mappedIfSafe)
        guard mapped.count >= Self.headerBytes,
            Array(mapped.prefix(8)) == Self.magic
        else { throw IndexError.notASidecar(url) }

        guard let precision = Precision(rawValue: mapped[8]) else {
            throw IndexError.unknownPrecision(mapped[8])
        }
        let dimension = Int(Self.readUInt32(mapped, at: 12))
        let count = Int(Self.readUInt64(mapped, at: 16))

        guard dimension == expectedDimension else {
            throw IndexError.dimensionMismatch(expected: expectedDimension, found: dimension)
        }
        let expected = Self.headerBytes + count * dimension * precision.stride
        guard mapped.count == expected else {
            throw IndexError.truncated(url, expected: expected, actual: mapped.count)
        }

        self.data = mapped
        self.dimension = dimension
        self.count = count
        self.precision = precision
        self.inverseNorms = Self.computeInverseNorms(
            data: mapped, count: count, dimension: dimension, precision: precision)
    }

    /// Score every eligible row against `query` and return the best `k`.
    ///
    /// :param query: The query embedding, already L2-normalised by the model.
    /// :param k: How many rows to return.
    /// :param eligible: Row indices to consider, or nil for the whole file.
    ///     A nil filter is the common case — the packs contain only searchable
    ///     passages, so an unscoped query has nothing to exclude.
    /// :returns: `(row, similarity)` pairs, best-first, at most `k` of them.
    public func search(
        query: [Float], k: Int, eligible: [Int32]? = nil
    ) -> [(row: Int, similarity: Float)] {
        guard k > 0, count > 0, query.count == dimension else { return [] }

        var scores: [Float]
        var rows: [Int32]
        if let eligible {
            rows = eligible
            scores = scoreSelected(query: query, rows: eligible)
        } else {
            rows = (0..<Int32(count)).map { $0 }
            scores = scoreAll(query: query)
        }

        return Self.topK(scores: scores, rows: rows, k: k)
    }

    /// Keep the best `k` without sorting the whole score vector.
    ///
    /// `k` is around 30 against up to 364 K rows, so a full sort would cost
    /// more than the scan that produced the scores. The threshold test rejects
    /// almost every row with one comparison.
    static func topK(scores: [Float], rows: [Int32], k: Int) -> [(row: Int, similarity: Float)] {
        var best: [(row: Int, similarity: Float)] = []
        best.reserveCapacity(k + 1)
        var threshold = -Float.greatestFiniteMagnitude
        for (position, score) in scores.enumerated() {
            if best.count == k && score <= threshold { continue }
            let insertion = best.firstIndex { score > $0.similarity } ?? best.count
            best.insert((Int(rows[position]), score), at: insertion)
            if best.count > k { best.removeLast() }
            if best.count == k { threshold = best[best.count - 1].similarity }
        }
        return best
    }

    /// Cosine similarity for one row — used to hydrate a lexical-only hit.
    ///
    /// :param query: The query embedding.
    /// :param row: A row index.
    /// :returns: Cosine similarity, or nil when the row is out of range.
    public func similarity(query: [Float], row: Int) -> Float? {
        guard row >= 0, row < count, query.count == dimension else { return nil }
        var vector = [Float](repeating: 0, count: dimension)
        readRows(into: &vector, first: row, count: 1)
        var dot: Float = 0
        vDSP_dotpr(vector, 1, query, 1, &dot, vDSP_Length(dimension))
        return dot * inverseNorms[row]
    }

    // MARK: - Scanning

    /// Rows scored per batch. Large enough for BLAS to be worth calling,
    /// small enough that the float staging buffer stays in cache-friendly
    /// megabytes rather than expanding the whole corpus to fp32.
    private static let batchRows = 4096

    private func scoreAll(query: [Float]) -> [Float] {
        var scores = [Float](repeating: 0, count: count)
        let batches = (count + Self.batchRows - 1) / Self.batchRows
        let dimension = self.dimension

        scores.withUnsafeMutableBufferPointer { output in
            // The batches write to disjoint slices, so the shared pointer is
            // safe; Swift cannot see that, hence the explicit escape.
            nonisolated(unsafe) let sink = output
            DispatchQueue.concurrentPerform(iterations: batches) { batch in
                let first = batch * Self.batchRows
                let rows = min(Self.batchRows, self.count - first)
                var staging = [Float](repeating: 0, count: rows * dimension)
                self.readRows(into: &staging, first: first, count: rows)
                // One matrix-vector product per batch: (rows x dim) by (dim x 1).
                // vDSP rather than cblas — same work, and no deprecated BLAS
                // headers to chase across SDK versions.
                vDSP_mmul(
                    staging, 1, query, 1, sink.baseAddress! + first, 1,
                    vDSP_Length(rows), 1, vDSP_Length(dimension))
                for offset in 0..<rows {
                    sink[first + offset] *= self.inverseNorms[first + offset]
                }
            }
        }
        return scores
    }

    private func scoreSelected(query: [Float], rows: [Int32]) -> [Float] {
        var scores = [Float](repeating: 0, count: rows.count)
        var vector = [Float](repeating: 0, count: dimension)
        for (position, row) in rows.enumerated() {
            let index = Int(row)
            guard index >= 0, index < count else { continue }
            readRows(into: &vector, first: index, count: 1)
            var dot: Float = 0
            vDSP_dotpr(vector, 1, query, 1, &dot, vDSP_Length(dimension))
            scores[position] = dot * inverseNorms[index]
        }
        return scores
    }

    /// Widen `count` rows starting at `first` into `destination` as Float.
    ///
    /// int8 rows are converted with `vDSP_vflt8`; the ×127 scale they carry
    /// cancels when the score is divided by the row norm, so no rescaling is
    /// needed here.
    private func readRows(into destination: inout [Float], first: Int, count rows: Int) {
        let elements = rows * dimension
        let offset = Self.headerBytes + first * dimension * precision.stride
        data.withUnsafeBytes { raw in
            let base = raw.baseAddress!.advanced(by: offset)
            destination.withUnsafeMutableBufferPointer { output in
                switch precision {
                case .int8:
                    vDSP_vflt8(
                        base.assumingMemoryBound(to: Int8.self), 1,
                        output.baseAddress!, 1, vDSP_Length(elements))
                case .float32:
                    output.baseAddress!.update(
                        from: base.assumingMemoryBound(to: Float.self), count: elements)
                }
            }
        }
    }

    private static func computeInverseNorms(
        data: Data, count: Int, dimension: Int, precision: Precision
    ) -> [Float] {
        var norms = [Float](repeating: 0, count: count)
        guard count > 0 else { return norms }
        data.withUnsafeBytes { raw in
            var row = [Float](repeating: 0, count: dimension)
            for index in 0..<count {
                let offset = headerBytes + index * dimension * precision.stride
                let base = raw.baseAddress!.advanced(by: offset)
                row.withUnsafeMutableBufferPointer { output in
                    switch precision {
                    case .int8:
                        vDSP_vflt8(
                            base.assumingMemoryBound(to: Int8.self), 1,
                            output.baseAddress!, 1, vDSP_Length(dimension))
                    case .float32:
                        output.baseAddress!.update(
                            from: base.assumingMemoryBound(to: Float.self), count: dimension)
                    }
                }
                var norm: Float = 0
                vDSP_svesq(row, 1, &norm, vDSP_Length(dimension))
                norms[index] = norm > 0 ? 1.0 / norm.squareRoot() : 0
            }
        }
        return norms
    }

    private static func readUInt32(_ data: Data, at offset: Int) -> UInt32 {
        var value: UInt32 = 0
        for byte in (0..<4).reversed() { value = value << 8 | UInt32(data[offset + byte]) }
        return value
    }

    private static func readUInt64(_ data: Data, at offset: Int) -> UInt64 {
        var value: UInt64 = 0
        for byte in (0..<8).reversed() { value = value << 8 | UInt64(data[offset + byte]) }
        return value
    }
}
