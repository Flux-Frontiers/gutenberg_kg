# KG Utils Extraction Plan

Date: 2026-06-07
Status: Proposed
Scope: Reduce duplication between `gutenberg_kg/docker/*` and `corpus_pepys/docker/*` by extracting shared functionality into `kg_utils`.

## Goal

Consolidate shared handler/client functionality while keeping corpus-specific behavior local.

Success criteria:
- Shared worker protocol and error handling live in `kg_utils`.
- Shared synthesis backend selection logic lives in `kg_utils`.
- Shared hit serialization/content hydration logic lives in `kg_utils`.
- Gutenberg- and Pepys-specific retrieval/routing behavior remains in repo-local handlers.

## Evidence Of Duplication

Function inventory overlap (quick structural check):
- `chat.py`: 15 common function names across Gutenberg and Pepys variants.
- `handler.py`: 8 common function names across Gutenberg and Pepys variants.

High-overlap blocks in Gutenberg code:
- Worker calls and RunPod error decoding in `docker/chat.py`.
- Backend resolver/factory logic in `docker/handler.py`.
- Handler op dispatch for `models`/`rewrite`/`imagine` in `docker/handler.py`.
- Hit serialization/content hydration in `docker/handler.py`.

## What To Extract

## 1) Shared worker client protocol (chat-side)

Current local helpers to replace:
- `_rewrite_via_worker`
- `_imagine_via_worker`
- `_query_worker`
- `_fetch_models`
- `WorkerError`

Proposed module:
- `kg_utils.worker.client`

Proposed API:
- `class WorkerError(Exception)`
- `class WorkerClient:`
- `def __init__(self, base_url: str, secret: str = "")`
- `def query(...) -> dict`
- `def list_models(backend: str = "") -> tuple[list[str], str]`
- `def rewrite(text: str, backend: str = "", model: str = "") -> tuple[str, str | None]`
- `def imagine(prompt: str, image_backend: str = "", aspect_ratio: str = "3:2", steps: int | None = None) -> tuple[str | None, str | None, str | None, str | None]`

Behavior notes:
- Centralize RunPod failure decoding: top-level `status == FAILED`, `error_type`, and soft `output.error`.
- Preserve current timeouts and payload shapes initially (no behavior drift).

## 2) Shared per-request synthesis backend resolution (handler-side)

Current local helpers to replace:
- `_normalize_omlx_endpoint`
- `_synth_for_backend`
- `_image_for_backend`

Proposed module:
- `kg_utils.synthesis.factory`

Proposed API:
- `def normalize_openai_base_url(endpoint: str) -> str`
- `def text_synth_for_backend(backend: str, fallback: TextSynthesizer) -> TextSynthesizer`
- `def image_synth_for_backend(backend: str, fallback: ImageSynthesizer) -> ImageSynthesizer`

Behavior notes:
- Preserve legacy env aliases (`VLLM_*`, `GUTENKG_IMAGE_MODEL`) exactly.
- Keep fallback behavior on unknown backend values.

## 3) Shared handler op dispatch (`models`/`rewrite`/`imagine`)

Current local duplicated branch logic:
- `if inp.get("op") == "models" ...`
- `if inp.get("op") == "rewrite" ...`
- `if inp.get("op") == "imagine" ...`

Proposed module:
- `kg_utils.worker.ops`

Proposed API:
- `def handle_aux_ops(inp: dict, text_synth: Callable[[str], TextSynthesizer], image_synth: Callable[[str], ImageSynthesizer]) -> dict | None`

Behavior notes:
- Returns operation payload when `op` matched, otherwise `None`.
- Keeps existing response schema stable for chat clients.

## 4) Shared hit serialization + SQLite content hydration

Current local helpers to replace:
- `_hit_to_dict`
- `_attach_content`

Proposed module:
- `kg_utils.retrieval.hits`

Proposed API:
- `def hit_to_dict(hit, include_diary_timestamp: bool = False) -> dict`
- `def attach_content_by_sqlite(hits: list[dict], kg_sqlite_map: dict[str, Path]) -> None`

Behavior notes:
- Preserve batched `IN (...)` query behavior.
- Keep permissive failure handling (skip on bad/missing DB).

## What Should Stay Local

Keep in Gutenberg repo-local handler:
- Corpus routing rules (`all`, `gutenberg`, `diary`, genre filtering).
- Gutenberg catalog enrichment (`catalog.json` structure).
- Diary metadata fallback map specific to bundled diaries.

Keep in repo-local Streamlit app:
- Sidebar options, corpus labels, UX text, and render flow.
- Result card styling/theming and app-specific prompts.

## Refactor Phases (Low-Risk Order)

1. Add shared modules in `kg_utils` with tests; do not modify app repos yet.
2. Migrate `corpus_pepys` to shared worker client + op dispatch + factory helpers.
3. Migrate `gutenberg_kg` to same shared modules.
4. Consolidate any remaining duplicate helper code and remove dead functions.
5. Add changelog notes in each repo about shared dependency minimum version.

## Test Plan

Unit tests (kg_utils):
- Error decoding matrix (`FAILED`, `error_type`, soft output errors).
- Payload generation for `query`, `models`, `rewrite`, `imagine`.
- Backend selection + fallback matrix for text/image backends.
- Hit hydration with missing DB, empty IDs, partial node matches.

Integration smoke (both repos):
- `op=models` returns model list/default.
- `op=rewrite` returns prompt/error shape.
- `op=imagine` returns b64/model/backend or error.
- query path still returns `hits`, timing fields, and optional synthesis.

Manual checks:
- Streamlit chat still connects and handles worker errors cleanly.
- Image render path still works end-to-end.

## Risks And Mitigations

Risk: Subtle response-schema drift breaks existing chat clients.
Mitigation: Contract tests that assert exact keys and value types.

Risk: Env var precedence changes alter backend resolution unexpectedly.
Mitigation: Snapshot tests for env precedence and fallback behavior.

Risk: Different corpus handlers need slight divergence over time.
Mitigation: Keep shared modules focused on protocol/plumbing, not corpus policy.

## Proposed Follow-Up Work Items

1. Implement `kg_utils.worker.client` first and migrate `docker/chat.py` usage.
2. Implement `kg_utils.worker.ops` and replace handler `op` branches.
3. Implement `kg_utils.synthesis.factory` and replace `_synth_for_backend` / `_image_for_backend`.
4. Implement `kg_utils.retrieval.hits` and replace local `_hit_to_dict` / `_attach_content`.
5. Add pinned `kg_utils` minimum version where these modules are consumed.

## PR-Sized Implementation Checklist

This section is intended to be executed in order with small, reviewable PRs.

## PR 1: Add shared worker client to kg_utils

Objective:
- Introduce a reusable RunPod worker client and unified error decoding.

Files (kg_utils repo):
- `src/kg_utils/worker/client.py` (new)
- `src/kg_utils/worker/__init__.py` (new)
- `src/kg_utils/__init__.py` (export surface)
- `tests/test_worker_client.py` (new)

Tasks:
- Add `WorkerError` exception.
- Add `decode_worker_response(data: dict) -> dict` helper.
- Add `WorkerClient` with methods:
	- `query(...)`
	- `list_models(...)`
	- `rewrite(...)`
	- `imagine(...)`
- Preserve current payloads/timeouts from existing chat clients.

Acceptance criteria:
- All worker methods return the same response shapes current chat code expects.
- Error decoding covers:
	- top-level `status == "FAILED"`
	- top-level `error_type`
	- soft `output.error`
- Unit tests pass.

## PR 2: Add synthesis backend factory helpers to kg_utils

Objective:
- Remove duplicated per-request backend selection logic from handlers.

Files (kg_utils repo):
- `src/kg_utils/synthesis/factory.py` (new)
- `src/kg_utils/synthesis/__init__.py` (export updates)
- `tests/test_synthesis_factory.py` (new)

Tasks:
- Add `normalize_openai_base_url(endpoint: str) -> str`.
- Add `text_synth_for_backend(backend: str, fallback: TextSynthesizer)`.
- Add `image_synth_for_backend(backend: str, fallback: ImageSynthesizer)`.
- Keep env precedence and legacy alias behavior unchanged.

Acceptance criteria:
- Unknown backend returns `fallback`.
- Legacy vars (`VLLM_*`, `GUTENKG_IMAGE_MODEL`) still work.
- Tests cover endpoint normalization and backend matrix.

## PR 3: Add shared handler aux-op dispatcher to kg_utils

Objective:
- Centralize `op=models|rewrite|imagine` behavior.

Files (kg_utils repo):
- `src/kg_utils/worker/ops.py` (new)
- `src/kg_utils/worker/__init__.py` (export updates)
- `tests/test_worker_ops.py` (new)

Tasks:
- Implement `handle_aux_ops(inp, text_synth_factory, image_synth_factory)`.
- Return `None` for unknown/no `op`.
- Preserve existing error text and return keys.

Acceptance criteria:
- Existing chat flows can consume response without changes.
- All op variants are covered by tests.

## PR 4: Add shared retrieval hit utilities to kg_utils

Objective:
- Deduplicate hit serialization/content hydration.

Files (kg_utils repo):
- `src/kg_utils/retrieval/hits.py` (new)
- `src/kg_utils/retrieval/__init__.py` (new)
- `src/kg_utils/__init__.py` (export surface)
- `tests/test_retrieval_hits.py` (new)

Tasks:
- Implement `hit_to_dict(hit, include_diary_timestamp=False)`.
- Implement `attach_content_by_sqlite(hits, kg_sqlite_map)` using batched `IN (...)` queries.
- Keep permissive behavior on missing/unreadable sqlite files.

Acceptance criteria:
- Hydration succeeds with mixed kg maps and partial node matches.
- Empty hits/IDs and missing db paths are no-op safe.

## PR 5: Migrate corpus_pepys to shared modules

Objective:
- Use `kg_utils` abstractions in the smaller codebase first.

Files (corpus_pepys repo):
- `docker/chat.py`
- `docker/handler.py`
- `pyproject.toml` (if minimum version bump needed)

Tasks:
- Replace local worker call helpers in chat with `WorkerClient`.
- Replace handler backend factories with synthesis factory helpers.
- Replace handler aux-op branches with `handle_aux_ops`.
- Replace local hit utils with retrieval hit helpers.
- Keep corpus-specific routing and prompt/system text local.

Acceptance criteria:
- `make up` + chat flow works unchanged.
- `op=models|rewrite|imagine` responses are contract-identical.
- No functional regression in diary query behavior.

## PR 6: Migrate gutenberg_kg to shared modules

Objective:
- Complete dedupe in the larger codebase.

Files (gutenberg_kg repo):
- `docker/chat.py`
- `docker/handler.py`
- `pyproject.toml` (if minimum version bump needed)

Tasks:
- Replace local worker call helpers in chat with `WorkerClient`.
- Replace `_normalize_omlx_endpoint`, `_synth_for_backend`, `_image_for_backend` with shared factory helpers.
- Replace duplicated aux-op branches with `handle_aux_ops`.
- Replace `_hit_to_dict` and `_attach_content` with retrieval helpers.
- Keep `_enrich_catalog` and Gutenberg corpus routing local.

Acceptance criteria:
- Query + synthesis + image generation paths still pass manual smoke checks.
- Genre filtering and diary-specific routing behavior remain unchanged.

## PR 7: Versioning, docs, and cleanup

Objective:
- Finalize dependency/version alignment and remove dead code.

Files:
- `CHANGELOG.md` in each impacted repo
- relevant docs (`docs/*`)
- any now-unused helper blocks in chat/handler modules

Tasks:
- Pin minimum `kg_utils` version where consumed.
- Remove superseded local helper functions.
- Add migration notes for operators.

Acceptance criteria:
- Clean diff with no dead helper code left.
- Release notes call out dependency minimum and behavior stability.

## Contract Checklist (must stay stable)

- Query response keys:
	- `query`, `corpus`, `total_hits`, `kgs_queried`, `hits`, `search_ms`, `synthesis`, `synthesis_ms`, `model`
- Aux op response keys:
	- `models/default`
	- `prompt/error` (rewrite)
	- `image_b64/prompt/aspect_ratio/image_model/image_backend` (imagine)
- Error behavior:
	- unauthorized secret still returns `{"error": "unauthorized"}`
	- worker failures still surface readable messages in chat

## Rollback Plan

- Keep each migration PR isolated by concern.
- If a migration PR regresses behavior, revert only that PR and keep shared module additions.
- Do not combine kg_utils introduction and app migration in one PR.
