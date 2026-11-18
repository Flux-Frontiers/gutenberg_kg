# Release Notes -- v1.40.0

> Released: 2026-11-18

### Changed

- **The worker serves `/runsync` itself instead of through RunPod's local
  test server.** `serve/worker_api.py` is a small FastAPI app that keeps the
  request and reply format: replies to every op and error case were compared
  with the RunPod server's, and the envelope, status codes, validation errors
  and CORS headers match. Differences no client uses: the `id` loses its
  `test-` prefix, and only `/runsync` is served
  (RunPod's `/run`, `/status` and `/stream` are gone). The
  image drops `runpod` and pins the `fastapi` and `uvicorn[standard]` versions
  it used to bring in. `gutenkg-handler` takes `--host` and `--port`, and
  still accepts `--rp_serve_api`, `--rp_api_host` and `--rp_api_port`, so
  compose files and Makefiles already checked out keep working.
- **An exception in the worker no longer sends its traceback to the client.**
  RunPod's server put the error type, message and full traceback in the
  reply, exposing file paths to anyone who can reach the worker. The reply now
  says the worker hit an internal error and names the job; the traceback is
  in the worker's log under that job id. Errors the handler returns, such as
  `book not found`, are unchanged.

### Fixed

- **Renders no longer arrive cut short from an Apple `container` worker.**
  `container`'s port forwarder drops bytes it has not yet relayed when the
  server closes the connection, so 2-9 MB render replies reached slow or
  remote clients truncated (Python `IncompleteRead`, curl error 18). The worker
  now lets the client close first: it holds the end of a `Connection: close`
  reply until the client hangs up (up to 300 s), and keeps idle connections
  open for 300 s instead of uvicorn's 5. `docs/APPLE_CONTAINERS.md` has the
  measurements.
- **`make models` downloads into the directory oMLX scans.** It always used
  `~/.omlx/models`, so with oMLX's `model_dirs` pointed elsewhere the download
  succeeded but the rescan never found it, and the run failed with "oMLX does
  not list ... after the rescan". It now uses the first of `model.model_dirs`
  in `~/.omlx/settings.json`, else `model.model_dir`, else `~/.omlx/models`,
  and checks free space on that volume.
- **`make run RUNTIME=apple` stops early when the worker image is missing.**
  Without a local image, `container run` tried to pull
  `docker.io/library/corpus-gutenberg` and failed with a confusing error. It
  now says to run `make pull-worker-image RUNTIME=apple` or
  `make build RUNTIME=apple`.

### Documentation

- **Publishing the worker image needs Docker Desktop's Rosetta, not QEMU.**
  `docs/INSTALLATION.md` now says so: under QEMU the amd64 half segfaults
  (exit 139) importing torch, and after a restart Docker can fall back to QEMU
  silently. It gives the error text, the off-and-on Rosetta toggle, a binfmt
  check, and Docker at 12 GB or more for publishing (#264).
- **The cheatsheet names the 8B default** and its `omlx serve` line (#263).

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
