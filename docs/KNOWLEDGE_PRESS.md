# The Knowledge Press apps

GutenbergKG builds the library. The ways to read it live in a separate repo,
[knowledge_press](https://github.com/Flux-Frontiers/knowledge_press), with its
own [documentation](https://flux-frontiers.github.io/knowledge_press/docs/).
This page covers what each reader is, its status, and what it needs from this
repo.

## Three ways to read the corpus

| Reader | Where it lives | Status |
|---|---|---|
| Chat UI (reading room) | This repo: Streamlit in front of the query worker | Available. See [Chat UI](CHAT_UI.md) and [Installation](INSTALLATION.md#docker-workflow). |
| Knowledge Press Forest | knowledge_press `web/`, a Vite, React and Three app | Available at [flux-frontiers.github.io/knowledge_press](https://flux-frontiers.github.io/knowledge_press/). Nothing to install. |
| Knowledge Press app for iPhone, iPad and Mac | knowledge_press `app/`, Swift with XcodeGen | In development for App Store deployment. Not yet on the App Store. |

### Knowledge Press Forest

Every book in the corpus is a tree, grown from its DocKG graph by the same
space-colonization rule `gutenkg viz3d` uses. You drive through genre groves,
open a book from its tree, and read its chapters in the browser. The
[Forest guide](https://flux-frontiers.github.io/knowledge_press/docs/forest/getting-started/)
covers the controls.

### Knowledge Press app

The app searches the corpus on the device and writes answers with the
language model built into iOS 26 and macOS 26, so it works with the network
off. It is in development for App Store deployment. Until it ships, it can be
built from source; the
[app RUNBOOK](https://github.com/Flux-Frontiers/knowledge_press/blob/main/app/RUNBOOK.md)
is the full path from a built corpus to the app answering on a device, and
the [App guide](https://flux-frontiers.github.io/knowledge_press/docs/app/getting-started/)
covers using it.

## What the readers need from this repo

knowledge_press builds no corpus. Its contract with GutenbergKG is data: the
files these commands write.

| Command | Writes | Read by |
|---|---|---|
| `gutenkg export-swift` | `core.pack`, `gutenberg.pack`, `diaries.pack`, their `.vectors`, `manifest.json`, `golden.json` under `bundles/<bundle>/swift/` | The app. See [On-device corpus packs](ON_DEVICE.md). |
| `gutenkg export-embedder` | The Core ML query embedder, beside the packs | The app |
| `gutenkg export-web-catalog` | The forest's book catalog, `web/src/game/catalog*.ts` | The forest |
| `gutenkg export-web-books` | One `web/public/books/<slug>.json` per book, built from the Swift packs | The forest's reader |

Each has a `make` target of the same name. Run `gutenkg ingest` before
`export-web-catalog`, and `export-swift` before `export-web-books`. The
[cheatsheet](CHEATSHEET.md#web-forest-catalog) has the options.

## Side-by-side checkouts

The two repos expect to sit next to each other:

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
git clone https://github.com/Flux-Frontiers/knowledge_press
```

This repo's `export-web-*` targets write into `../knowledge_press`; set
`KNOWLEDGE_PRESS_DIR` to point elsewhere. knowledge_press's Makefile finds the
corpus at `../gutenberg_kg`; set `GUTENBERG_KG_DIR` to point elsewhere.

## Licenses

The knowledge_press `web/` directory is Elastic-2.0, like this repo. The app
in `app/` is proprietary. The names and artwork are covered by
[TRADEMARK.md](https://github.com/Flux-Frontiers/knowledge_press/blob/main/TRADEMARK.md).
