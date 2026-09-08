# Release Notes — v1.19.0

> Released: 2026-09-08

This release adds two complete, independently useful capabilities: a way to ship a
named subset of the corpus instead of the whole thing, and a native app that
remembers your conversations instead of forgetting them the moment it closes.

## What changed

**Ship a subset of the corpus, not all of it.** A small TOML spec names books by
genre, by a Gutenberg ebook_id, or by a bare directory name unique across genres —
deliberately with no fuzzy matching, so a misspelled or ambiguous selector fails
the command rather than silently picking the wrong book. `gutenkg bundle
validate`/`build`/`export`/`image`/`make` turn that spec into a filtered Swift
export, a filtered DocKG rebuild, or a tagged container image, and `make build`
now takes `SPEC=`/`BUNDLE=` to tag images by product rather than always
`:latest`. The filtering runs everywhere a subset touches — the catalog, the
passages, and the vector scan itself, without which a three-book export still
streamed the full corpus-wide vector store. Verified against the real corpus
throughout: a forced cross-genre naming collision, a measured 39-book build time,
and a container image built from source that answered a live query against
exactly the one book it was scoped to. `docs/BUNDLES.md` is the operator's guide.

**The native apps remember your conversations.** Every chat now survives a
relaunch — written as one directory per conversation, plain JSON with images kept
beside it rather than inlined, so a single rendered illustration can't bloat a
conversation file into something slow to list. The iPad and Mac both gained a
proper sidebar: chats grouped by day, search, swipe-to-delete, rename, with the
answer engine and corpus scope moved up beside the conversation list, since scope
is the single largest lever on how good an on-device answer is. The iPhone
reaches the same list from a toolbar button. A chat can now be exported as
Markdown through the system share sheet, with every quoted passage carrying its
work, author, genre, and score — an answer without its evidence being the one
thing this project exists not to produce.

**Rendered illustrations default to a size that doesn't time out.** The app used
to send no size at all on an image request, so the worker silently fell back to
its own largest preset. Settings now offers the same three presets the Streamlit
interface does, defaulting to the fastest one.

## Upgrading

No migration needed. Existing conversations are unaffected — the persistence
layer is new, not a change to a prior format. Rebuild the corpus packs
(`gutenkg export-swift`) to pick up the illustration-resolution default; nothing
else requires a rebuild.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
