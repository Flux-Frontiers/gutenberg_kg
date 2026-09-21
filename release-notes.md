# Release Notes -- v1.22.2

> Released: 2026-09-21

### Fixed

- **A cast is framed like the window, not at VTK's default FOV.** PyVista's
  `camera_position` is (position, focal point, view up) and carries no view
  angle, so `cast_scene_to_looking_glass`'s fresh off-screen plotter kept
  VTK's default 30 degrees while the window sat at the `RENDER_FOV` of 14
  that **Frame for Render** had set. The subject landed
  tan(15)/tan(7) = 2.2x too small on the panel, about eight scroll-wheel
  steps to undo by hand -- and since Frame for Render is the documented step
  before casting, that was the normal path. `create_forest_visualization`
  does not set the angle, so the cast builder now carries it across.

- **`pycode-kg` leaves the published `kgdeps` extra for the optional `kg`
  Poetry group.** Nothing under `src/` or `app/` imports `pycode_kg`: it is
  the `pycodekg` CLI and MCP server this repo *runs*, served to agents from
  `.venv/bin/pycodekg-mcp` in `.mcp.json`. An extra is published metadata, so
  `pip install gutenberg-kg[kgdeps]` handed every consumer a sibling KG
  package -- and torch and sentence-transformers behind it -- for tooling they
  will never run. `ftree_kg` made the same move for the same reason.

  `kg-rag` stays in `kgdeps` and is correct there: `gutenberg_kg.ingest`,
  `.audit`, `.export_swift` and `.serve.handler` all import it, so it is a
  feature of this package. The two were grouped because their transformers
  floors move together, which is a resolver constraint rather than a reason to
  publish both.

  Verified against the built wheel's `METADATA`, not `pyproject.toml`:
  `pycode-kg` appears nowhere in it, and `Provides-Extra: kgdeps` survives.
  Maintainers now want `poetry install --with dev,kg`; `docs/INSTALLATION.md`
  says so and its extras table no longer advertises `pycode-kg`.

### Changed

- **Fleet dependency floors raised and relocked** (`kgrag_priv` sweep items 46
  and 49): `kgmodule-utils` to `>=0.23.0`, `doc-kg` to `>=0.27.0`, `kg-rag` to
  `>=0.16.0`, `pycode-kg` to `>=0.27.1`, `diary-kg` to `>=0.100.0` (moved
  at release by `scripts/check_pins.py --bump`, in the Dockerfile ARG, the
  runpod floor and the lock as well), `quiltwright` to `>=0.15.0` in both
  places it is declared, and `ruff` from `>=0.4.0` to `>=0.15` inside the
  existing `<0.16` cap. The 2026-09-20 fleet releases put every consumer's
  lock behind them; this is the currency bump that follows.

- **The `kg` Poetry group is gone** (`kgrag_priv` sweep item 50, phase 1).
  It held `pycode-kg`, a tool this repo runs but never imports. Under the fleet's
  "tools are global" rule a tool is installed once with `uv tool` and is
  never a dependency of the repo; 20 of 22 clones were carrying their own
  copy, and every copy was a lock entry that drifted on each release.
  `doc-kg` stays: `build_corpus`, `ingest`, `serve.handler` and
  `cli.cmd_imagine` all import it, so it is a library here, not a tool.
  The import is the test. The `kgdeps` comment in `pyproject.toml` that still
  pointed at the group is corrected (#154).
- **GitHub Actions moved off Node 20** (#149): the workflow actions are on
  their Node 24 majors ahead of GitHub retiring the Node 20 runtime.
- **Corpus snapshots**: the 1.22.0 release snapshot is committed, and one
  snapshot whose key named no commit was pruned (#148).

- **The `kg-rag` pin moved in all four places it lives, not one.**
  `scripts/check_pins.py` caught the other three: `docker/Dockerfile`'s
  `ARG KG_RAG_VERSION` and `runpod/requirements.txt` both still said 0.15.0,
  which would have had the index built by 0.16.0 and read by 0.15.0, and would
  have let `pip install .` silently upgrade past an ARG that then named a
  version no build actually runs. Lock, Dockerfile, pyproject floor and runpod
  now agree.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
