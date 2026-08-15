# Handoff — defects in `gutenberg_kg` surfaced by the `corpus_pepys` audit

**Status: all four items are fixed on this branch.** This file was originally
findings-only; it now doubles as the rationale for the diff beside it. Line
references are to the tree as it was at `b704b07` (merge of PR #46), i.e. before
the fix — they are kept so the reasoning stays checkable against the original.

**Origin:** an audit of `corpus_pepys` against this repo — Docker build, chat UI,
dependency pins. `gutenberg_kg` was the reference implementation for that audit,
so most differences were fixed on the `corpus_pepys` side
(Flux-Frontiers/corpus_pepys#7). Four things turned out to be wrong *here*, one
of them a live user-facing crash.

**Verified:** `ruff check .`, `ruff format --check .`, `ty check src/` (5
pre-existing warnings in `scene.py`/`cmd_quilt.py`, unchanged), `docker compose
config`, hadolint, `make check-pins`, and the test suite — 134 passed, 6 skipped,
with the 10 collection errors from absent optional deps (`click`, `numpy`)
unchanged from before. Two new test modules: `tests/test_chat_worker_ops.py`
(16, the first coverage `serve/` has had) and `tests/test_check_pins.py` (16).

---

## Summary

| # | Severity | Item | Where | Status |
|---|---|---|---|---|
| 1 | **High** | Chat sidebar crashed with `KeyError` when `HANDLER_SECRET` is set | `serve/Chat.py`, `serve/pages/1_Browse.py`, `docker/docker-compose.yml`, `Makefile` | ✅ fixed |
| 2 | Medium | Dockerfile pinned `kgmodule-utils` below its own declared floor; the pin was silently overridden later in the same build | `docker/Dockerfile` | ✅ fixed |
| 3 | Low | Cross-pin comment block documented versions three releases stale | `docker/Dockerfile` | ✅ fixed |
| 4 | Low | `synthesis_error` rendered but never produced | `serve/handler.py` | ✅ fixed |
| 5 | — | Two things `corpus_pepys` has that this repo may want | `scripts/check_pins.py`, `tests/` | ✅ both adopted |

---

## 1. Chat sidebar crashed when `HANDLER_SECRET` is set — **High** · fixed

### What happens

Set `HANDLER_SECRET` in `docker/.env` and start the stack. The worker enforces it
(`serve/handler.py:888`):

```python
if HANDLER_SECRET and inp.get("secret") != HANDLER_SECRET:
    return {"error": "unauthorized"}
```

`curl` keeps working — you pass `"secret"` in the body. The chat UI does not, for
two separate reasons that compound.

**(a) The secret never reaches the chat container.** `Chat.py` reads it from the
environment (`serve/Chat.py:566`, `:657`) and puts it in query, rewrite and
imagine calls. But nothing sets it in the chat container:

- `docker/docker-compose.yml` — the `chat` service passes `KGRAG_ENDPOINT`,
  `GUTENKG_IMAGE_ENDPOINT`, `IMAGE_ENDPOINT`, `IMAGE_STEPS`. No `HANDLER_SECRET`.
  The `worker` service does set it.
- `Makefile:211-223` — the Apple `container` `chat` target has the same omission.
  The `run` target sets it at `Makefile:196`.

So every chat query returns `{"error": "unauthorized"}` while `curl` and the
Makefile smoke test keep working — which makes it read as a chat bug rather than
a configuration one.

**(b) Two sidebar fetches never send the secret at all**, so this would fail even
if (a) were fixed. `_fetch_stats` (`serve/Chat.py:333`) and `_corpus_options`
(`serve/Chat.py:354`) build their payloads by hand and omit it entirely:

```python
json={"input": {"op": "stats"}},
```

### Why it is a crash and not a graceful degradation

`_fetch_stats` treats any 200 as success:

```python
resp.raise_for_status()
payload = resp.json()
...
return payload.get("output", payload)
```

The worker's rejection is a **200 with an error body**, not an HTTP error. So
`raise_for_status()` passes and the function returns `{"error": "unauthorized"}`
— a *truthy* dict. The sidebar then takes the success branch
(`serve/Chat.py:501-505`):

```python
if stats:
    model_short = (stats.get("embed_model") or "").rsplit("/", 1)[-1]
    st.sidebar.markdown(
        f"{stats['books']} books · {stats['genres']} genres · {stats['diaries']} diaries  \n"
```

`stats['books']` raises `KeyError: 'books'` and Streamlit renders a traceback
where the sidebar should be. The `else` branch — "corpus stats unavailable —
worker offline" — is unreachable in this case, because the failure mode it was
written for produces a falsy `{}` and this one does not.

`_corpus_options` fails more quietly: `{"error": ...}.get("genres", [])` yields
`[]`, so the corpus dropdown silently collapses to `["all", "diary"]` and every
genre disappears from the UI.

Note this is not exclusively a secret problem. **Any** worker error payload —
a missing index, a bootstrap failure — reaches the same subscript and crashes the
same way. The secret is just the reliable way to trigger it.

### Fix applied

Five parts:

1. **`HANDLER_SECRET` forwarded to the chat container** — added to the compose
   `chat` service and to the Makefile's Apple `chat` target, matching what their
   worker counterparts already did.
2. **New `_worker_op(worker_url, op, secret)` helper** in `Chat.py`. Both bare-op
   callers went through their own hand-built payload; the secret and the
   envelope handling now live in one place instead of being duplicated and — as
   it turned out — omitted. `_fetch_stats` and `_corpus_options` became thin
   wrappers over it and gained a `secret` parameter, which correctly joins the
   `st.cache_data` key: a different secret is a different result.
3. **Error payloads normalised to `{}`** inside `_worker_op`:

   ```python
   out = payload.get("output", payload)
   return out if isinstance(out, dict) and "error" not in out else {}
   ```

   This is what makes the existing "worker offline" fallbacks reachable. It also
   guards the non-dict case, which would have been its own `AttributeError`.
4. **`stats['books']` → `stats.get('books', 0)`** and likewise for `genres` and
   `diaries`, so a partial payload costs a number rather than the sidebar. Belt
   and braces with (3), deliberately: they fail independently.
5. **`pages/1_Browse.py` sends the secret too.** Its `_call_worker` had the same
   omission, so every op on that page returned `unauthorized` and the UI rendered
   an empty corpus rather than a rejected request. There the secret is read from
   the environment inside `_call_worker` rather than threaded through the four
   cached wrappers above it — it is process-fixed, so it cannot go stale inside a
   cache entry, and this keeps the change to one function.

Covered by `tests/test_chat_worker_ops.py`, including the specific regression:
an `unauthorized` payload must come back falsy so `_render_sidebar` takes the
offline branch.

---

## 2. `kgmodule-utils` pinned below its own floor, and the pin did not hold — Medium · fixed

`docker/Dockerfile:92`:

```dockerfile
ARG KGMODULE_UTILS_VERSION=0.10.0
```

against `pyproject.toml:82`:

```toml
"kgmodule-utils[synthesis,sqlite-vec]>=0.11.0",
```

and `poetry.lock`, which resolves **0.11.0**. The Dockerfile's own comment,
eleven lines above the ARG, states the rule this breaks:

> KEEP THESE >= THE FLOORS IN pyproject.toml [project].dependencies. The
> `pip install .` below re-resolves the same packages, so a pin below the floor
> is silently upgraded there — the pinned layer is wasted work and the numbers
> here become fiction.

That is exactly what now happens. The build does:

```dockerfile
RUN pip install ... "kgmodule-utils[synthesis,sqlite-vec]==${KGMODULE_UTILS_VERSION}" ...
COPY pyproject.toml README.md /app/
COPY src/gutenberg_kg /app/src/gutenberg_kg
RUN pip install --no-cache-dir .
```

The second `pip install .` reads `>=0.11.0`, finds 0.10.0 installed, and upgrades
it. Consequences:

- **The ARG is fiction.** Building with `--build-arg KGMODULE_UTILS_VERSION=0.10.0`
  produces an image running 0.11.0. There is no way to actually pin it low.
- **The cached layer is wasted** for that package — it is downloaded twice per
  cold build, once at 0.10.0 and once at 0.11.0.
- **The three sibling pins are now unverified together.** `kg-rag`,
  `doc-kg` and `diary-kg` are `==`-pinned specifically so a stale one is a hard
  resolution failure at build time. That guarantee only holds while the set is
  self-consistent; one member drifting past its floor and being silently
  corrected means the set is no longer the thing being tested.

**Fix applied:** the ARG is now `0.11.0`, matching the floor and the lock. The
resulting image is what was already being produced, so this changes no runtime
behaviour — it makes the recorded pin true, restores the layer cache, and puts
the four cross-pinned packages back under the `==` guarantee.

**Now guarded:** `scripts/check_pins.py` was ported in this branch and catches
exactly this — see item 5. It is a prerequisite of `make build` in both runtime
branches and runs in CI, so a drifted image cannot be produced.

---

## 3. The cross-pin comment block was stale — Low · fixed

`docker/Dockerfile`, immediately above the ARGs, enumerates the pinned set:

> ```
> kg-rag 0.11.0      needs transformers>=5.5.0 ...
> doc-kg 0.20.0      transformers>=5.5.0, kgmodule-utils>=0.9.0
> kgmodule-utils 0.9.0
> diary-kg 0.96.0    requires doc-kg>=0.20.0 + kgmodule-utils>=0.9.0
> ```

The ARGs directly below say `DOC_KG_VERSION=0.21.1` and
`KGMODULE_UTILS_VERSION=0.10.0`; the lock says kgmodule-utils 0.11.0. The comment
describes the constraint relationships correctly but names versions from an
earlier round. Since this block is the documentation of record for *why* the four
move together, a stale copy is worse than none — the next person to bump them
will reason from 0.9.0 floors that no longer apply.

**Fix applied:** rewritten from the lock's actual constraints, in the same commit
as item 2 — `kg-rag 0.11.0` needs `transformers>=5.5.0,<6` and
`kgmodule-utils>=0.8.0`; `doc-kg 0.21.1` needs `kgmodule-utils[semantic]>=0.10.0`;
`diary-kg 0.96.0` needs `doc-kg>=0.20.0` and `kgmodule-utils>=0.9.0`;
`kgmodule-utils 0.11.0` carries the transformers range through its `[semantic]`
extra. The worked example of why a stale pin resolves rather than fails is now
stated against the real versions.

---

## 4. `synthesis_error` rendered but never produced — Low · fixed

`serve/Chat.py:456` reads it and `:466-470` renders a dedicated warning:

```python
synthesis_error = result.get("synthesis_error")
...
elif synthesis_error:
    st.warning(f"Answer generation failed — **{synthesis_error}** ...")
```

No handler ever sets that key. `serve/handler.py:963-980` returns `synthesis`,
`synthesis_ms` and `model`, and calls `synthesize_rag` without a try/except — so
a synthesis failure propagates out of the handler and surfaces as a worker error,
never as `synthesis_error`. The branch is unreachable.

### Fix applied

Populated rather than dropped. The `synthesize_rag` call is wrapped, and a
backend failure (LLM server down, model unloaded, timeout) now degrades to
hits-plus-explanation instead of failing the whole query — a search that worked
should not be discarded because the optional narration did not. `synthesis_error`
carries `"{ExceptionType}: {message}"`, `synthesis_ms` still reports how long the
attempt took, and the key is present-and-`None` on the success and
not-requested paths so the response shape is stable.

`corpus_pepys` carried the identical dead path (inherited from this file) and is
fixed the same way in Flux-Frontiers/corpus_pepys#7, so the two workers keep the
same response contract.

---

## 5. Two things `corpus_pepys` has that this repo may want

Neither is a defect here. **The second is now adopted; the first is not.**

**`scripts/check_pins.py`.** Compares the KG package versions across
`poetry.lock`, the Dockerfile ARGs, and any compose build args, and fails with a
readable diff when they disagree. It is what makes item 2 impossible to
reintroduce. It is ~120 lines with no dependencies beyond `tomllib`, and it is
wired into `make build-image` as a prerequisite so a mismatched image cannot be
built. Porting it needs the `PINNED` dict retargeted at this repo's package set
and a floor check added — the `corpus_pepys` version deliberately compares only
lock-vs-Dockerfile because that project is `package-mode = false` and has no
`pip install .` step, which is precisely the mechanism that makes floors matter
here.

**Ported, with the floor check added.** `scripts/check_pins.py` here compares
four files rather than two, because this repo names the KG versions in four
places that drift independently:

| file | form | what it governs |
|---|---|---|
| `pyproject.toml` | floors (`>=`) | what the wheel demands |
| `poetry.lock` | exact | what the local build resolves |
| `docker/Dockerfile` | exact (`==` via ARG) | what the served image installs |
| `runpod/requirements.txt` | floors (`>=`) | what the serverless worker installs |

It fails on: an ARG below its pyproject floor (item 2), an ARG disagreeing with
the lock, a runpod floor below the pyproject floor, a package missing from the
lock or from the Dockerfile, and a stray `*_VERSION` arg reappearing in compose.

**It immediately found a fifth instance of item 2 that the manual pass had
missed:** `runpod/requirements.txt` pinned `kgmodule-utils>=0.10.0`, also below
the `>=0.11.0` floor, so the serverless worker could install a version the
package rejects. Fixed in the same commit — which is the argument for the script
better than any description of it.

Stdlib-only (`tomllib` + `re`), including a small `_version_key` rather than
`packaging.version`, so a build gate never depends on what the install resolved.
That matters for the ordering it exists to test: `"0.9.0" > "0.11.0"` under a
string compare, which is the exact drift being checked for.

Wired into `make build` in both runtime branches and into the CI lint job.
Covered by `tests/test_check_pins.py` (16 tests) — a gate that cannot go red is
worse than none, so each drift class has a test that asserts exit status 1.

**A testable Streamlit stub — adopted.** `Chat.py` had no test coverage at all,
largely because importing it requires a real Streamlit and it builds its whole
page at import time. `corpus_pepys/tests/conftest.py` gets around this in three
lines:

```python
_streamlit = MagicMock()
_streamlit.cache_data = lambda *a, **kw: (lambda fn: fn)
sys.modules["streamlit"] = _streamlit
```

The `cache_data` substitution is the load-bearing part — as a plain `MagicMock`
it replaces every decorated function with a mock, so the memoised helpers cannot
be called at all; as an identity decorator they are directly testable and there
is no cache bleed between tests.

`tests/test_chat_worker_ops.py` uses it to cover `_worker_op`, `_fetch_stats` and
`_corpus_options` — 16 tests, the first coverage `serve/` has had. It lives in the
test module rather than a `tests/conftest.py` (this repo has none) and stubs only
`streamlit`; `kg_utils.worker` stays real, since CI installs it and nothing in
these tests needs it mocked. The stub is applied unconditionally rather than via
`setdefault`: CI runs `--with dev`, so streamlit is absent there and the stub is
what makes the module importable at all — but under `--all-extras` the real
`st.cache_data` would memoise across tests and make results order-dependent.

Still untested in both repos: `_MODEL_BLOCKLIST` / `_is_synth_model`, which
originated here. `corpus_pepys` covers its copy; this one has no equivalent yet.

---

## Deliberate divergences — do not "fix" these

Recorded so a future consistency pass does not undo them.

- **Apple vmnet gateway.** `Makefile` here uses `192.168.65.1` as the cold-start
  fallback, with a comment attributing it to CLI 1.1.0. That appears to be wrong:
  `192.168.65.x` is *Docker Desktop's* gateway subnet, while the
  `container-network-vmnet` plugin allocates from `192.168.64.0/24` (macOS vmnet's
  default). `corpus_pepys` uses `192.168.64.1` and documents the discrepancy.
  Both repos auto-detect from the live `default` network first, so this only bites
  on a cold start before the runtime is up — but the constant here is the one
  more likely to be wrong. Worth verifying against
  `container network list` on a machine with the CLI before changing either.
- **Loose `docker/*.py` scripts in `corpus_pepys` vs this repo's packaged
  `serve/` module.** That project is `package-mode = false`; there is no package
  to put them in.
- **`corpus_pepys` has no corpus selector** in its chat sidebar. It has one corpus.

---

## Checked and found consistent

For completeness, these were compared and needed no change on either side:
`.dockerignore` coverage (this repo's is the model the `corpus_pepys` one was
built from), the CPU-only torch pre-install and its `--index-url` rationale, the
HF offline environment, the `handle_aux_ops` contract and the `models` / `rewrite`
/ `imagine` op shapes, the `WorkerClient` call signatures, the compose
worker/chat split and `--profile chat`, the ruff rule selection and the `*.md`
formatter exclusion, and the pre-commit hook set.
