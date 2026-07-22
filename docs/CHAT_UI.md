# The Knowledge Press — Chat UI

[`gutenberg_kg/serve/chat.py`](../src/gutenberg_kg/serve/chat.py) is a [Streamlit](https://streamlit.io/) chat
front-end for the GutenbergKG corpus. It turns the headless query worker into a
point-and-click reading room: ask a question in plain English, get ranked source
passages from the knowledge graph, optionally synthesize a narrative answer with a
local or cloud LLM, and render a corpus-grounded illustration.

It is a **thin client**. All retrieval, synthesis, and image work happens in the
query worker ([`gutenberg_kg/serve/handler.py`](../src/gutenberg_kg/serve/handler.py)); the chat app only
collects your question, calls the worker over HTTP, and renders the result. The
worker must be running before the chat UI is useful.

---

## What it queries

The UI searches the consolidated **DocKG** (237 books across 19 genres) plus the
four **DiaryKG** temporal indices—**241 books across 20 genres** in all—baked into the Docker image. The sidebar
**Scope** selector controls which slice is searched:

| Scope | Searches |
|-------|----------|
| `all` | DocKG + DiaryKG (everything) |
| `gutenberg` | DocKG only (all prose/verse genres) |
| `diary` | the four historical diaries only |
| `<genre>` | a single genre, e.g. `philosophy`, `russian-literature`, `sacred-texts` |

---

## Running it

### Option 1 — Docker (recommended)

The chat UI ships as the `gutenberg-chat` service in
[`docker/docker-compose.yml`](../docker/docker-compose.yml), behind the `chat`
compose profile. From the repo root:

```bash
make chat        # starts worker + chat UI
```

Then open **http://localhost:8501**. `make chat` brings up both the worker
(port 8000) and the chat container (port 8501); the chat container reaches the
worker over the compose network via `KGRAG_ENDPOINT=http://gutenberg-worker:8000`.

To bring up everything at once — worker, chat UI, *and* the local FLUX image
server (port 8090) for illustration rendering:

```bash
make up
```

Shut it all down with:

```bash
make stop
```

### Option 2 — Standalone (local dev)

You can run the Streamlit app directly against a worker you start separately.
Start the worker first (`make run`), then:

```bash
gutenkg chat          # requires: pip install 'gutenberg-kg[chat]'
```

The app opens on **http://localhost:8501** and, when not running inside Docker,
defaults to a worker at `http://localhost:8000`.

---

## Using the interface

### Asking a question

Type into the chat box at the bottom (*"Ask about any text in the corpus…"*) and
press Enter. The current **Scope** is applied to the query and shown as a
`` `[scope]` `` tag on your message. Each answer turn shows:

- The **synthesized answer** (if synthesis is on), or an info note pointing you to
  the source passages.
- A **stats caption** — number of passages, KGs queried, search time, and (if
  synthesizing) synthesis time.
- An expandable **📄 Source passages** panel with one card per hit: a colored KG-kind
  badge, node-kind badge, genre · author · title, source path, a score bar, a text
  preview, and a *📖 Full passage* disclosure for the complete text.

The score bar is color-coded: green ≥ 0.70, amber ≥ 0.40, red below.

### Suggested queries

The sidebar's **💡 Try asking** section has one-click example questions, each
pre-wired to the right scope (e.g. *"What did Pepys say about the great fire?"* in
the `diary` scope). Clicking one runs it immediately.

### Search controls (sidebar)

| Control | Default | Effect |
|---------|---------|--------|
| **Scope** | `all` | Which KG slice to search (see table above) |
| **Results** | 10 | Max number of passages (`k`), 1–50 |
| **Min score** | 0.50 | Drop hits below this similarity score |
| **Semantic floor** | 0.00 | Skip a whole KG if its *best* match is below this |
| **Synthesize response** | off | Generate a narrative answer via an LLM backend |

If you get *"No passages matched"*, lower **Min score** or reword the question.

### Synthesis (optional)

Toggle **Synthesize response** to have an LLM weave the retrieved passages into a
narrative answer. Retrieval is always deterministic and grounded in the graph — the
LLM only summarizes verified passages, it never invents sources. When enabled, two
extra controls appear:

- **Provider** — `oMLX` (local MLX, Apple Silicon), `Ollama` (local, cross-platform),
  or `OpenAI` (cloud).
- **Model** — fetched live from the selected provider; **🔄 Refresh models** re-queries
  the list.

Synthesis needs a reachable LLM endpoint configured on the **worker** (not the chat
app) — see the environment table below. If the backend is down, the answer turn
shows a *"Answer generation failed"* warning and still lists the source passages.

### Saving and illustrating results

The sidebar **🖼️ Image** section acts on the most recent result:

- **💾 Save result** — download the answer + source passages as Markdown.
- **🎨 Render response** — a two-stage pipeline: an LLM rewrites the passage into a
  visual scene description, then an image backend generates the illustration. The
  **Resolution** selector (Preview / Standard / Full) trades quality for speed.
  Requires a running image server (`make up`, or `make image-server` separately) and,
  for the rewrite step, a synthesis provider.

### Clearing the conversation

**🗑️ Clear chat** in the sidebar (or **🗑️ Clear** next to the title) resets the
session.

---

## Configuration (environment variables)

The chat app itself reads only two variables; the rest are consumed by the worker
it talks to.

**Read by the chat app:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `KGRAG_ENDPOINT` | `http://localhost:8000` | URL of the query worker. Set to `http://gutenberg-worker:8000` inside compose. |
| `HANDLER_SECRET` | *(empty)* | If the worker requires a shared secret, set the same value here so requests authenticate. |

**Read by the worker** (set in [`docker/.env`](../docker/.env.example) — copy
`docker/.env.example` to `docker/.env`): `VLLM_ENDPOINT_URL` / `VLLM_MODEL` /
`VLLM_API_KEY` (oMLX), `OLLAMA_ENDPOINT` (Ollama), `OPENAI_API_KEY` (OpenAI), and
`GUTENKG_IMAGE_ENDPOINT` / `IMAGE_STEPS` (image generation). See
[`docs/INSTALLATION.md`](INSTALLATION.md#environment-variables--full-reference) for
the full reference.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| *"Cannot connect to worker"* | The worker isn't running. Start it with `make run` (or `make chat`, which starts both). Check `KGRAG_ENDPOINT`. |
| *"No passages matched"* | Query too specific or **Min score** too high. Lower the score or reword. |
| *"Answer generation failed"* | Synthesis is on but the LLM backend is unreachable. Confirm oMLX/Ollama is running and the worker's `VLLM_ENDPOINT_URL` / `OLLAMA_ENDPOINT` is correct. |
| *"No models reported"* | The provider returned no model list; the provider default is used. Check the backend is up, then **🔄 Refresh models**. |
| **🎨 Render response** disabled | Run a query first — it illustrates the *most recent* result. |
| Image generation fails | The image server isn't running. Start it with `make up` or `make image-server`. |

---

## See also

- [`docs/INSTALLATION.md`](INSTALLATION.md) — full Docker and environment reference
- [`docs/CHEATSHEET.md`](CHEATSHEET.md) — CLI command reference
- [`docker/docker-compose.yml`](../docker/docker-compose.yml) — service definitions
