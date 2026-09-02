# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Convert the corpus embedder to Core ML for on-device query embedding.

The corpus packs hold ``bge-small-en-v1.5`` vectors.  A query embedded by any
other model — including Apple's own ``NLContextualEmbedding`` — lands in a
different space and returns noise that looks like results, so the app has to
carry *this* model.  At 33 M parameters it converts to about 65 MB of fp16
Core ML and runs on the Neural Engine in a few milliseconds.

What this writes
----------------
::

    <out>/
      BGEEmbedder.mlpackage   the traced encoder, fp16
      vocab.txt               the WordPiece vocabulary, verbatim from the tokenizer
      embedder.json           model id, dim, max length, pooling, special-token ids

``embedder.json`` exists so the Swift side has no constants of its own to drift.
The tokenizer it describes is BERT WordPiece, lowercase, and the pooling is
CLS — both are properties of *this* checkpoint, not assumptions, and both are
read from the loaded tokenizer and config rather than hardcoded here.

Dependencies
------------
``torch``, ``transformers`` and ``coremltools`` are not project dependencies —
this runs once per embedder change, on a Mac.  Install them into the same
environment before running::

    poetry run pip install torch transformers coremltools
    gutenkg export-embedder --out bundles/gutenberg-all/swift

Parity
------
The command embeds a fixed probe sentence with both PyTorch and the converted
Core ML model and reports the cosine between them.  Anything below 0.999 means
the conversion changed the model, and the packs' vectors would no longer be
comparable with what the app produces — so it fails rather than shipping a
model that returns plausible nonsense.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["EmbedderExportError", "EmbedderReport", "export_embedder"]

#: The checkpoint the corpus was built with.  Changing this invalidates every
#: pack, so it is not an option on the command.
MODEL_ID = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

#: bge-small is trained with 512-token inputs, but a *query* is a sentence.
#: A shorter fixed length is a smaller model and a faster Neural Engine run,
#: and it is what the app actually needs.
MAX_LENGTH = 64

#: Cosine below this between PyTorch and Core ML means the conversion changed
#: the model.  fp16 conversion normally lands at 0.9999+.
PARITY_FLOOR = 0.999

PROBE = "descriptions of the Great Fire of London"


class EmbedderExportError(RuntimeError):
    """The conversion could not run, or produced a model that failed parity."""


@dataclass
class EmbedderReport:
    """What the conversion produced."""

    package: Path
    vocab: Path
    metadata: Path
    parity: float
    bytes: int


def export_embedder(out: Path, *, compute_units: str = "ALL", progress=None) -> EmbedderReport:
    """Trace and convert the query embedder to Core ML.

    :param out: Directory to write into; created if absent.
    :param compute_units: Core ML compute units — ``ALL`` lets the Neural
        Engine take it, ``CPU_AND_GPU`` is the fallback for debugging a
        numerical difference.
    :param progress: Optional ``callable(str)`` for status lines.
    :returns: A report naming every file written, and the measured parity.
    :raises EmbedderExportError: If a dependency is missing, or the converted
        model does not agree with PyTorch.
    """
    say = progress or (lambda _message: None)
    try:
        import coremltools as ct
        import torch
        from transformers import AutoConfig, AutoModel, AutoTokenizer
    except ImportError as exc:
        raise EmbedderExportError(
            "conversion needs torch, transformers and coremltools:\n"
            "  poetry run pip install torch transformers coremltools"
        ) from exc

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    say(f"loading {MODEL_ID}…")
    # `AutoTokenizer.from_pretrained` is a dynamic factory whose declared
    # return type is a union of tokenizer backends and None, so a type checker
    # cannot see the BertTokenizerFast that actually comes back — nor any of
    # the special-token attributes read below. `Any` says that honestly; the
    # guard turns the None arm into a message instead of an AttributeError
    # eight lines later.
    tokenizer: Any = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer is None:
        raise EmbedderExportError(
            f"transformers returned no tokenizer for {MODEL_ID} — check the model id "
            "and that the download completed."
        )
    config = AutoConfig.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID).eval()

    if config.hidden_size != EMBED_DIM:
        raise EmbedderExportError(
            f"{MODEL_ID} has hidden size {config.hidden_size}, but the packs "
            f"hold {EMBED_DIM}-dimensional vectors"
        )

    class QueryEncoder(torch.nn.Module):
        """CLS pooling plus L2 normalisation, folded into the graph.

        Doing both here rather than in Swift means the app cannot get the
        pooling wrong, and the Core ML model's output is directly comparable
        with a pack vector.
        """

        def __init__(self, encoder):
            super().__init__()
            self.encoder = encoder

        def forward(self, input_ids, attention_mask):
            hidden = self.encoder(
                input_ids=input_ids, attention_mask=attention_mask
            ).last_hidden_state
            pooled = hidden[:, 0]  # bge pools on CLS, not by mean
            return torch.nn.functional.normalize(pooled, p=2, dim=1)

    wrapped = QueryEncoder(model).eval()
    example = tokenizer(
        PROBE, return_tensors="pt", padding="max_length", truncation=True, max_length=MAX_LENGTH
    )
    input_ids = example["input_ids"].to(torch.int32)
    attention_mask = example["attention_mask"].to(torch.int32)

    say("tracing…")
    with torch.no_grad():
        reference = wrapped(input_ids, attention_mask)
        traced = torch.jit.trace(wrapped, (input_ids, attention_mask))

    say("converting to Core ML (fp16)…")
    shape = (1, MAX_LENGTH)
    mlmodel = ct.convert(
        traced,
        inputs=[
            ct.TensorType(name="input_ids", shape=shape, dtype=int),
            ct.TensorType(name="attention_mask", shape=shape, dtype=int),
        ],
        outputs=[ct.TensorType(name="embedding")],
        compute_precision=ct.precision.FLOAT16,
        compute_units=getattr(ct.ComputeUnit, compute_units),
        minimum_deployment_target=ct.target.iOS18,
    )
    mlmodel.short_description = (
        f"{MODEL_ID} query encoder — CLS pooled, L2 normalised, {MAX_LENGTH} tokens"
    )

    package = out / "BGEEmbedder.mlpackage"
    if package.exists():
        import shutil

        shutil.rmtree(package)
    mlmodel.save(str(package))

    say("checking parity against PyTorch…")
    predicted = mlmodel.predict(
        {
            "input_ids": input_ids.numpy().astype("int32"),
            "attention_mask": attention_mask.numpy().astype("int32"),
        }
    )["embedding"]
    parity = _cosine(reference.numpy()[0], predicted.reshape(-1))
    if parity < PARITY_FLOOR:
        raise EmbedderExportError(
            f"Core ML output differs from PyTorch (cosine {parity:.5f} < {PARITY_FLOOR}). "
            "The converted model would not be comparable with the packs' vectors. "
            "Retry with --compute-units CPU_AND_GPU to isolate a Neural Engine "
            "numerical difference."
        )

    vocab = out / "vocab.txt"
    _write_vocab(tokenizer, vocab)

    metadata = out / "embedder.json"
    metadata.write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "dim": EMBED_DIM,
                "max_length": MAX_LENGTH,
                "pooling": "cls",
                "normalized": True,
                "tokenizer": {
                    "kind": "bert-wordpiece",
                    "lowercase": bool(getattr(tokenizer, "do_lower_case", True)),
                    "vocab": vocab.name,
                    "unk_token": tokenizer.unk_token,
                    "cls_token": tokenizer.cls_token,
                    "sep_token": tokenizer.sep_token,
                    "pad_token": tokenizer.pad_token,
                    "unk_id": tokenizer.unk_token_id,
                    "cls_id": tokenizer.cls_token_id,
                    "sep_id": tokenizer.sep_token_id,
                    "pad_id": tokenizer.pad_token_id,
                    "continuing_prefix": "##",
                },
                "parity": {"probe": PROBE, "cosine_vs_pytorch": round(float(parity), 6)},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return EmbedderReport(
        package=package,
        vocab=vocab,
        metadata=metadata,
        parity=float(parity),
        bytes=_directory_size(package),
    )


def _write_vocab(tokenizer: Any, destination: Path) -> None:
    """Write the WordPiece vocabulary, one token per line, id order.

    Taken from the loaded tokenizer rather than downloaded separately, so the
    file and the traced model can never be from different revisions.

    :param tokenizer: A loaded ``transformers`` tokenizer.
    :param destination: File to write.
    """
    vocab = tokenizer.get_vocab()
    ordered = [token for token, _ in sorted(vocab.items(), key=lambda item: item[1])]
    destination.write_text("\n".join(ordered) + "\n", encoding="utf-8")


def _cosine(a, b) -> float:
    """Cosine similarity between two 1-D arrays."""
    import numpy as np

    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denominator) if denominator else 0.0


def _directory_size(path: Path) -> int:
    """Total bytes under *path* — an ``.mlpackage`` is a directory."""
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
