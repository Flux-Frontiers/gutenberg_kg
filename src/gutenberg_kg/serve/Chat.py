# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Chat.py — GutenbergKG Chat Interface

Streamlit chat UI for the corpus-gutenberg KGRAG worker.  Searches the
consolidated DocKG (241 books, 20 genres) and 4 DiaryKG temporal indices,
and optionally synthesises answers via a local Ollama / oMLX model.

Run standalone (worker must be running first):
    gutenkg chat

Or via docker compose:
    docker compose --profile chat up
"""

from __future__ import annotations

import html
import io
import os
from pathlib import Path

import httpx
import streamlit as st
from kg_utils.worker import WorkerClient, WorkerError

from gutenberg_kg import __version__

# /.dockerenv only exists under Docker; Apple's `container` runtime sets no
# marker file, so the images also set GUTENKG_IN_CONTAINER=1 explicitly.
_IN_CONTAINER = os.path.exists("/.dockerenv") or bool(os.environ.get("GUTENKG_IN_CONTAINER"))
_HOST = "host.docker.internal" if _IN_CONTAINER else "localhost"

_DEFAULT_WORKER = os.environ.get("KGRAG_ENDPOINT", "http://localhost:8000")

_SYNTH_PROVIDERS: dict[str, str] = {
    "oMLX": "omlx",
    "Ollama": "ollama",
    "OpenAI": "openai",
}

# Synthesis models to hide from the dropdown. Reasoning models like Agents-A1
# emit their chain-of-thought as plain prose in the response body — not as
# strippable `<think>` tags, and unaffected by the `enable_thinking:false` flag —
# so on RAG prompts the answer truncates inside the thinking and the UI shows raw
# reasoning instead of an answer. Also excludes non-chat utilities (document
# converters, embedding models). Matched case-insensitively as substrings.
_MODEL_BLOCKLIST: tuple[str, ...] = (
    "agents-a1",  # reasoning agent — unstrippable "Thinking Process:" prose
    "deepseek-r1",  # R1 reasoning model
    "gpt-oss",  # reasoning model (harmony channels leak into content)
    "markitdown",  # document-to-markdown converter, not a chat model
    "embed",  # embedding models (nomic-embed, mxbai-embed, qwen3-embedding)
)


def _is_synth_model(model_id: str) -> bool:
    """Return ``True`` if a model id is usable for RAG synthesis (not blocklisted).

    :param model_id: Model id reported by the backend.
    :returns: ``False`` for reasoning/non-chat models unsuited to concise RAG.
    """
    lid = model_id.lower()
    return not any(pat in lid for pat in _MODEL_BLOCKLIST)


_RESOLUTION_LABELS: dict[str, str] = {
    "Preview": "Preview  (768 × 512)",
    "Standard": "Standard  (1152 × 768)",
    "Full": "Full  (1536 × 1024)",
}

# Pixel dimensions sent to the image backend for each preset (all 3:2).
_RESOLUTION_SIZES: dict[str, str] = {
    "Preview": "768x512",
    "Standard": "1152x768",
    "Full": "1536x1024",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="The Knowledge Press — GutenbergKG",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KG_KIND_COLOR: dict[str, str] = {
    "gutenberg": "#2E86AB",  # steel blue — prose/verse
    "diary": "#D4A017",  # amber — diary
    "verse": "#7B68EE",  # medium slate blue — sacred texts
}
_NODE_KIND_COLOR: dict[str, str] = {
    "chunk": "#4A90D9",
    "section": "#1ABC9C",
    "entity": "#E74C3C",
}

_SUGGESTED_QUERIES: list[tuple[str, str]] = [
    ("philosophy", "What is justice according to Plato?"),
    ("sacred-texts", "What does the Quran say about Moses?"),
    ("world-literature", "How does Dante describe the circles of Hell?"),
    ("russian-literature", "How does Tolstoy portray the Napoleonic invasion?"),
    ("french-literature", "How did Jules Verne describe undersea exploration?"),
    ("natural-history", "Describe Darwin's observations on the Galápagos"),
    ("ancient-classical", "What virtues does Seneca recommend in his dialogues?"),
    ("diary", "What did Pepys say about the great fire?"),
]

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; padding: 6px 18px; }
    .hit-card { background:var(--secondary-background-color); border-radius:6px; padding:10px 14px; margin-bottom:6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kg_kind_badge(kg_kind: str, kg_name: str = "") -> str:
    """Render an inline HTML badge naming a hit's source KG.

    :param kg_kind: KG kind string, e.g. ``"KGKind.GUTENBERG"``.
    :param kg_name: Display name to use instead of ``kg_kind`` when set.
    :returns: HTML ``<span>`` markup for the badge.
    """
    label = kg_name or kg_kind
    color = _KG_KIND_COLOR.get(kg_kind.lower().split(".")[-1], "#95A5A6")
    return (
        f"<span style='background:{color};color:#fff;border-radius:3px;"
        f"padding:1px 6px;font-size:11px;font-weight:bold;font-family:monospace;'>"
        f"{label}</span>"
    )


def _node_kind_badge(kind: str) -> str:
    """Render an inline HTML badge naming a hit's node kind (chunk/section/entity).

    :param kind: Node kind string.
    :returns: HTML ``<span>`` markup for the badge.
    """
    color = _NODE_KIND_COLOR.get(kind, "#95A5A6")
    return (
        f"<span style='background:{color};color:#fff;border-radius:3px;"
        f"padding:1px 6px;font-size:11px;font-weight:bold;font-family:monospace;'>"
        f"{kind}</span>"
    )


def _score_bar(score: float, width: int = 80) -> str:
    """Render an inline HTML bar visualising a similarity score, colour-coded by magnitude.

    :param score: Similarity score in ``[0, 1]``.
    :param width: Bar width in pixels.
    :returns: HTML markup for the bar plus a numeric label.
    """
    pct = min(int(score * 100), 100)
    color = "#27AE60" if score >= 0.7 else "#F39C12" if score >= 0.4 else "#E74C3C"
    return (
        f"<div style='display:inline-block;vertical-align:middle;"
        f"width:{width}px;height:8px;background:var(--secondary-background-color);border-radius:4px;overflow:hidden;'>"
        f"<div style='width:{pct}%;height:100%;background:{color};'></div></div>"
        f"&nbsp;<small style='color:var(--text-color);opacity:0.6;font-size:10px;'>{score:.3f}</small>"
    )


def _preview(text: str, n: int = 220) -> tuple[str, bool]:
    """Truncate text to roughly ``n`` characters at a word boundary.

    :param text: Text to truncate.
    :param n: Maximum length before truncation.
    :returns: Tuple of ``(preview_text, was_truncated)``.
    """
    text = (text or "").strip()
    if len(text) <= n:
        return text, False
    cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…", True


def _render_hit_card(hit: dict) -> None:
    """Render a single search hit as a styled HTML card with an expandable full passage.

    :param hit: Hit dictionary as returned by the worker (kg/node metadata, score, content).
    """
    kg_kind = hit.get("kg_kind", "").lower().split(".")[-1]
    kg_name = hit.get("kg_name", "")
    node_kind = hit.get("kind", "")
    score = float(hit.get("score", 0.0))
    source = hit.get("source_path") or "—"
    content = hit.get("content") or hit.get("summary") or ""
    preview, truncated = _preview(content, 220)

    author = hit.get("author") or ""
    title = hit.get("title") or ""
    genre = hit.get("genre") or ""
    meta_parts = [x for x in [genre, author, title] if x]
    meta_line = " · ".join(meta_parts) if meta_parts else hit.get("name", "")

    border_color = _KG_KIND_COLOR.get(kg_kind, "#555")
    esc_preview = html.escape(preview)
    details = ""
    if truncated:
        esc_full = html.escape(content).replace("\n", "<br>")
        details = (
            "<details style='margin-top:6px;'>"
            "<summary style='cursor:pointer;color:#4A90D9;font-size:12px;'>📖 Full passage</summary>"
            f"<div style='color:var(--text-color);font-size:13px;margin-top:6px;"
            f"line-height:1.55;'>{esc_full}</div>"
            "</details>"
        )

    st.markdown(
        f"""
        <div style="background:var(--secondary-background-color);border-left:4px solid {
            border_color
        };
                    border-radius:6px;padding:10px 14px;margin-bottom:6px;">
          {_kg_kind_badge(kg_kind, kg_name)}
          &nbsp;
          {_node_kind_badge(node_kind)}
          &nbsp;&nbsp;
          <b style="font-size:14px;color:var(--text-color);">{html.escape(meta_line)}</b>
          <br>
          <span style="color:var(--text-color);opacity:0.55;font-size:11px;
                       font-family:monospace;">📄 {html.escape(source)}</span>
          &nbsp;&nbsp;
          {_score_bar(score)}
          {
            "<br><span style='color:var(--text-color);opacity:0.8;font-size:12px;'>"
            + esc_preview
            + "</span>"
            if esc_preview
            else ""
        }
          {details}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Worker calls
# ---------------------------------------------------------------------------


def _rewrite_via_worker(
    worker_url: str,
    text: str,
    secret: str,
    backend: str = "",
    model: str = "",
) -> tuple[str, str | None]:
    """Ask the worker to rewrite a corpus passage into an image-generation prompt."""
    return WorkerClient(worker_url, secret).rewrite(text, backend=backend, model=model)


def _imagine_via_worker(
    worker_url: str,
    prompt: str,
    secret: str,
    *,
    image_backend: str = "",
    steps: int | None = None,
    size: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Route image generation through the worker. Returns (b64, image_model, image_backend, error)."""
    return WorkerClient(worker_url, secret).imagine(
        prompt,
        image_backend=image_backend,
        steps=steps,
        size=size,
    )


def _query_worker(
    query: str,
    *,
    worker_url: str,
    corpus: str,
    k: int,
    min_score: float,
    semantic_floor: float,
    synthesize: bool,
    secret: str,
    model: str = "",
    backend: str = "",
) -> dict:
    """Route a corpus query through the worker and return the raw result payload.

    :param query: Natural-language query string.
    :param worker_url: Base URL of the KGRAG worker.
    :param corpus: Corpus scope, e.g. ``"all"``, ``"diary"``, or a genre name.
    :param k: Number of hits to request.
    :param min_score: Drop hits below this similarity score.
    :param semantic_floor: Discard a KG entirely if its best hit is below this.
    :param synthesize: Whether to also request a synthesised narrative answer.
    :param secret: Shared secret for the worker (if configured).
    :param model: Override model ID for synthesis.
    :param backend: Synthesis backend (``"omlx"``, ``"ollama"``, ``"openai"``).
    :returns: The worker's raw JSON response as a dict.
    """
    return WorkerClient(worker_url, secret).query(
        query,
        corpus=corpus,
        k=k,
        min_score=min_score,
        semantic_floor=semantic_floor,
        synthesize=synthesize,
        model=model,
        backend=backend,
    )


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_stats(worker_url: str) -> dict:
    """Fetch live corpus totals from the worker's ``stats`` op (cached 5 min).

    :param worker_url: Base URL of the KGRAG worker.
    :returns: The worker's stats dict, or ``{}`` if the worker is unreachable so
              the header degrades gracefully before the worker is up.
    """
    try:
        resp = httpx.post(
            f"{worker_url.rstrip('/')}/runsync",
            json={"input": {"op": "stats"}},
            timeout=10.0,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError:
        return {}
    return payload.get("output", payload)


@st.cache_data(ttl=300, show_spinner=False)
def _corpus_options(worker_url: str) -> list[str]:
    """Build the corpus-scope dropdown from the worker's live genre list.

    ``all`` (DocKG + diaries) and ``diary`` (diaries only) always bookend the
    list; the middle is every DocKG genre reported by the worker's ``list_genres``
    op. The ``diaries`` genre is folded into the ``diary`` scope, so it is
    excluded here. Falls back to ``["all", "diary"]`` if the worker is offline.

    :param worker_url: Base URL of the KGRAG worker.
    :returns: Ordered corpus-scope options for the sidebar selectbox.
    """
    try:
        resp = httpx.post(
            f"{worker_url.rstrip('/')}/runsync",
            json={"input": {"op": "list_genres"}},
            timeout=10.0,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError:
        return ["all", "diary"]
    genres = (payload.get("output", payload)).get("genres", [])
    names = sorted(g["genre"] for g in genres if g.get("genre") and g["genre"] != "diaries")
    return ["all", *names, "diary"]


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_models(worker_url: str, secret: str, backend: str = "") -> tuple[list[str], str]:
    """Fetch the available model list and default model from the worker (cached 60s).

    :param worker_url: Base URL of the KGRAG worker.
    :param secret: Shared secret for the worker (if configured).
    :param backend: Synthesis backend to query models for.
    :returns: Tuple of ``(model_ids, default_model_id)``. Reasoning and non-chat
              models (see ``_MODEL_BLOCKLIST``) are filtered out.
    """
    models, default = WorkerClient(worker_url, secret).list_models(backend=backend)
    models = [m for m in models if _is_synth_model(m)]
    if default and not _is_synth_model(default):
        default = models[0] if models else ""
    return models, default


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------


def _result_to_markdown(result: dict) -> str:
    """Render a query result dict as a downloadable Markdown document.

    :param result: Worker query result (question, corpus, synthesis, hits).
    :returns: Markdown text summarising the answer and source passages.
    """
    lines = ["# GutenbergKG — Result", ""]
    if result.get("query"):
        lines += [f"**Question:** {result['query']}", ""]
    if result.get("corpus") and result["corpus"] != "all":
        lines += [f"**Corpus:** {result['corpus']}", ""]
    if result.get("synthesis"):
        lines += ["## Answer", "", result["synthesis"], ""]
        if result.get("model"):
            lines += [f"_Model: {result['model']}_", ""]
    hits = result.get("hits", [])
    if hits:
        lines += [f"## Source passages ({len(hits)})", ""]
        for h in hits:
            author = h.get("author") or ""
            title = h.get("title") or h.get("name") or "passage"
            src = h.get("source_path") or "—"
            head = " · ".join(x for x in [title, author] if x) or src
            lines += [f"### {head}  ·  score {h.get('score', 0):.3f}", ""]
            lines += [(h.get("content") or h.get("summary") or "").strip(), ""]
    return "\n".join(lines)


def _build_image_prompt(result: dict) -> str:
    """Distil a result into a concise image-generation prompt (≤800 chars)."""
    if result.get("synthesis"):
        return result["synthesis"][:800]
    hits = result.get("hits", [])[:3]
    parts = [h.get("content") or h.get("summary") or "" for h in hits]
    return " ".join(p.strip() for p in parts if p.strip())[:800]


def _open_image(path: Path) -> None:
    """Display a saved image in the Streamlit UI with its file path as a caption.

    :param path: Path to the image file on disk.
    """
    st.image(str(path), use_container_width=True)
    st.caption(f"📁 {path}")


def _render_assistant_turn(result: dict) -> None:
    """Render an assistant chat turn: synthesis (or warning), stats caption, and hit cards.

    :param result: Worker query result to render.
    """
    hits = result.get("hits", [])
    synthesis = result.get("synthesis")
    synthesis_error = result.get("synthesis_error")

    if not hits:
        st.warning("No passages matched — try different wording or lower the min score.")
        return

    if synthesis:
        st.markdown(synthesis)
        if result.get("model"):
            st.caption(f"🤖 {result['model']}")
    elif synthesis_error:
        st.warning(
            f"Answer generation failed — **{synthesis_error}**\n\n"
            "Check that Ollama/oMLX is running and reachable."
        )
    else:
        st.info("Answer generation off — see source passages below.")

    _parts = [
        f"📊 {result.get('total_hits', len(hits))} passages · {result.get('kgs_queried', 0)} KGs queried"
    ]
    if result.get("search_ms") is not None:
        _parts.append(f"search {result['search_ms']:,} ms")
    if result.get("synthesis_ms") is not None:
        _parts.append(f"synthesis {result['synthesis_ms']:,} ms")
    st.caption(" · ".join(_parts))

    with st.expander(f"📄 Source passages ({len(hits)})", expanded=not bool(synthesis)):
        for hit in hits:
            _render_hit_card(hit)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> dict:
    """Render the sidebar controls (corpus, search, synthesis, image settings).

    :returns: Query configuration dict assembled from the current widget values.
    """
    st.sidebar.title("📚 GutenbergKG")
    st.sidebar.caption(f"v{__version__}")
    stats = _fetch_stats(_DEFAULT_WORKER)
    if stats:
        model_short = (stats.get("embed_model") or "").rsplit("/", 1)[-1]
        st.sidebar.markdown(
            f"{stats['books']} books · {stats['genres']} genres · {stats['diaries']} diaries  \n"
            f"{model_short}"
        )
    else:
        st.sidebar.markdown("_corpus stats unavailable — worker offline_")
    st.sidebar.markdown("---")
    st.sidebar.subheader("📖 Corpus")

    corpus_options = _corpus_options(_DEFAULT_WORKER)
    corpus = st.sidebar.selectbox(
        "Scope",
        options=corpus_options,
        format_func=lambda x: x,
        index=0,
        help="all = DocKG + DiaryKG · gutenberg = DocKG only · diary = diaries only · <genre> = one genre",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Search")

    k = st.sidebar.slider("Results", min_value=1, max_value=50, value=15)
    min_score = st.sidebar.slider(
        "Min score",
        min_value=0.0,
        max_value=0.9,
        value=0.6,
        step=0.05,
        help="Drop hits below this similarity score",
    )
    semantic_floor = st.sidebar.slider(
        "Semantic floor",
        min_value=0.0,
        max_value=0.9,
        value=0.3,
        step=0.05,
        help="Ignore a KG entirely if its best match is below this score",
    )
    synthesize = st.sidebar.toggle(
        "Synthesize response",
        key="synthesize",
        help="Generate a narrative answer via the configured LLM backend",
    )

    backend = ""
    model = ""
    if synthesize:
        # Both selectboxes carry an explicit key so their value lives in
        # st.session_state and survives a rerun. Without one, Streamlit derives
        # the widget's identity from its parameters — including `options` and
        # `index` — so anything that changes those (switching provider, or
        # "Refresh models" returning a different order or default) makes it a
        # *new* widget, silently resetting the choice to the provider default.
        # That reset was invisible: the sidebar showed the default while the
        # query still ran, so answers came back from a model you had not picked.
        provider_label = st.sidebar.selectbox(
            "Provider",
            options=list(_SYNTH_PROVIDERS.keys()),
            key="synth_provider",
            help="LLM backend — oMLX (local MLX), Ollama (local), or OpenAI (cloud)",
        )
        backend = _SYNTH_PROVIDERS[provider_label]

        secret = os.environ.get("HANDLER_SECRET", "")
        with st.sidebar:
            with st.spinner("Fetching models…"):
                models, default = _fetch_models(_DEFAULT_WORKER, secret, backend)
        if models:
            # Reconcile the stored choice against the current list BEFORE the
            # widget renders. Streamlit raises if session_state holds a value
            # that is not in `options`, which is exactly what happens when the
            # provider changes or a refresh drops a model. Keeping a still-valid
            # choice is what makes the selection stick across a refresh.
            if st.session_state.get("synth_model") not in models:
                st.session_state["synth_model"] = default if default in models else models[0]
            model = st.sidebar.selectbox(
                "Model",
                options=models,
                key="synth_model",
                help="Model — fetched live from the selected provider",
            )
        else:
            st.sidebar.caption("⚠️ No models reported — using provider default.")
        if st.sidebar.button("🔄 Refresh models", use_container_width=True):
            # Drops every provider's entry (cache_data.clear() has no per-key
            # form), so the next run refetches. synth_model is deliberately left
            # in session_state: the reconcile above keeps it if it survived the
            # refresh, and only falls back to the default if it truly vanished.
            _fetch_models.clear()
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("🖼️ Image")
    resolution = st.sidebar.selectbox(
        "Resolution",
        options=list(_RESOLUTION_LABELS.keys()),
        format_func=lambda r: _RESOLUTION_LABELS[r],
        index=0,
        help="Smaller = faster generation",
    )
    has_result = any(
        m.get("role") == "assistant" and m.get("result")
        for m in st.session_state.get("messages", [])
    )
    last_result = next(
        (
            m["result"]
            for m in reversed(st.session_state.get("messages", []))
            if m.get("role") == "assistant" and m.get("result")
        ),
        None,
    )
    if last_result:
        st.sidebar.download_button(
            "💾 Save result",
            data=_result_to_markdown(last_result),
            file_name="gutenberg_result.md",
            mime="text/markdown",
            use_container_width=True,
            help="Download the most recent result as Markdown",
        )
    else:
        st.sidebar.button(
            "💾 Save result",
            disabled=True,
            use_container_width=True,
            help="Run a query first",
        )
    render_clicked = st.sidebar.button(
        "🎨 Render response",
        use_container_width=True,
        disabled=not has_result,
        help=(
            "Generate an illustration from the most recent result"
            if has_result
            else "Run a query first"
        ),
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("💡 Try asking")
    for genre, q in _SUGGESTED_QUERIES:
        label = f"[{genre}] {q}"
        if st.sidebar.button(label, use_container_width=True, key=f"sq_{q[:30]}"):
            st.session_state.pending_query = q
            st.session_state.pending_corpus = genre

    st.sidebar.markdown("---")
    if st.sidebar.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    return {
        "worker_url": _DEFAULT_WORKER,
        "secret": os.environ.get("HANDLER_SECRET", ""),
        "corpus": corpus,
        "k": k,
        "min_score": min_score,
        "semantic_floor": semantic_floor,
        "synthesize": synthesize,
        "backend": backend,
        "model": model,
        "resolution": resolution,
        "render_clicked": render_clicked,
    }


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _init_state() -> None:
    """Initialise Streamlit session-state defaults on first run."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = ""
    if "pending_corpus" not in st.session_state:
        st.session_state.pending_corpus = ""
    if "synthesize" not in st.session_state:
        st.session_state.synthesize = False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: render the chat UI, handle queries, and drive image rendering."""
    _init_state()
    cfg = _render_sidebar()

    title_col, clear_col = st.columns([5, 1])
    with title_col:
        st.title("📚 The Knowledge Press")
    with clear_col:
        if st.session_state.messages and st.button("🗑️ Clear", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    _n_books = _fetch_stats(_DEFAULT_WORKER).get("books")
    _books_phrase = (
        f"{_n_books} Project Gutenberg texts" if _n_books else "the Project Gutenberg corpus"
    )
    st.caption(
        f"Semantic search across {_books_phrase} — philosophy, literature, "
        "sacred texts, natural history, science fiction, and four historical diaries."
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                corpus_tag = msg.get("corpus", "")
                label = f"`[{corpus_tag}]` " if corpus_tag and corpus_tag != "all" else ""
                st.markdown(label + msg["content"])
            else:
                _render_assistant_turn(msg["result"])

    prompt = st.chat_input("Ask about any text in the corpus…")
    if not prompt and st.session_state.pending_query:
        prompt = st.session_state.pending_query
        if st.session_state.pending_corpus:
            cfg["corpus"] = st.session_state.pending_corpus
        st.session_state.pending_query = ""
        st.session_state.pending_corpus = ""

    if prompt:
        corpus = cfg["corpus"]
        with st.chat_message("user"):
            label = f"`[{corpus}]` " if corpus and corpus != "all" else ""
            st.markdown(label + prompt)
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "corpus": corpus, "result": None}
        )

        with st.chat_message("assistant"):
            with st.spinner("Searching the corpus…"):
                try:
                    result = _query_worker(
                        prompt,
                        worker_url=cfg["worker_url"],
                        corpus=corpus,
                        k=cfg["k"],
                        min_score=cfg["min_score"],
                        semantic_floor=cfg["semantic_floor"],
                        synthesize=cfg["synthesize"],
                        secret=cfg["secret"],
                        model=cfg["model"],
                        backend=cfg["backend"],
                    )
                except httpx.ConnectError:
                    st.error(
                        f"Cannot connect to worker at **{cfg['worker_url']}**. "
                        "Is it running? (`make run`)"
                    )
                    st.session_state.messages.pop()
                    st.stop()
                except httpx.HTTPStatusError as exc:
                    st.error(
                        f"Worker returned HTTP {exc.response.status_code}: {exc.response.text}"
                    )
                    st.session_state.messages.pop()
                    st.stop()
                except WorkerError as exc:
                    st.error(f"Worker error: {exc}")
                    st.session_state.messages.pop()
                    st.stop()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Unexpected error: {exc}")
                    st.session_state.messages.pop()
                    st.stop()

            if "error" in result:
                st.error(f"Worker error: {result['error']}")
                st.session_state.messages.pop()
                st.stop()

            _render_assistant_turn(result)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.get("synthesis", ""),
                "corpus": corpus,
                "result": result,
            }
        )
        st.rerun()

    if cfg["render_clicked"]:
        last_result = next(
            (
                m["result"]
                for m in reversed(st.session_state.messages)
                if m.get("role") == "assistant" and m.get("result")
            ),
            None,
        )
        if last_result:
            import base64
            import tempfile
            import time

            from PIL import Image as PILImage

            st.divider()
            prompt = _build_image_prompt(last_result)
            with st.spinner("Rewriting via LLM…"):
                t0_vlm = time.perf_counter()
                prompt, vlm_error = _rewrite_via_worker(
                    cfg["worker_url"],
                    prompt,
                    cfg["secret"],
                    backend=cfg["backend"],
                    model=cfg["model"],
                )
                vlm_ms = round((time.perf_counter() - t0_vlm) * 1000)
                if vlm_error:
                    st.warning(f"Rewrite failed — sending raw corpus text. ({vlm_error})")
                else:
                    st.caption(
                        f"🎨 Prompt: {prompt[:160]}{'…' if len(prompt) > 160 else ''}"
                        f" · rewrite {vlm_ms:,} ms"
                    )
            image_backend = "openai" if cfg["backend"] == "openai" else ""
            with st.spinner("Generating image…"):
                try:
                    t0_img = time.perf_counter()
                    b64, image_model, image_backend_used, img_error = _imagine_via_worker(
                        cfg["worker_url"],
                        prompt,
                        cfg["secret"],
                        image_backend=image_backend,
                        size=_RESOLUTION_SIZES.get(cfg["resolution"]),
                    )
                    img_ms = round((time.perf_counter() - t0_img) * 1000)
                    if img_error or not b64:
                        st.error(f"Image generation failed: {img_error or 'no image returned'}")
                    else:
                        out_path = (
                            Path(tempfile.mkdtemp()) / f"gutenberg_render_{int(time.time())}.png"
                        )
                        PILImage.open(io.BytesIO(base64.b64decode(b64))).save(str(out_path))
                        _open_image(out_path)
                        st.caption(
                            f"🖼️ {image_model or image_backend_used or 'unknown'}"
                            f" · {cfg['resolution']} · {img_ms:,} ms"
                        )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Image generation failed: {exc}")


if __name__ == "__main__":
    main()
