# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
chat.py — GutenbergKG Chat Interface

Streamlit chat UI for the corpus-gutenberg KGRAG worker.  Searches the
consolidated DocKG (245 books, 18 genres) and 4 DiaryKG temporal indices,
and optionally synthesises answers via a local Ollama / oMLX model.

Run standalone (worker must be running first):
    streamlit run docker/chat.py

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

_DEFAULT_WORKER = os.environ.get("KGRAG_ENDPOINT", "http://localhost:8000")

# When running inside Docker on macOS, host services are at host.docker.internal, not localhost.
_IN_DOCKER = os.path.exists("/.dockerenv")
_HOST = "host.docker.internal" if _IN_DOCKER else "localhost"
_DEFAULT_IMAGE_SERVER = os.environ.get("GUTENKG_IMAGE_ENDPOINT", f"http://{_HOST}:8090")
_DEFAULT_IMAGE_MODEL = os.environ.get("GUTENKG_IMAGE_MODEL", "flux2-klein-4b")
_DEFAULT_IMAGE_STEPS = int(os.environ.get("IMAGE_STEPS", "4"))
_DEFAULT_VLM_ENDPOINT = os.environ.get("GUTENKG_VLM_ENDPOINT", f"http://{_HOST}:8080/v1")

_ASPECT_SIZES: dict[str, str] = {
    "3:2": "1536x1024",
    "16:9": "1536x864",
    "1:1": "1024x1024",
    "4:3": "1365x1024",
    "9:16": "864x1536",
    "2:3": "1024x1536",
}

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

_ALL_GENRES = [
    "all",
    "— DocKG —",
    "american-literature",
    "ancient-classical",
    "audel-electric",
    "biography",
    "drama",
    "english-literature",
    "french-literature",
    "german-literature",
    "letters",
    "natural-history",
    "philosophy",
    "russian-literature",
    "sacred-texts",
    "science-fiction",
    "shakespeare",
    "spanish",
    "travel",
    "world-literature",
    "— DiaryKG —",
    "diary",
]

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
    label = kg_name or kg_kind
    color = _KG_KIND_COLOR.get(kg_kind.lower().split(".")[-1], "#95A5A6")
    return (
        f"<span style='background:{color};color:#fff;border-radius:3px;"
        f"padding:1px 6px;font-size:11px;font-weight:bold;font-family:monospace;'>"
        f"{label}</span>"
    )


def _node_kind_badge(kind: str) -> str:
    color = _NODE_KIND_COLOR.get(kind, "#95A5A6")
    return (
        f"<span style='background:{color};color:#fff;border-radius:3px;"
        f"padding:1px 6px;font-size:11px;font-weight:bold;font-family:monospace;'>"
        f"{kind}</span>"
    )


def _score_bar(score: float, width: int = 80) -> str:
    pct = min(int(score * 100), 100)
    color = "#27AE60" if score >= 0.7 else "#F39C12" if score >= 0.4 else "#E74C3C"
    return (
        f"<div style='display:inline-block;vertical-align:middle;"
        f"width:{width}px;height:8px;background:var(--secondary-background-color);border-radius:4px;overflow:hidden;'>"
        f"<div style='width:{pct}%;height:100%;background:{color};'></div></div>"
        f"&nbsp;<small style='color:var(--text-color);opacity:0.6;font-size:10px;'>{score:.3f}</small>"
    )


def _preview(text: str, n: int = 220) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= n:
        return text, False
    cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…", True


def _render_hit_card(hit: dict) -> None:
    kg_kind = hit.get("kg_kind", "").lower().split(".")[-1]
    kg_name = hit.get("kg_name", "")
    node_kind = hit.get("kind", "")
    score = float(hit.get("score", 0.0))
    source = hit.get("source_path") or "—"
    content = hit.get("content") or hit.get("summary") or ""
    preview, truncated = _preview(content, 220)

    # Author/title for DocKG hits; diary name for DiaryKG hits.
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


class WorkerError(Exception):
    pass


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
) -> dict:
    payload: dict = {
        "input": {
            "query": query,
            "corpus": corpus,
            "k": k,
            "min_score": min_score,
            "semantic_floor": semantic_floor,
            "synthesize": synthesize,
        }
    }
    if model:
        payload["input"]["model"] = model
    if secret:
        payload["input"]["secret"] = secret

    resp = httpx.post(
        worker_url.rstrip("/") + "/runsync",
        json=payload,
        timeout=httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=5.0),
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "FAILED" or "error_type" in data:
        err = data.get("error", data)
        raise WorkerError(f"{err.get('error_type', 'Unknown')}: {err.get('error_message', err)}")

    return data.get("output", data)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_models(worker_url: str, secret: str) -> tuple[list[str], str]:
    payload: dict = {"input": {"op": "models"}}
    if secret:
        payload["input"]["secret"] = secret
    try:
        resp = httpx.post(
            worker_url.rstrip("/") + "/runsync",
            json=payload,
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
        )
        resp.raise_for_status()
        out = resp.json().get("output", {})
        return out.get("models", []), out.get("default", "")
    except Exception:  # noqa: BLE001
        return [], ""


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------


def _result_to_markdown(result: dict) -> str:
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
    """Render *path* inline with st.image and show the file path as a caption."""
    st.image(str(path), use_container_width=True)
    st.caption(f"📁 {path}")


def _render_assistant_turn(result: dict, idx: int = 0) -> None:
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

    st.caption(
        f"📊 {result.get('total_hits', len(hits))} passages · {result.get('kgs_queried', 0)} KGs queried"
    )

    save_col, aspect_col, render_col = st.columns([3, 2, 3], vertical_alignment="bottom")
    with save_col:
        st.download_button(
            "💾 Save result",
            data=_result_to_markdown(result),
            file_name=f"gutenberg_result_{idx}.md",
            mime="text/markdown",
            key=f"dl_{idx}",
        )
    with aspect_col:
        aspect = st.selectbox(
            "Ratio",
            options=["3:2", "16:9", "1:1", "4:3", "9:16", "2:3"],
            label_visibility="collapsed",
            key=f"aspect_{idx}",
        )
    with render_col:
        render_clicked = st.button(
            "🎨 Render response",
            key=f"render_btn_{idx}",
            use_container_width=True,
            help="Generate an illustration from the retrieved passages using local FLUX",
        )

    if render_clicked:
        import tempfile
        import time

        prompt = _build_image_prompt(result)
        with st.spinner("Rewriting via VLM…"):
            try:
                from gutenberg_kg.image_gen import vlm_rewrite

                prompt, vlm_error = vlm_rewrite(prompt, base_url=_DEFAULT_VLM_ENDPOINT)
                if vlm_error:
                    st.warning(f"VLM rewrite failed — sending raw corpus text. ({vlm_error})")
                else:
                    st.caption(f"🎨 Prompt: {prompt[:160]}{'…' if len(prompt) > 160 else ''}")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"VLM rewrite error: {exc}")

        server = _DEFAULT_IMAGE_SERVER.strip()
        out_path = Path(tempfile.mkdtemp()) / f"gutenberg_render_{int(time.time())}.png"

        if server:
            with st.spinner(f"Generating via {_DEFAULT_IMAGE_MODEL}…"):
                try:
                    import base64

                    from PIL import Image as PILImage

                    resp = httpx.post(
                        server.rstrip("/") + "/v1/images/generations",
                        json={
                            "model": _DEFAULT_IMAGE_MODEL,
                            "prompt": prompt,
                            "n": 1,
                            "size": _ASPECT_SIZES.get(aspect, "1536x1024"),
                            "num_inference_steps": _DEFAULT_IMAGE_STEPS,
                        },
                        timeout=httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0),
                    )
                    resp.raise_for_status()
                    b64 = resp.json()["data"][0]["b64_json"]
                    pil = PILImage.open(io.BytesIO(base64.b64decode(b64)))
                    pil.save(str(out_path))
                    _open_image(out_path)
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text[:400]
                    st.error(f"Image server HTTP {exc.response.status_code}: {body}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Image server error: {exc}")
        else:
            with st.spinner("Generating locally — ~20 s on Apple Silicon…"):
                try:
                    from gutenberg_kg import image_gen

                    pil = image_gen.generate(prompt, aspect_ratio=aspect)
                    pil.save(str(out_path))
                    _open_image(out_path)
                except ImportError:
                    st.warning("Local image generation requires `mflux` (Apple Silicon).")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Image generation failed: {exc}")

    with st.expander(f"📄 Source passages ({len(hits)})", expanded=not bool(synthesis)):
        for hit in hits:
            _render_hit_card(hit)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> dict:
    st.sidebar.title("📚 GutenbergKG")
    st.sidebar.markdown(
        "245 books · 18 genres · 4 diaries  \n696K nodes · 6.2M edges · bge-small-en-v1.5"
    )
    st.sidebar.markdown("---")
    st.sidebar.subheader("📖 Corpus")

    # Filter out separators for the actual corpus value
    corpus_options = [g for g in _ALL_GENRES if not g.startswith("—")]
    corpus = st.sidebar.selectbox(
        "Scope",
        options=corpus_options,
        format_func=lambda x: x,
        index=0,
        help="all = DocKG + DiaryKG · gutenberg = DocKG only · diary = diaries only · <genre> = one genre",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Search")

    k = st.sidebar.slider("Results", min_value=1, max_value=50, value=10)
    min_score = st.sidebar.slider(
        "Min score",
        min_value=0.0,
        max_value=0.9,
        value=0.5,
        step=0.05,
        help="Drop hits below this similarity score",
    )
    semantic_floor = st.sidebar.slider(
        "Semantic floor",
        min_value=0.0,
        max_value=0.9,
        value=0.0,
        step=0.05,
        help="Ignore a KG entirely if its best match is below this score",
    )
    synthesize = st.sidebar.toggle(
        "Synthesize response",
        key="synthesize",
        help="Generate a narrative answer via the configured LLM backend",
    )

    model = ""
    if synthesize:
        models, default = _fetch_models(_DEFAULT_WORKER, os.environ.get("HANDLER_SECRET", ""))
        if models:
            default_idx = models.index(default) if default in models else 0
            model = st.sidebar.selectbox(
                "Model",
                options=models,
                index=default_idx,
                help="Synthesis model — pulled live from the worker's LLM backend",
            )
        else:
            st.sidebar.caption("⚠️ No models reported — using the worker's default.")
        if st.sidebar.button("🔄 Refresh models", use_container_width=True):
            _fetch_models.clear()
            st.rerun()

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
        "model": model,
    }


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _init_state() -> None:
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
    _init_state()
    cfg = _render_sidebar()

    title_col, clear_col = st.columns([5, 1])
    with title_col:
        st.title("📚 The Knowledge Press")
    with clear_col:
        if st.session_state.messages and st.button("🗑️ Clear", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    st.caption(
        "Semantic search across 245 Project Gutenberg texts — philosophy, literature, "
        "sacred texts, natural history, science fiction, and four historical diaries."
    )

    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                corpus_tag = msg.get("corpus", "")
                label = f"`[{corpus_tag}]` " if corpus_tag and corpus_tag != "all" else ""
                st.markdown(label + msg["content"])
            else:
                _render_assistant_turn(msg["result"], idx=i)

    # Handle suggested-query button clicks (they set pending_query + pending_corpus).
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

            _render_assistant_turn(result, idx=len(st.session_state.messages))

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.get("synthesis", ""),
                "corpus": corpus,
                "result": result,
            }
        )


if __name__ == "__main__":
    main()
