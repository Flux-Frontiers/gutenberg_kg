# Release Notes -- v1.28.0

> Released: 2026-10-21

### Added

- **Book-scoped retrieval in the worker.** The `corpus` field now also takes
  a catalog key, `"<genre>/<book>"`, and searches that one book only. A
  `"diaries/<title>"` key searches that one diary's DiaryKG. The scope rules
  live in `serve/scope.py` so they can be tested without starting the worker;
  the RunPod worker (`runpod/handler.py`) uses the same module.
- **`gutenkg converse`** (Entmoot, phases 1 and 2): two books hold a moot,
  seeded with `--topic`. Each tree retrieves only from its own book, answers
  through the local model, and cites its passages with `[sN]` tags. A quote of
  its own book counts when it appears in any passage that book returned during
  the moot; a quote of the other tree is tagged `[oN]` (turn `N`), checked and
  reported separately, and never counts toward grounding. A quote with an
  ellipsis is checked fragment by fragment. The persona asks for at most four
  quoted phrases a turn, and the stats report `quotes_per_turn`. A failed turn
  is retried once, and the same book cannot be seated twice. The default
  model is `Qwen3.8-27B-4bit`; `--model` overrides it. `--out` writes a JSON
  transcript with grounding stats.
- **`gutenkg converse --backend`** picks the model provider, `omlx`, `ollama`
  or `openai`, the same choices the chat app offers, so a moot can run
  without a local model. It defaults to `SYNTH_BACKEND`, then `omlx`. Off
  omlx, the backend's own default model applies unless `--model` names one,
  and `openai` without `OPENAI_API_KEY` or `SYNTH_API_KEY` is a clean usage
  error.
- **Quote snapping in moots.** Every quote left in a moot transcript is now
  verbatim. After the grounding check, each quote of 3 or more words that
  was not found in its source is compared with that source (the speaker's
  passage pool, or the other tree's tagged turn for `[oN]`). When the
  source's words reach a similarity of 0.85 (`SNAP_MIN_RATIO`), they
  replace the quote's; otherwise the quotation marks come off and the words
  stand as paraphrase, as they also do for a missed quote with an ellipsis.
  Grounding is still measured on the model's raw reply, kept as `raw_text`;
  each correction is recorded in the utterance's `snaps`, and the stats add
  `quotes_snapped` and `quotes_unquoted`.
- **Moots print as a conversation.** On a terminal, `gutenkg converse`
  prints each turn as a Rich speech bubble as it arrives: the first book on
  the left in green, the second on the right in magenta, the turn number
  and title in the border in bold italic, quoted words in bold and citation
  tags dimmed, and each tree's name in the text in bold italic in that
  tree's color, so the reader sees who is addressed. The cited sections,
  any ungrounded warning and each snap or unquote go underneath. A header
  rule names the books, topic and model, and a
  grounding table closes the moot. Output that is not a terminal (pipes,
  logs, tests), or any run with the new `--plain`, prints the plain text as
  before.
- **A moot ends with a run summary**: start time, elapsed wall time, the
  average and slowest turn, backend and model, worker, host, machine (CPU
  and RAM), OS, and Python and gutenberg-kg versions. It prints as a table
  on a terminal and as plain lines otherwise, and `--out` records it under
  `run`, with every turn's seconds.
- **Quotes are at least three words.** The persona and the retry reminder
  ask for it, and snapping removes the quotation marks from any shorter
  quote, which is too short to check, so it reads as paraphrase. Every
  unquote now records its `reason` (`not in source`, `ellipsis` or
  `under 3 words`), and the stats count the short ones apart, as
  `quotes_too_short`, so `quotes_unquoted` still means a checked quote that
  failed.
- **Moots have a shape: turn intents.** Each turn is asked to make one
  move (`INTENTS`, scheduled by `turn_intent`): the first opens, each
  book's last turn closes (what it still holds, and what it takes from the
  other), and the turns between rotate through answer, ask a pointed
  question, give an example from the passages, and concede a point before
  pressing. The persona also forbids repeating a sentence already said.
  Each turn's `intent` is recorded in the transcript. On the Aurelius and
  Machiavelli moot this ended the echoed sentences (2 to 0), gave the moot
  a real close, and raised own-book quotes from 19 to 27.
- **Moots bring fresh passages and argue the point.** The strongest matches
  for a topic were the same every turn, so a book repeated its best lines
  (Machiavelli's "to appear merciful is useful" four times in eight turns).
  A book's later retrievals now ask the worker for twice as many hits
  (`FRESH_OVERFETCH`) and put passages it has already cited last, so each
  turn brings new text. The persona no longer calls a book a tree, which
  leaked into speech ("thou art an old tree"); it asks each book to answer
  the point the other just made rather than argue about how it was quoted,
  a tic in which nearly every turn opened "thou misquote me"; and it asks
  for at least one exact quote in every turn, since paraphrase cannot be
  checked.
- **`gutenkg author-voices`** records each author's voice for moots in
  `corpus/authors/voices.json`, beside the author pages and apart from
  ingestion. Gender comes from Wikidata's sex or gender (P21) and a coarse
  accent from country of citizenship (P27): `en-US` for an American
  citizenship (which wins, as for Henry James), `en-GB` for a British, Irish
  or Commonwealth one, and none otherwise, so translated authors keep the
  system's accent. Authors are found through their pages' Wikipedia links in
  batches; the few without one are searched by name and listed for review,
  and placeholders such as `Various` are not looked up. Each entry keeps its
  Wikidata item and citizenship labels for review. Existing entries are kept
  unless `--refresh`, and an entry marked `"source": "manual"` is never
  overwritten. The first run found 133 men, 15 women, 37 American and 57
  British, Irish or Commonwealth authors among 150. `export-web-moots` stamps
  each tree in a moot pack with its author's `voice` (`gender`, `accent`).
- **`gutenkg export-web-moots`** writes `converse --out` transcripts as moot
  packs for the Knowledge Press Forest (`../knowledge_press/web/public/moots/`
  by default, moved by `KNOWLEDGE_PRESS_DIR`, like the other web exports).
  A pack holds what the reader sees: the trees by worker key, the topic,
  date, model and backend, and each turn's corrected text, speaker,
  citations, grounding and corrections. It never carries the raw reply,
  prompts or retrieval queries. The id is a slug of both book names and the
  topic, and `index.json` is merged by id, so re-running a pairing on the
  same topic replaces its pack.
- **A tree speaks in its author's voice.** The persona still makes each
  tree the book, and now adds that it speaks with its author's voice: in
  the first person where the author wrote in the first person, and in the
  author's own style and diction. A book with no named author (an empty
  author, or `Various`, `Anonymous` or `Unknown`) speaks as itself, with no
  voice line and no "by".
- **A tree can quote itself.** `[oN]` now names any earlier turn of the
  moot, the speaker's own as well as the other tree's; turn numbers are
  unique, so the tag stays unambiguous. A quote of the speaker's own turn
  is recorded with source `self` and counted in `self_quotes_found` /
  `self_quotes_total`. Like quotes of the other tree, it never counts toward
  grounding: words spoken in the moot are model-written, not the book.
  Before this, such quotes were rejected, which was the only kind of invalid
  `[oN]` in a 27B test run.

### Fixed

- **A book no longer talks about its passages or claims what it lacks.**
  The persona told a book to "say so plainly" when no passage bore on a
  point, and the model turned that into claims about its whole text,
  saying a figure or event its book does contain "does not appear in my
  passages"; a book sees only part of its text each turn. The persona now
  has the book speak as itself, never mention passages, sources or what it
  was given, never claim its book lacks something, and turn to what it does
  say instead; and never check the other book's quotes against its own,
  which had read as "your citation appears to misquote my source". In
  testing, such talk fell from 11 instances in a moot to none.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
