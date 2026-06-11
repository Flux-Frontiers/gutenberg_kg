"""
test_local.py — smoke-test the handler without Docker or RunPod.

Usage (from gutenberg_kg/runpod/):
    KG_VOLUME=/path/to/local/indices python test_local.py

If KG_VOLUME is not set, a symlink to the local repo's .dockg/ is used
so you can test against your locally built indices.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _add_sibling_src_to_path() -> None:
    """Allow local smoke tests to import sibling packages from source trees.

    This keeps test_local.py usable outside Docker where kg-rag may not be
    installed into the active interpreter, but exists as a sibling repo.
    """

    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "kgrag" / "src",  # typical layout: repos/gutenberg_kg + repos/kgrag
        here.parents[2] / "KGRAG" / "src",  # fallback for case variants
        here.parents[2] / "kg_utils" / "src",
        here.parents[2] / "KG_utils" / "src",
    ]
    for src in candidates:
        if not src.is_dir():
            continue
        has_known_pkg = (src / "kg_rag").is_dir() or (src / "kg_utils").is_dir()
        if has_known_pkg:
            src_str = str(src)
            if src_str not in sys.path:
                sys.path.insert(0, src_str)


_add_sibling_src_to_path()

if "KG_VOLUME" not in os.environ:
    import pathlib
    import tempfile

    gutenberg_repo = pathlib.Path(__file__).parent.parent
    bundle = gutenberg_repo / "bundles" / "gutenberg-all"
    if not bundle.exists():
        raise SystemExit(
            f"Corpus bundle not found at {bundle}\n"
            "Run 'make build-corpus' first to generate bundles/gutenberg-all/."
        )
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gutenkg_vol_"))
    (tmp / "gutenberg_kg").symlink_to(bundle)
    os.environ["KG_VOLUME"] = str(tmp)
    print(f"[test] Using corpus bundle at {bundle}")

try:
    import handler  # noqa: E402  (triggers startup bootstrap)
except ModuleNotFoundError as exc:
    if exc.name in {"kg_rag", "kg_utils"}:
        raise SystemExit(
            "Missing dependency required by runpod handler.\n"
            "Install sibling deps or expose source trees for kg_rag and kg_utils.\n"
            "Examples:\n"
            "  pip install -e ../kg_utils -e ../kgrag\n"
            "  poetry -C ../kg_utils install && poetry -C ../kgrag install"
        ) from exc
    raise

TEST_CASES = [
    {
        "input": {
            "op": "models",
        }
    },
    {
        "input": {
            "query": "Marcus Aurelius on suffering and stoic virtue",
            "corpus": "philosophy",
            "k": 4,
        }
    },
    {
        "input": {
            "query": "redemption and moral transformation in Russian literature",
            "k": 5,
            "semantic_floor": 0.2,
        }
    },
    {
        "input": {
            "query": "the nature of justice and the good life in philosophy",
            "corpus": "gutenberg",
            "k": 6,
        }
    },
    {
        "input": {
            "query": "test",
            "corpus": "not-a-corpus",
        }
    },
]

for i, job in enumerate(TEST_CASES, 1):
    print(f"\n{'=' * 60}")
    if "op" in job["input"]:
        print(f"Test {i}: op={job['input']['op']}")
    else:
        print(f"Test {i}: {job['input']['query'][:60]}")
    result = handler.handler(job)
    if "error" in result:
        print(f"ERROR: {result['error']}")
    elif "models" in result:
        print(f"  models={len(result['models'])} default={result.get('default')}")
    else:
        print(
            f"  corpus={result.get('corpus')} kgs_queried={result['kgs_queried']} "
            f"total_hits={result['total_hits']} search_ms={result.get('search_ms')}"
        )
        for h in result["hits"]:
            print(f"  [{h['score']:.3f}] {h['source_path']} | {str(h['summary'])[:80]}")

print("\nAll tests done.")
