"""model_setup.py - Ensure local ML models used by the pipeline are present.

Two models are needed on the machine that runs ``chunk-diaries`` / ``ingest`` /
``build-corpus`` (they are never downloaded at Docker runtime — see
``docker/Dockerfile``, which pre-downloads only the embedder and never touches
spaCy since chunking happens locally before the image is built):

- ``en_core_web_sm``       spaCy model used by ``diary-transformer`` for
                           sentence segmentation (``gutenkg chunk-diaries``).
- ``BAAI/bge-small-en-v1.5``  sentence-transformers embedder used by both
                           ``gutenkg ingest`` and ``gutenkg build-corpus``
                           (must match ``EMBED_MODEL`` in the Docker image).

Neither is a pip dependency: the spaCy model ships via ``spacy download``, and
the embedder is fetched from HuggingFace on first use. A fresh clone + venv
has neither, and the failure only surfaces mid-pipeline (see
``diary/chunk.py``), which is what this module lets ``gutenkg init`` catch
up front instead.
"""

from __future__ import annotations

from dataclasses import dataclass

SPACY_MODEL = "en_core_web_sm"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass
class ModelCheckResult:
    """Outcome of checking (and optionally fetching) one model."""

    name: str
    kind: str  # "spacy" | "embedder"
    status: str  # "ok" | "downloaded" | "missing" | "failed"
    message: str = ""


def _check_spacy(download: bool) -> ModelCheckResult:
    try:
        import spacy
    except ImportError as exc:
        return ModelCheckResult(SPACY_MODEL, "spacy", "failed", f"spacy not installed: {exc}")

    try:
        spacy.load(SPACY_MODEL)
        return ModelCheckResult(SPACY_MODEL, "spacy", "ok", "already installed")
    except OSError:
        pass

    if not download:
        return ModelCheckResult(
            SPACY_MODEL, "spacy", "missing", f"run: python -m spacy download {SPACY_MODEL}"
        )

    try:
        from spacy.cli.download import download as spacy_download

        spacy_download(SPACY_MODEL)
        spacy.load(SPACY_MODEL)
        return ModelCheckResult(SPACY_MODEL, "spacy", "downloaded", "fetched successfully")
    except Exception as exc:  # noqa: BLE001
        return ModelCheckResult(SPACY_MODEL, "spacy", "failed", str(exc))


def _check_embedder(download: bool) -> ModelCheckResult:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        return ModelCheckResult(
            EMBED_MODEL, "embedder", "failed", f"sentence-transformers not installed: {exc}"
        )

    try:
        SentenceTransformer(EMBED_MODEL, local_files_only=True)
        return ModelCheckResult(EMBED_MODEL, "embedder", "ok", "already cached")
    except Exception:  # noqa: BLE001
        pass

    if not download:
        return ModelCheckResult(
            EMBED_MODEL, "embedder", "missing", "not cached locally (needs network to fetch)"
        )

    try:
        SentenceTransformer(EMBED_MODEL)
        return ModelCheckResult(EMBED_MODEL, "embedder", "downloaded", "fetched successfully")
    except Exception as exc:  # noqa: BLE001
        return ModelCheckResult(EMBED_MODEL, "embedder", "failed", str(exc))


def check_models(download: bool = True) -> list[ModelCheckResult]:
    """Check (and by default fetch) every model the local pipeline needs.

    :param download: When True, missing models are downloaded. When False,
        this only reports what's missing (use for a dry ``--check``).
    :returns: One :class:`ModelCheckResult` per model, spaCy first.
    """
    return [_check_spacy(download), _check_embedder(download)]
