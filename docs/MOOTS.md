# Moots: two books in conversation

A moot seats two books from the corpus and lets them talk about a topic. Each
book speaks only from passages of its own text, quotes them, and answers what
the other book just said. The name comes from Tolkien's Entmoot, the council of
the Ents: in the [Knowledge Press Forest](KNOWLEDGE_PRESS.md) every book is a
tree, so a moot is two trees talking.

A moot is model-written. A local or hosted language model writes each turn from
the passages its book returned; the book does not speak for itself. What the
moot guarantees is that every quotation in the finished transcript is the
book's exact words, or the words of an earlier turn, and that each book's
citations name passages it actually retrieved.

## Run a moot

You need two things running:

- **A worker** on `http://localhost:8000` (`make run`, or `--worker` for
  another URL). It does the book-scoped retrieval: each book searches only its
  own text. See [Installation](INSTALLATION.md).
- **A model backend** for the replies, chosen with `--backend`: `omlx` (the
  default), `ollama`, or `openai` (any OpenAI-compatible host, so no local
  model is needed). The worker is needed whatever the backend.

```bash
gutenkg converse "philosophy/Meditations" "philosophy/The Prince" \
    --topic virtue --out moot.json
```

Books are named by catalog key, `<genre>/<book>`. A diary is
`diaries/<title>`, searched in its own DiaryKG. Copy keys from
`bundles/gutenberg-all/.dockg/catalog.json` or the worker's `list_books` op;
the diary titles contain an em dash.

On a terminal, each turn prints as a speech bubble as it arrives: the first
book on the left in green, the second on the right in magenta. The passages a
turn cites and any quote corrections print under it. A grounding table and a
run summary (elapsed time, per-turn time, backend, model, machine) close the
run. Piped or logged output, or `--plain`, prints plain text instead.

| Option | Default | Meaning |
|---|---|---|
| `--topic` | none | Subject of the moot; anchors every retrieval. Recommended. |
| `--turns` | `8` | Total turns, both books together (2-40). |
| `--k` | `6` | Passages retrieved per turn. |
| `--backend` | `$SYNTH_BACKEND`, then `omlx` | `omlx`, `ollama` or `openai`. |
| `--model` | `Qwen3.8-27B-4bit` on omlx, else the backend's default | Model id. On omlx, `SYNTH_MODEL` does not apply. |
| `--temperature` | `0.6` | Sampling temperature. |
| `--worker` | `$KGRAG_ENDPOINT`, then `http://localhost:8000` | Worker URL. |
| `--out` | print only | Write the JSON transcript. |
| `--plain` | off | Plain text instead of speech bubbles. |

Backend settings: `omlx` reads `SYNTH_ENDPOINT` (default
`http://localhost:8080/v1`) and `SYNTH_API_KEY`; `ollama` reads
`OLLAMA_ENDPOINT` (default `http://localhost:11434/v1`); `openai` needs
`OPENAI_API_KEY` or `SYNTH_API_KEY`. When the worker sets a secret, `converse`
reads it from `HANDLER_SECRET`.

Model size matters. A 4B model such as `Qwen3-4B-Instruct-2507-MLX-8bit` is
about three times faster than the 27B default but quotes its book far less
reliably, so more of its quotes end up corrected or unquoted.

## How a turn is made

1. **Retrieval.** Each book first searches its own text for the topic alone.
   After that, a turn searches for the topic plus the other book's last turn.
   Passages a book has already cited go to the back, so each turn brings new
   text.
2. **The prompt.** The model is told it is the book, speaking in its author's
   voice (in the first person where the author wrote in the first person). A
   book with no named author, or one by `Various`, `Anonymous` or `Unknown`,
   speaks as itself. The model answers the other book's point, quotes its own
   passages at least once and at most four times, cites them as `[s1]`,
   `[s2]`, ..., and may quote any earlier turn `N` as `[oN]`. It never repeats
   a sentence already said and never talks about its passages.
3. **The turn's move.** Each turn has one intent, so the moot develops instead
   of circling one point: the first turn opens, the turns between rotate
   through answer, ask a pointed question, give an example, and concede a point
   before pressing, and each book's last turn closes the moot.
4. **Grounding.** The raw reply is checked: each `[sN]` tag must name one of
   this turn's passages, each quote of the speaker's own book must appear in a
   passage that book returned during the moot, and each `[oN]` quote must
   appear in turn `N`. Quotes of earlier turns are reported but never count as
   grounding, since words spoken in a moot are model-written. A turn that
   fails the check is retried once.
5. **Quote snapping.** Every quote left in the transcript is then made
   verbatim. A quote of 3 or more words that was not found is compared with its
   source; when the source's words match it closely (a similarity of at least
   0.85), they replace the quote. Otherwise the quotation marks come off and the
   words stand as paraphrase, as they also do for a quote with an ellipsis or
   one shorter than 3 words. Each correction is printed and recorded.

The rolling context is the last 3 turns verbatim plus a summary of the moot,
rebuilt every 4 turns.

## The transcript

`--out` writes JSON with each turn's corrected `text`, the model's `raw_text`,
its citations, its `intent`, and its corrections (`snaps`). The `stats` block
holds the grounding rates, measured on the raw replies, and the quote counts:
`quotes_snapped`, `quotes_unquoted`, and `quotes_too_short`. The run summary is
stored under `run`.

## Play moots in the forest

The [Knowledge Press Forest](https://flux-frontiers.github.io/knowledge_press/)
plays saved moots: the **Moots** button lists them, each turn appears as a
speech bubble, the speaking tree is ringed in its color, and the turns can be
read aloud. Playing a saved moot needs no worker and no model.

`gutenkg export-web-moots` turns `--out` transcripts into moot packs in a
sibling knowledge_press checkout (`KNOWLEDGE_PRESS_DIR` points elsewhere):

```bash
gutenkg export-web-moots moot.json         # -> ../knowledge_press/web/public/moots/
gutenkg export-web-moots runs/*.json --out /tmp/moots
```

A pack holds only what a reader sees: the corrected text, speakers, citations
and corrections, never the raw replies, prompts or retrieval queries. Its id is
both book names and the topic, so re-running a pairing on the same topic
replaces its pack, and `index.json` is merged rather than rewritten. The forest
publishes a pack when it is committed to knowledge_press `main`.

## Live moots from the forest

The forest can also hold a new moot against your local worker and play each
turn as it is made. The worker holds the moot: the forest starts it, asks for
one turn at a time, and may stop it.

| Op | Input | Returns |
|---|---|---|
| `moot_start` | `books` (two catalog keys), and optionally `topic`, `turns` (2-40, default 8), `k` (1-20, default 6), `model`, `temperature` (default 0.6) | `moot_id`, the pack `id`, `topic`, `date`, `model`, `backend`, `turns`, and `trees`, each with its author's `voice` |
| `moot_turn` | `moot_id` | `turn`, in the moot-pack form (text, speaker, citations, corrections), and `done`; the last turn adds `stats` |
| `moot_stop` | `moot_id` | `stopped` |

The model call uses the worker's own synthesis backend. A request may name a
model but not a backend, and the default model is chosen as for
`gutenkg converse`. A turn takes as long as the model needs: about 5 to 12
seconds with a 4B model on oMLX, longer with the 27B default. A worker holds
at most 4 live moots in memory. One left unasked for 30 minutes is dropped, a
full table drops the least recently used, and a restart ends them all. An
error comes back as RunPod's `{"status": "FAILED", "error": ...}`. A backend
failure leaves the moot in place, so the turn can be asked for again.

Two settings let a browser reach the worker:

- **`GUTENKG_CORS_ORIGINS`**: the origins allowed to call it, comma
  separated. `docker compose` and `make run` default to the forest's dev
  server, `http://localhost:5173`, and the published forest,
  `https://flux-frontiers.github.io`. Set it empty to turn CORS off.
- **`MOOT_TOKEN`**: optional. When set, the moot ops need it as `token`,
  and the forest sends it in place of `HANDLER_SECRET`, which never reaches
  a browser. On a worker with neither set, the moot ops need nothing, as
  every other op.

Browsers differ on reaching `http://localhost` from the published https
forest (checked 2026-10-21):

| Forest at | Chrome | Safari |
|---|---|---|
| `http://localhost:5173` (`make web-dev` in knowledge_press) | works | works |
| `https://flux-frontiers.github.io/knowledge_press/` | works after you allow local network access when Chrome asks | blocked: Safari refuses insecure content on a secure page |

## Author voices

Each tree in a moot pack carries its author's voice (`gender` and `accent`), so
the forest reads a woman's book in a woman's voice and an American author in
an American voice where the browser has one. `gutenkg author-voices` builds
the table, `corpus/authors/voices.json`, from Wikidata: gender from sex or
gender (P21), and an accent from country of citizenship (P27), `en-US` for an
American citizenship, `en-GB` for a British, Irish or Commonwealth one, and
none otherwise, so translated authors keep the browser's default accent.
Ingestion does not touch the table.

```bash
gutenkg author-voices                      # look up authors not yet in the table
gutenkg author-voices --refresh            # look everyone up again
gutenkg author-voices --dry-run            # print the table instead of writing it
```

An entry with `"source": "manual"` is never overwritten, so a hand correction
survives `--refresh`.

## Limits

- A moot is only as good as the model. Small models quote less reliably and
  argue less well; the grounding table shows how a run did.
- Retrieval sees passages, not whole books. A book with an appended work (an
  essay or a second text in the same file) can quote that work as if it were
  the main one.
- Some translations carry footnote markers in their text, which can show up
  inside a quote as a number fused onto a word.
