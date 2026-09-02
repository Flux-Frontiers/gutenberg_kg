// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// A read-only SQLite connection, owning the handle so the pack types do not.
//
// That ownership is not tidiness: a class with a `deinit` may not throw from
// its initializer until every stored property is set, and both pack types want
// to fail early on a file that will not open. Keeping the handle — and the
// `deinit` that closes it — down here lets them.

import Foundation
import SQLite3

/// SQLite's "copy this string, I may free it" sentinel.
private let transientText = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

/// A serialised, read-only connection to one pack file.
final class SQLiteConnection: @unchecked Sendable {

    enum ConnectionError: Error, LocalizedError {
        case cannotOpen(URL, String)
        case query(String, String)

        var errorDescription: String? {
            switch self {
            case .cannotOpen(let url, let message):
                return "Could not open \(url.lastPathComponent): \(message)"
            case .query(_, let message):
                return "Corpus query failed: \(message)"
            }
        }
    }

    private let handle: OpaquePointer
    /// The pack is opened `NOMUTEX`, so this type owns the exclusion rather
    /// than paying SQLite's per-call mutex on a single-threaded read.
    private let lock = NSLock()

    /// :param url: The SQLite file to open read-only.
    /// :throws: ``ConnectionError/cannotOpen(_:_:)``.
    init(readOnly url: URL) throws {
        var handle: OpaquePointer?
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX
        guard sqlite3_open_v2(url.path, &handle, flags, nil) == SQLITE_OK, let handle else {
            let message = handle.map { String(cString: sqlite3_errmsg($0)) } ?? "unknown error"
            sqlite3_close(handle)
            throw ConnectionError.cannotOpen(url, message)
        }
        self.handle = handle
    }

    deinit { sqlite3_close(handle) }

    /// Run `sql` and hand each row to `body`.
    ///
    /// Text bindings come first and integer bindings after, matching how the
    /// callers build their SQL: the scoping columns are text, the offsets are
    /// integers.
    ///
    /// :param sql: The statement.
    /// :param text: Text parameters, in order.
    /// :param ints: Integer parameters, bound after the text ones.
    /// :param body: Called once per row with the live statement.
    /// :throws: ``ConnectionError/query(_:_:)`` when the statement will not prepare.
    func each(
        _ sql: String,
        text: [String] = [],
        ints: [Int64] = [],
        _ body: (OpaquePointer) -> Void
    ) throws {
        lock.lock()
        defer { lock.unlock() }

        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, let statement
        else {
            throw ConnectionError.query(sql, String(cString: sqlite3_errmsg(handle)))
        }
        defer { sqlite3_finalize(statement) }

        var position: Int32 = 1
        for value in text {
            sqlite3_bind_text(statement, position, value, -1, transientText)
            position += 1
        }
        for value in ints {
            sqlite3_bind_int64(statement, position, value)
            position += 1
        }

        while sqlite3_step(statement) == SQLITE_ROW { body(statement) }
    }

    /// Run `sql`, ignoring any failure — for optional metadata a pack may lack.
    func tryEach(_ sql: String, text: [String] = [], _ body: (OpaquePointer) -> Void) {
        try? each(sql, text: text, body)
    }

    /// A row's text column, or nil when it is NULL.
    static func string(_ statement: OpaquePointer, _ column: Int32) -> String? {
        guard let raw = sqlite3_column_text(statement, column) else { return nil }
        return String(cString: raw)
    }

    /// A row's integer column, or nil when it is NULL.
    static func integer(_ statement: OpaquePointer, _ column: Int32) -> Int? {
        guard sqlite3_column_type(statement, column) != SQLITE_NULL else { return nil }
        return Int(sqlite3_column_int64(statement, column))
    }
}
