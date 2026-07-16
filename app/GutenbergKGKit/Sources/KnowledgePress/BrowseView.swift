// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Browse tab — the pages/1_Browse.py flow: genres → books → chapters →
// chapter text, backed by the worker's list_genres/list_books/get_chapters/
// get_chapter ops.

import GutenbergKGKit
import SwiftUI

struct BrowseView: View {
    @Environment(AppModel.self) private var model
    @State private var selectedGenre: GenreCount?
    @State private var books: [Book] = []
    @State private var selectedBook: Book?
    @State private var chapters: [Chapter] = []
    @State private var selectedChapter: Chapter?
    @State private var chapterContent: ChapterContent?
    @State private var loadError: String?

    private var client: WorkerClient {
        WorkerClient(
            baseURL: URL(string: model.workerURLString) ?? URL(string: "http://localhost:8000")!,
            secret: model.secret)
    }

    var body: some View {
        HSplitView {
            genreList
                .frame(minWidth: 180, idealWidth: 220)
            bookList
                .frame(minWidth: 220, idealWidth: 280)
            chapterPane
                .frame(minWidth: 300)
        }
        .overlay(alignment: .bottom) {
            if let loadError {
                Label(loadError, systemImage: "exclamationmark.triangle")
                    .padding(8)
                    .background(.orange.opacity(0.15), in: Capsule())
                    .padding()
            }
        }
    }

    private var genreList: some View {
        List(model.genres, selection: Binding(get: { selectedGenre?.id }, set: { id in
            selectedGenre = model.genres.first { $0.id == id }
            books = []
            selectedBook = nil
            chapters = []
            chapterContent = nil
            if let genre = selectedGenre {
                Task { await loadBooks(genre.genre) }
            }
        })) { genre in
            HStack {
                Text(genre.genre)
                Spacer()
                Text("\(genre.bookCount)")
                    .foregroundStyle(.secondary)
            }
            .tag(genre.id)
        }
        .listStyle(.inset)
    }

    private var bookList: some View {
        List(books, selection: Binding(get: { selectedBook?.id }, set: { id in
            selectedBook = books.first { $0.id == id }
            chapters = []
            chapterContent = nil
            if let genre = selectedGenre, let book = selectedBook {
                Task { await loadChapters(genre.genre, book.book) }
            }
        })) { book in
            VStack(alignment: .leading) {
                Text(book.title ?? book.book)
                if let author = book.author {
                    Text(author).font(.caption).foregroundStyle(.secondary)
                }
            }
            .tag(book.id)
        }
        .listStyle(.inset)
        .overlay {
            if selectedGenre == nil {
                Text("Select a genre").foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var chapterPane: some View {
        if let content = chapterContent {
            chapterReader(content)
        } else {
            List(chapters, selection: Binding(get: { selectedChapter?.id }, set: { id in
                selectedChapter = chapters.first { $0.id == id }
                if let chapter = selectedChapter {
                    Task { await loadChapter(chapter.id) }
                }
            })) { chapter in
                Text(chapter.title ?? chapter.id).tag(chapter.id)
            }
            .listStyle(.inset)
            .overlay {
                if selectedBook == nil {
                    Text("Select a book").foregroundStyle(.secondary)
                }
            }
        }
    }

    private func chapterReader(_ content: ChapterContent) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button {
                    chapterContent = nil
                } label: {
                    Label("Chapters", systemImage: "chevron.left")
                }
                Spacer()
                if let index = content.index, let total = content.total {
                    Text("\(index + 1) / \(total)").foregroundStyle(.secondary)
                }
                Button("◀︎ Prev") { if let id = content.prevId { Task { await loadChapter(id) } } }
                    .disabled(content.prevId == nil)
                Button("Next ▶︎") { if let id = content.nextId { Task { await loadChapter(id) } } }
                    .disabled(content.nextId == nil)
            }
            .padding(10)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(content.title ?? "")
                        .font(.title2.bold())
                    Text(content.text)
                        .font(.body)
                        .textSelection(.enabled)
                        .lineSpacing(4)
                }
                .padding()
                .frame(maxWidth: 700, alignment: .leading)
            }
        }
    }

    private func loadBooks(_ genre: String) async {
        do {
            books = try await client.listBooks(genre: genre)
            loadError = nil
        } catch { loadError = error.localizedDescription }
    }

    private func loadChapters(_ genre: String, _ book: String) async {
        do {
            chapters = try await client.chapters(genre: genre, book: book)
            loadError = nil
        } catch { loadError = error.localizedDescription }
    }

    private func loadChapter(_ sectionId: String) async {
        guard let genre = selectedGenre, let book = selectedBook else { return }
        do {
            chapterContent = try await client.chapter(
                genre: genre.genre, book: book.book, sectionId: sectionId)
            loadError = nil
        } catch { loadError = error.localizedDescription }
    }
}
