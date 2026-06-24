# Release Notes — v1.7.0

> Released: 2026-06-24

GutenbergKG 1.7.0 makes the served retriever genuinely hybrid and the corpus
builder leaner and more reliable. Chat queries now blend dense semantic search
with a lexical BM25 channel, so exact phrases the embedder used to bury (think
"circles of Hell" landing on Dante's *Inferno*) surface where you expect them.
At the same time, the consolidated build sheds nearly a million dead-weight
edges, and `--embed-device auto` no longer melts down on Apple Silicon.

## What changed

**Hybrid dense + lexical retrieval.** The served handler now fuses cosine kNN
with an FTS5/BM25 channel via reciprocal rank fusion (RRF, k=60), recovering
exact-term matches that pure embeddings miss. Both channels honour the same
genre and content-kind scope, and the FTS5 index is rebuilt over the full
consolidated graph at the end of a build so the hybrid path reliably activates
rather than silently degrading to dense-only. This requires `doc-kg >= 0.16.0`,
now the floor across every install extra.

**Leaner consolidated bundles.** `build-corpus` no longer discovers SIMILAR_TO
edges by default. The served handler is semantic-first and never traverses the
edges table, so the ~800k edges a full build produced (245 books × ~2.8k) were
pure bloat in the shipped `graph.sqlite`. The flag flipped from opt-out
`--no-similar` to an opt-in `--similar/--no-similar` pair. Per-book
`gutenkg ingest` is unchanged — it still builds cap-8 edges for viz3d arcs and
hop queries.

**Device-aware embedding.** `--embed-device auto` now resolves to CPU instead of
MPS. The full build embeds 700k+ nodes, and MPS single-process streaming OOMs on
Apple's unified-memory watermark partway through; the CPU path fans out across
`cpu_count/2` worker processes and finishes reliably. Pass `--embed-device mps`
explicitly only for a small corpus that fits in GPU memory. The startup banner
reports the resolved mode.

**Docker and deployment.** The Docker image now installs the local repo package
rather than hot-copying a single file over a PyPI install, so runtime imports
always match the checkout being built; transient SQLite sidecar files are
excluded from the build context. The RunPod handler was rewritten onto the same
direct LanceDB cosine-search path as the Docker handler, gaining DiaryKG support
and eliminating the startup hang on large corpora; see the new `docs/RUNPOD.md`
for the full deployment guide. The README now leads with the Docker local-app
quick start.

**Corpus cleanup.** Three mislabeled / duplicate Dante editions in
`world-literature` were consolidated into *The Divine Comedy (Cary)* and
*The Divine Comedy (Longfellow)*, with the duplicate dropped.

## Upgrading

Rebuild the consolidated bundle (`make build-corpus`) to pick up the
SIMILAR_TO-free graph and the freshly rebuilt FTS5 index that powers hybrid
retrieval — an existing bundle built before this release will fall back to
dense-only ranking. Ensure `doc-kg >= 0.16.0` is installed (a plain
`pip install -e ".[full]"` / `poetry install` handles this). If you relied on
SIMILAR_TO edges in a consolidated bundle for viz3d, pass `--similar` to opt
back in. No data migration is required.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
