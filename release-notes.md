# Release Notes -- v1.29.0

> Released: 2026-10-22

### Added

- **Live moots: the worker holds a moot for the forest.** Three new worker
  ops let the Knowledge Press Forest hold a moot against a local worker and
  play each turn as it is made: `moot_start` (two catalog keys, topic,
  turns, k, model, temperature) returns the trees with their author voices,
  `moot_turn` speaks one turn and returns it in the moot-pack form,
  `moot_stop` ends it. The worker keeps each moot (`serve/moot_ops.py`):
  at most 4, dropped after 30 idle minutes, the least recently used making
  room. Keeping it there means no passage pools cross the wire, and a
  browser cannot hand the grounding check a doctored pool. The model call
  uses the worker's own backend, so a browser may name a model but not a
  backend. `run_moot` is now a loop over a new `entmoot.Moot` class
  (`start()`, `next_turn()`), so the CLI is unchanged.
- **CORS on the local worker** (`serve/cors.py`), on when
  `GUTENKG_CORS_ORIGINS` is set. `docker compose` and `make run` default it
  to the forest's dev server and the published forest. Tested on 2026-10-21:
  Chrome reaches the worker from both once local network access is allowed;
  Safari only from the dev server, since it blocks `http://localhost` on an
  https page. A new `MOOT_TOKEN` lets the moot ops run without
  `HANDLER_SECRET`, which never reaches a browser.
- The worker image carries `corpus/authors/voices.json` (`GUTENKG_VOICES`),
  so live moots give each tree its author's voice.
- The worker image pins `runpod==1.12.0` (was `>=1.7.0`): the CORS hook
  subclasses its internal `WorkerAPI`.

- **Moots are documented.** A new guide, `docs/MOOTS.md`, covers running
  `gutenkg converse` (what it needs, every option and backend setting), how a
  turn is made (retrieval, the persona and author voice, turn intents,
  grounding, quote snapping), the JSON transcript, playing moots in the
  forest with `export-web-moots`, `author-voices`, and the known limits. The
  README has a moots section and a "Choose a path" row, the docs home and
  `KNOWLEDGE_PRESS.md` link the guide, and the API reference gains pages for
  `serve.entmoot`, `serve.scope`, `export_web_moots` and `author_voices`.

### Changed

- **The worker answers only its own Mac by default.** `docker compose` and
  `make run` published port 8000 on every interface, so anyone on the same
  network could use the worker, and with live moots a browser on the
  published forest could be pointed at it. The port now binds to
  `127.0.0.1`. A new `WORKER_BIND` setting in `docker/.env` restores LAN
  access (`WORKER_BIND=0.0.0.0`) for phones and other devices;
  `docs/INSTALLATION.md` covers it.
- The README describes live moots and `WORKER_BIND`.

### Fixed

- `docs/RUNPOD.md` listed 17 genre slugs; the corpus has 20 (`audel-electric`,
  `diaries` and `horror` were missing).
- `docs/KNOWLEDGE_PRESS.md` said every export command has a `make` target of
  the same name; `export-embedder` has none. It now names the three that do,
  and lists `export-web-moots`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
