# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Regenerate the tokenizer parity fixture from the real BertTokenizer.

`WordPieceTokenizer.swift` is a port of `tokenization_bert.py`, and the corpus
vectors were produced by the original.  A word split differently sends the query
elsewhere in the embedding space and returns fluent, ranked, wrong passages —
silently.  `TokenizerParityTests` pins the two together, and this writes what it
pins them to.

Run it when the embedder changes, and only then; the output is checked in.
`transformers` is not a project dependency (nor is it needed to run the tests):

    poetry run pip install transformers
    poetry run python scripts/make_tokenizer_fixture.py

Writes `vocab.txt` — byte-identical to what `export_embedder` ships beside the
model — and `tokenizer_fixture.json` into the Swift test fixtures directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from transformers import AutoTokenizer

FIXTURES = (
    Path(__file__).resolve().parents[1] / "app/GutenbergKGKit/Tests/GutenbergKGKitTests/Fixtures"
)

tok = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")

vocab = tok.get_vocab()
ordered = [t for t, _ in sorted(vocab.items(), key=lambda kv: kv[1])]
FIXTURES.mkdir(parents=True, exist_ok=True)
(FIXTURES / "vocab.txt").write_text("\n".join(ordered) + "\n", encoding="utf-8")

CASES = [
    # the twelve golden queries the parity gate replays
    "pillar of salt",
    "circles of Hell",
    "What does the Quran say about Moses?",
    "the whiteness of the whale",
    "descriptions of the Great Fire of London",
    "the categorical imperative and moral duty",
    "a monster assembled from dead body parts",
    "time travel to the distant future",
    "the fall of the House of Usher",
    "how to wire an electric bell",
    "shipwreck on a desert island",
    "a dinner party with too much wine in a London diary",
    # adversarial: the shapes that break a hand-written WordPiece
    "don't",
    "Café",
    "naïve café résumé",
    "coöperate",
    "Hello,   world!!!",
    "The Diary of Samuel Pepys — Complete",
    "1666-09-02",
    "ISBN 978-0-14-243726-4",
    "R2-D2 & C-3PO",
    "antidisestablishmentarianism",
    "supercalifragilisticexpialidocious",
    "  leading and trailing   ",
    "?!",
    "",
    "   ",
    "MiXeD CaSe WoRdS",
    "e.g. i.e. etc.",
    "Mr. O'Brien's façade",
    # control and replacement characters the cleaner is supposed to drop
    "null\x00and\ufffdreplacement",
    "tab\tand\nnewline",
    # scripts: Greek strips accents; CJK segmentation is deliberately absent,
    # so this case measures the known gap rather than asserting it away
    "Ἀχιλλεύς",
    "Zhōngwén 中文",
    "a" * 250,  # longer than maxCharactersPerWord -> a single [UNK]
    " ".join(["word"] * 80),  # forces truncation at max_length
]

out = []
for text in CASES:
    tokens = tok.tokenize(text)
    encoded = tok(text, padding="max_length", truncation=True, max_length=64)
    out.append(
        {
            "text": text,
            "tokens": tokens,
            "ids": tok.convert_tokens_to_ids(tokens),
            "encoded": encoded["input_ids"],
            "mask": encoded["attention_mask"],
        }
    )

with (FIXTURES / "tokenizer_fixture.json").open("w", encoding="utf-8") as fh:
    json.dump(
        {
            "model": "BAAI/bge-small-en-v1.5",
            "max_length": 64,
            "lowercase": bool(tok.do_lower_case),
            "unk": tok.unk_token_id,
            "cls": tok.cls_token_id,
            "sep": tok.sep_token_id,
            "pad": tok.pad_token_id,
            "cases": out,
        },
        fh,
        ensure_ascii=False,
        indent=1,
    )

print(f"{len(out)} cases, vocab {len(ordered)} -> {FIXTURES}")
