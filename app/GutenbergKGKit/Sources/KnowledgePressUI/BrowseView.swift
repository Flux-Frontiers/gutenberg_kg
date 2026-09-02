// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Browse tab — the pages/1_Browse.py flow: genres → books → chapters →
// chapter text, backed by the worker's list_genres/list_books/get_chapters/
// get_chapter ops.
//
// A NavigationStack rather than the split view it started as: the same drill
// reads correctly on a phone and on a Mac window, and it is one code path.

import GutenbergKGKit
import SwiftUI

struct BrowseView: View {
    @Environment(AppModel.self) private var model
    @State private var path: [BrowseStep] = []
    @State private var loadError: String?

    /// The packs when they are installed, the worker when they are not —
    /// Browse does not need to know which, and neither does the reader.
    private var browser: any CorpusBrowser { model.browser }

    var body: some View {
        NavigationStack(path: $path) {
            List(model.genres) { genre in
                NavigationLink(value: BrowseStep.books(genre.genre)) {
                    HStack {
                        Text(genre.genre)
                        Spacer()
                        Text("\(genre.bookCount)")
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Corpus")
            .overlay {
                if model.genres.isEmpty {
                    ContentUnavailableView(
                        "No genres yet",
                        systemImage: "books.vertical",
                        description: Text(model.connectionError ?? "Connecting to the worker…"))
                }
            }
            .navigationDestination(for: BrowseStep.self) { step in
                destination(for: step)
            }
        }
        .overlay(alignment: .bottom) {
            if let loadError {
                Label(loadError, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .padding(8)
                    .background(.orange.opacity(0.15), in: Capsule())
                    .padding()
            }
        }
    }

    @ViewBuilder
    private func destination(for step: BrowseStep) -> some View {
        switch step {
        case .books(let genre):
            BookListView(genre: genre, browser: browser, loadError: $loadError)
        case .chapters(let genre, let book, let title):
            ChapterListView(
                genre: genre, book: book, title: title, browser: browser, loadError: $loadError)
        case .reader(let genre, let book, let sectionId):
            ChapterReaderView(
                genre: genre, book: book, sectionId: sectionId, browser: browser,
                loadError: $loadError)
        }
    }
}

/// One level of the browse drill.
enum BrowseStep: Hashable {
    case books(String)
    case chapters(genre: String, book: String, title: String)
    case reader(genre: String, book: String, sectionId: String)
}

private struct BookListView: View {
    let genre: String
    let browser: any CorpusBrowser
    @Binding var loadError: String?
    @State private var books: [Book] = []

    var body: some View {
        List(books) { book in
            NavigationLink(
                value: BrowseStep.chapters(
                    genre: genre, book: book.book, title: book.title ?? book.book)
            ) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(book.title ?? book.book)
                    if let author = book.author {
                        Text(author).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle(genre)
        .task {
            do {
                books = try await browser.listBooks(genre: genre)
                loadError = nil
            } catch { loadError = error.localizedDescription }
        }
    }
}

private struct ChapterListView: View {
    let genre: String
    let book: String
    let title: String
    let browser: any CorpusBrowser
    @Binding var loadError: String?
    @State private var chapters: [Chapter] = []

    var body: some View {
        List(chapters) { chapter in
            NavigationLink(
                value: BrowseStep.reader(genre: genre, book: book, sectionId: chapter.id)
            ) {
                Text(chapter.title ?? chapter.id)
            }
        }
        .navigationTitle(title)
        .task {
            do {
                chapters = try await browser.chapters(genre: genre, book: book)
                loadError = nil
            } catch { loadError = error.localizedDescription }
        }
    }
}

private struct ChapterReaderView: View {
    let genre: String
    let book: String
    @State var sectionId: String
    let browser: any CorpusBrowser
    @Binding var loadError: String?
    @State private var content: ChapterContent?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let content {
                    Text(content.title ?? "")
                        .font(.title2.bold())
                    Text(content.text)
                        .font(.body)
                        .textSelection(.enabled)
                        .lineSpacing(4)
                    pager(content)
                } else {
                    ProgressView().padding(.top, 40)
                }
            }
            .padding()
            .frame(maxWidth: 700, alignment: .leading)
        }
        .navigationTitle(content?.title ?? "Chapter")
        .task(id: sectionId) { await load() }
    }

    private func pager(_ content: ChapterContent) -> some View {
        HStack {
            Button("◀︎ Previous") { if let id = content.prevId { sectionId = id } }
                .disabled(content.prevId == nil)
            Spacer()
            if let index = content.index, let total = content.total {
                Text("\(index + 1) / \(total)")
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Next ▶︎") { if let id = content.nextId { sectionId = id } }
                .disabled(content.nextId == nil)
        }
        .font(.callout)
        .padding(.top, 8)
    }

    private func load() async {
        do {
            content = try await browser.chapter(genre: genre, book: book, sectionId: sectionId)
            loadError = nil
        } catch { loadError = error.localizedDescription }
    }
}
