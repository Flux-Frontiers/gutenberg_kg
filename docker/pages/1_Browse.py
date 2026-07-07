# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
1_Browse.py — GutenbergKG corpus browser.

Streamlit page (auto-discovered by the multi-page nav next to chat.py) that
lists every book by genre and reads it chapter by chapter, reconstructed from
the DocKG section/chunk nodes already baked into the worker's index — no raw
corpus text is shipped in the deployed image.

Run standalone (worker must be running first):
    streamlit run docker/chat.py
    # then use the "Browse" entry in the top nav

Or via docker compose:
    docker compose --profile chat up
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

_IN_DOCKER = os.path.exists("/.dockerenv")
_HOST = "host.docker.internal" if _IN_DOCKER else "localhost"
_DEFAULT_WORKER = os.environ.get("KGRAG_ENDPOINT", "http://localhost:8000")

st.set_page_config(
    page_title="Browse — GutenbergKG",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Worker calls
# ---------------------------------------------------------------------------


def _call_worker(worker_url: str, op: str, **kwargs) -> dict:
    """POST ``{"input": {"op": op, **kwargs}}`` to the worker's ``/runsync`` endpoint.

    Mirrors the RunPod job format ``docker/handler.py`` expects, the same
    convention ``WorkerClient`` uses internally for the chat page's queries.

    :param worker_url: Base URL of the KGRAG worker.
    :param op: One of the corpus-browse ops (``list_genres``, ``list_books``,
        ``get_chapters``, ``get_chapter``).
    :param kwargs: Extra fields merged into ``input`` (e.g. ``genre``, ``book``).
    :returns: The worker's JSON response, or ``{"error": ...}`` on request failure.
    """
    try:
        resp = httpx.post(
            f"{worker_url.rstrip('/')}/runsync",
            json={"input": {"op": op, **kwargs}},
            timeout=30.0,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        return {"error": f"worker request failed: {exc}"}
    # RunPod-style local server wraps the handler's return value in "output".
    return payload.get("output", payload)


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_genres(worker_url: str) -> list[dict]:
    """Fetch ``[{"genre", "book_count"}, ...]`` from the worker (cached 5 min)."""
    result = _call_worker(worker_url, "list_genres")
    return result.get("genres", [])


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_books(worker_url: str, genre: str) -> list[dict]:
    """Fetch a genre's books from the worker (cached 5 min)."""
    result = _call_worker(worker_url, "list_books", genre=genre)
    return result.get("books", [])


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_chapters(worker_url: str, genre: str, book: str) -> list[dict]:
    """Fetch a book's chapter list from the worker (cached 5 min)."""
    result = _call_worker(worker_url, "get_chapters", genre=genre, book=book)
    return result.get("chapters", [])


def _fetch_chapter(worker_url: str, genre: str, book: str, section_id: str) -> dict:
    """Fetch one chapter's reconstructed text from the worker (not cached — Prev/Next-driven)."""
    return _call_worker(worker_url, "get_chapter", genre=genre, book=book, section_id=section_id)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("📖 Browse")
worker_url = st.sidebar.text_input("Worker URL", value=_DEFAULT_WORKER)

genres = _fetch_genres(worker_url)
if not genres:
    st.sidebar.error("No genres returned — is the worker running?")
    st.stop()

genre_labels = [f"{g['genre']} ({g['book_count']})" for g in genres]
genre_idx = st.sidebar.selectbox("Genre", range(len(genres)), format_func=lambda i: genre_labels[i])
genre = genres[genre_idx]["genre"]

books = _fetch_books(worker_url, genre)
if not books:
    st.sidebar.warning(f"No books found in {genre!r}.")
    st.stop()

book_labels = [f"{b['title']} — {b['author'] or 'Unknown'}" for b in books]
book_idx = st.sidebar.selectbox("Book", range(len(books)), format_func=lambda i: book_labels[i])
book_meta = books[book_idx]
book = book_meta["book"]

chapters = _fetch_chapters(worker_url, genre, book)
if not chapters:
    st.sidebar.warning("No chapters found for this book.")
    st.stop()

# Reset the reading position whenever the selected book changes.
book_key = f"{genre}/{book}"
if st.session_state.get("_browse_book_key") != book_key:
    st.session_state["_browse_book_key"] = book_key
    st.session_state["_browse_chapter_idx"] = 0

chapter_labels = [c["title"] or f"Chapter {c['index'] + 1}" for c in chapters]
chapter_idx = st.sidebar.selectbox(
    "Chapter",
    range(len(chapters)),
    format_func=lambda i: chapter_labels[i],
    key="_browse_chapter_idx",
)

# ---------------------------------------------------------------------------
# Main pane
# ---------------------------------------------------------------------------

ebook_id = book_meta.get("ebook_id")
st.title(book_meta["title"])
subtitle = book_meta.get("author") or "Unknown author"
if ebook_id:
    subtitle += f" · [Project Gutenberg #{ebook_id}](https://www.gutenberg.org/ebooks/{ebook_id})"
st.caption(subtitle)

chapter = _fetch_chapter(worker_url, genre, book, chapters[chapter_idx]["id"])
if chapter.get("error"):
    st.error(chapter["error"])
else:
    st.subheader(chapter.get("title") or chapter_labels[chapter_idx])
    st.markdown(chapter.get("text") or "*(no text found for this chapter)*")

    # Widget-bound state (key="_browse_chapter_idx") can only be changed via an
    # on_click callback, which runs *before* the selectbox redraws on rerun —
    # mutating it after the widget has already rendered this run raises
    # StreamlitAPIException.
    def _go_to(new_idx: int) -> None:
        st.session_state["_browse_chapter_idx"] = new_idx

    col_prev, _, col_next = st.columns([1, 4, 1])
    with col_prev:
        st.button(
            "← Previous",
            disabled=chapter_idx == 0,
            use_container_width=True,
            on_click=_go_to,
            args=(chapter_idx - 1,),
        )
    with col_next:
        st.button(
            "Next →",
            disabled=chapter_idx >= len(chapters) - 1,
            use_container_width=True,
            on_click=_go_to,
            args=(chapter_idx + 1,),
        )
