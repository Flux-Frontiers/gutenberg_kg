# Handoff — defects in `gutenberg_kg` surfaced by the `corpus_pepys` audit

**Status:** findings only. Nothing in this branch changes behaviour; this file is
the entire diff. Each item below is verified against the tree at
`b704b07` (merge of PR #46), with file and line references.

**Origin:** an audit of `corpus_pepys` against this repo — Docker build, chat UI,
dependency pins. `gutenberg_kg` was the reference implementation for that audit,
so most differences were fixed on the `corpus_pepys` side
(Flux-Frontiers/corpus_pepys#7). Four things turned out to be wrong *here*, and
one is a live user-facing crash. They are written up here rather than fixed
because they touch the serving layer of the larger repo and deserve their own
review.

---

## Summary

| # | Severity | Item | Where |
|---|---|---|---|
| 1 | **High** | Chat sidebar crashes with `KeyError` when `HANDLER_SECRET` is set | `serve/Chat.py`, `docker/docker-compose.yml`, `Makefile` |
| 2 | Medium | Dockerfile pins `kgmodule-utils` below its own declared floor; the pin is silently overridden later in the same build | `docker/Dockerfile` |
| 3 | Low | Cross-pin comment block documents versions three releases stale | `docker/Dockerfile` |
| 4 | Low | `synthesis_error` is rendered but never produced | `serve/Chat.py`, `serve/handler.py` |
| 5 | — | Two things `corpus_pepys` now has that this repo may want | — |

---

## 1. Chat sidebar crashes when `HANDLER_SECRET` is set — **High**

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

### Suggested fix

Three parts, all small:

1. Add `HANDLER_SECRET: ${HANDLER_SECRET:-}` to the compose `chat` service and
   `-e HANDLER_SECRET="$${HANDLER_SECRET:-}"` to the Makefile `chat` target.
2. Thread the secret into `_fetch_stats` and `_corpus_options` (they need a
   `secret` parameter; it also becomes part of the `st.cache_data` key, which is
   correct — a different secret is a different result).
3. Make `_fetch_stats` reject error payloads so the `else` branch can do its job:

   ```python
   out = payload.get("output", payload)
   return out if isinstance(out, dict) and "error" not in out else {}
   ```

   Independently, `stats['books']` should become `stats.get('books', 0)` — a
   partial payload should not take the sidebar down.

`corpus_pepys` has (1) and (3) implemented in
Flux-Frontiers/corpus_pepys#7 (`docker/chat.py::_fetch_stats`,
`docker/docker-compose.yml`, `Makefile::chat-container`) if a worked example is
useful. Its `stats` op and handler dispatch are modelled directly on this repo's.

---

## 2. `kgmodule-utils` is pinned below its own floor, and the pin does not hold — Medium

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

**Fix:** bump the ARG to `0.11.0` so it matches the floor and the lock. This is a
one-character change and the resulting image is what is already being produced.

**Related:** this repo has no equivalent of `corpus_pepys`'s
`scripts/check_pins.py`, which is why the drift went unnoticed — see item 5.

---

## 3. The cross-pin comment block is stale — Low

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

Worth updating in the same commit as item 2.

---

## 4. `synthesis_error` is rendered but never produced — Low

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

Two coherent resolutions:

- **Populate it.** Wrap the `synthesize_rag` call so a backend failure (LLM
  server down, model unloaded, timeout) degrades to hits-plus-explanation rather
  than failing the whole query. This is the behaviour the UI was clearly written
  for, and it is the better outcome — a search that worked should not be discarded
  because the optional narration failed.
- **Drop the branch** if the fail-the-query behaviour is intended.

`corpus_pepys` carries the identical dead path (inherited from this file) and has
recorded the same decision in its `HANDOFF.md`. Whichever way this goes, both
repos should go the same way.

---

## 5. Two things `corpus_pepys` now has that this repo may want

Neither is a defect here; both are offered because the audit produced them.

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

**A testable Streamlit stub.** `Chat.py` currently has no test coverage, largely
because importing it requires a real Streamlit and it builds its whole page at
import time. `corpus_pepys/tests/conftest.py` gets around this in three lines:

```python
_streamlit = MagicMock()
_streamlit.cache_data = lambda *a, **kw: (lambda fn: fn)
sys.modules["streamlit"] = _streamlit
```

The `cache_data` substitution is the load-bearing part — as a plain `MagicMock`
it replaces every decorated function with a mock, so the memoised helpers cannot
be called at all; as an identity decorator they are directly testable and there
is no cache bleed between tests. That unlocked 23 tests over the model blocklist
and the stats fetch. The same stub would work unmodified here, and the model
blocklist (`_MODEL_BLOCKLIST` / `_is_synth_model`, which originated in this repo)
is currently untested in both.

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
