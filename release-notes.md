# Release Notes -- v1.34.1

> Released: 2026-11-07

### Fixed

- **A moot turn with no `[sN]` tag is no longer grounded.** A reply with no
  tags and no quotes passed the grounding check, so the Forest showed a
  paraphrase with no sources as grounded and it was never retried. A turn now
  needs at least one `[sN]` tag naming one of its passages. A turn that only
  quotes the other book with `[oN]` also needs one. Without it, the turn gets
  the reminder retry and is marked ungrounded if it fails again.
- **An `[oN]` tag must name a turn already spoken.** A quote tagged with a
  turn that did not exist, such as `[o9]` in turn 2, was exempt from the
  grounding check, so an invented quote could pass under it. Such a tag now
  fails the turn, as an `[sN]` tag for a passage not given already did.
- **A grounded turn must repeat its own book's words.** A turn with one valid
  tag and an invented paraphrase passed. A turn now needs a quote found in its
  book, or a run of 6 or more words copied from its passages; models often
  copy a line without quote marks, so requiring a quote alone failed 6 of 8
  well-grounded turns in a live moot. The reminder retry now asks for at least
  one quote. In a live Meditations vs The Prince moot on anger, 7 of 8 turns
  were grounded and 3 were retried; the one ungrounded turn misquoted its book.
- **An invented quote cannot pass under an `[oN]` tag.** A quote is tied to
  the first tag after it, so an invented quote placed before a real quote of
  the other book was exempt from the check. An `[oN]` quote found neither in
  the turn it names nor in the speaker's book now counts as a missed quote of
  that book. An honest misquote of the other book now also fails the turn and
  is retried; snapping still corrects it in the transcript.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
