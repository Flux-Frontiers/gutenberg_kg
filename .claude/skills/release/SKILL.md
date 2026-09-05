---
name: release
description: >
  Cut a GutenbergKG release — verify every version and doc surface is in sync,
  promote the changelog, regenerate release notes, tag, and push. Use when
  releasing gutenberg_kg / gutenkg, cutting a version, or tagging v*.
---

# Release Workflow (gutenberg_kg / GutenbergKG)

Releases here are **tag-triggered**. Pushing a `v*` tag runs
`.github/workflows/release.yml`, which builds the wheel and sdist and creates a
GitHub Release from `release-notes.md` via `gh release create --notes-file`.

**This repo does not publish to PyPI.** There is no OIDC trusted publishing and
no PyPI step — the release is a GitHub Release with the dist attached. That
makes a bad tag recoverable: delete the release and the tag, fix, re-tag. Do
not import the "PyPI accepts a version once, there is no undo" caution from the
kg_utils release skill; it is a different repo with a different workflow.

What is *not* trivially recoverable is a wrong `release-notes.md`, because the
GitHub Release body is written from it at tag time.

---

## Step 0 — Preconditions

```bash
git checkout main && git pull origin main
git status --porcelain          # must be empty
```

`main` must already carry the work being released. This repo develops on
`develop` and promotes to `main` by PR, so the usual order is: land the work on
`develop`, promote `develop` → `main`, then release from `main`.

Confirm `## [Unreleased]` in `CHANGELOG.md` has content. If it is empty there is
nothing to release — stop.

## Step 1 — Decide the version

Read `version` in `pyproject.toml`. If a `chore(release): bump version to X.Y.Z`
commit already landed, adopt it and skip the bump in Step 3. The tag is
`v<version>`.

**Check the tag actually exists for the version in `pyproject.toml`.** This repo
has shipped bumps that were never tagged — 1.16.0 and 1.17.0 both landed as
version bumps with no changelog section and no tag, so `pyproject.toml` claimed
a version that had never been released. `git tag` is the source of truth for
what shipped, not `pyproject.toml`.

```bash
git tag --sort=-v:refname | head -5
grep -n '^version' pyproject.toml
```

If they disagree, the untagged versions have no distinct changelog content —
their work is pooled in `[Unreleased]`. Do not invent boundaries to backfill
them. Release the whole span under one new version and say so in the commit.

## Step 2 — Promote the changelog

Replace `## [Unreleased]` with `## [<version>] - <YYYY-MM-DD>` and insert a
fresh empty `## [Unreleased]` above it.

**One ASCII hyphen** between version and date — `fleet_audit.py` parses this
heading strictly, and the strictness is the point.

**Consolidate while you are in there.** Successive cycles leave duplicate
`### Added` / `### Changed` / `### Fixed` headings stacked in `[Unreleased]` —
the 1.18.0 release merged four `Added` and two `Fixed`. Also re-file entries
that sit under `Added` but describe a fix; several bug fixes have been filed as
`Added` because the cycle's entry was appended under whatever heading was last.

**Check the merged PRs since the last release actually have entries.** #111 and
#112 had none at 1.18.0 and had to be written from their commit messages:

```bash
git log --oneline --no-merges <last-tag>..HEAD
```

## Step 3 — Bump the version (skip if already done)

- `pyproject.toml` → `version = "..."`
- `src/gutenberg_kg/__init__.py` → `__version__ = "..."`

`poetry lock` is **not** needed for a version bump here — the package version
does not appear in `poetry.lock`. Run it only if dependencies changed.

## Step 4 — THE SYNC AUDIT

Six version surfaces must agree. Check all of them explicitly; do not assume a
previous release left them correct.

```bash
grep -n '^version' pyproject.toml
grep -n '__version__' src/gutenberg_kg/__init__.py
grep -n '^version:\|^date-released:' CITATION.cff
grep -n '[0-9]\+\.[0-9]\+\.[0-9]\+' README.md
grep -n 'gutenkg: ' docs/CORPUS.md
```

- [ ] `pyproject.toml`
- [ ] `src/gutenberg_kg/__init__.py`
- [ ] `CITATION.cff` `version:` — **and `date-released:`**, a second stale field
      hiding behind the first. It was still `2026-09-01` at the 1.18.0 release,
      two bumps after that date.
- [ ] `README.md` version badge (the shields.io URL, ~line 11)
- [ ] `README.md` **BibTeX** — `version      = {X.Y.Z},`
- [ ] `docs/CORPUS.md` — the `> - gutenkg: \`X.Y.Z\`` stamp near the top

Note what this repo does **not** have, so you do not go looking: no APA citation
block in the README (BibTeX only), no "Latest News" section, and no
`docs/features.md`.

**Corpus counts are a separate surface with its own skill.** If books were
added, removed or re-ingested this cycle, the README badges, the "Corpus at a
Glance" table, the intro prose, the partnership blurb, the BibTeX corpus totals
and `docs/CORPUS.md` are all stale. Use the **`sync-corpus-docs`** skill for
those rather than editing them here — it knows which numbers come from where.
`scripts/regenerate_corpus_doc.py` regenerates `docs/CORPUS.md` and needs the
live corpus, so it cannot run in a container that has no corpus; in that case
update the version stamp by hand and leave the counts alone.

**Prose must describe what actually shipped.** A new command or module is not
released until it is documented — check `README.md` and the relevant
`docs/*.md` guide name it. Read every grep hit rather than counting them;
substring matches on unrelated features are common.

## Step 5 — Regenerate `release-notes.md`

`release.yml` feeds this file to `gh release create --notes-file`. If it is
stale the GitHub Release describes **the previous release**. It was still at
v1.15.0 when 1.18.0 was cut, two versions behind.

Generate it from the changelog rather than by hand, so the two cannot drift:

```python
import pathlib, re
VERSION, DATE = "1.18.0", "2026-09-05"
cl = pathlib.Path("CHANGELOG.md").read_text()
body = re.search(rf"^## \[{re.escape(VERSION)}\] - {DATE}\n(.*?)(?=^## \[)",
                 cl, re.S | re.M).group(1).strip("\n")
pathlib.Path("release-notes.md").write_text(
    f"# Release Notes -- v{VERSION}\n\n> Released: {DATE}\n\n{body}\n\n"
    "---\n\n_Full changelog: [CHANGELOG.md](CHANGELOG.md)_\n"
)
```

The heading uses `--`, not an em dash, matching the existing file. Confirm the
first line names the version you are releasing.

## Step 6 — Verify the build is green

```bash
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run ruff format --check .
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run ruff check .
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run ty check src/ --exclude src/gutenberg_kg/viz3d.py
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run pytest --tb=short -q
python3 scripts/check_pins.py
python3 scripts/check_docs_build.py
```

The `env -u` prefix is not optional: an inherited `VIRTUAL_ENV` silently
retargets `poetry run` at another repo's interpreter, and the tests then pass
against the wrong dependency set.

All six are pre-commit hooks except `check_pins.py`, so a normal commit has
already run most of them. `check_pins.py` and the `Installed CLI` job have no
local equivalent — they catch KG pin drift across
`pyproject` / `poetry.lock` / `docker/Dockerfile` / `runpod/requirements.txt`
and wheel packaging respectively. `check_pins.py` also prints a "Behind PyPI"
advisory when a KG dependency has a newer release; that is informational — the
KG pins move as a set, not per release — and is not a reason to hold the tag.

CI note: `ci.yml` gates Lint, Type Check and Test to **pushes and PRs against
`main`** only. They are skipped on `develop`, so a merge into `develop` proves
much less than it appears to. `main` is where those three actually run.

## Step 7 — Commit and tag

```bash
git add CHANGELOG.md release-notes.md README.md CITATION.cff \
        docs/CORPUS.md pyproject.toml src/gutenberg_kg/__init__.py
git commit -m "chore(release): v<version> release notes"
git tag -a v<version> -m "v<version>"
```

## Step 8 — Push (ASK FIRST — always)

Never push the tag autonomously. Show the sync-audit result and the tag, and get
explicit approval. The tag push is what publishes.

```bash
git push origin main
git push origin v<version>
```

Then watch the run: build → GitHub Release. Confirm the release body on GitHub
is this version's notes and that the wheel and sdist are attached.

## Step 9 — Put the release back on `develop`

`main` now carries a release commit that `develop` does not, and the next
promotion PR will conflict on `CHANGELOG.md` if it is left there.

```bash
git checkout develop && git pull origin develop
git merge main            # or fast-forward if develop has not moved
git push origin develop
```

Keep `develop`; it is the working branch, not a throwaway feature branch.

---

## Known environment quirk

`git push --delete` of a remote branch fails in the Claude Code remote
container (`send-pack: unexpected disconnect`, then a misleading "Everything
up-to-date"), and the GitHub MCP server has no delete-branch tool. Branch
deletion is a manual step for the user.
