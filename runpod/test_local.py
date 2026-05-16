"""
test_local.py — smoke-test the handler without Docker or RunPod.

Usage (from gutenberg_kg/runpod/):
    KG_VOLUME=/path/to/local/indices python test_local.py

If KG_VOLUME is not set, a symlink to the local repo's .dockg/ is used
so you can test against your locally built indices.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if "KG_VOLUME" not in os.environ:
    import pathlib
    import tempfile

    gutenberg_repo = pathlib.Path(__file__).parent.parent
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gutenkg_vol_"))
    (tmp / "gutenberg_kg").symlink_to(gutenberg_repo)
    os.environ["KG_VOLUME"] = str(tmp)
    print(f"[test] Using local volume symlink at {tmp}")

import handler  # noqa: E402  (triggers startup bootstrap)

TEST_CASES = [
    {
        "input": {
            "query": "Marcus Aurelius on suffering and stoic virtue",
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
            "k": 6,
        }
    },
]

for i, job in enumerate(TEST_CASES, 1):
    print(f"\n{'=' * 60}")
    print(f"Test {i}: {job['input']['query'][:60]}")
    result = handler.handler(job)
    if "error" in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"  kgs_queried={result['kgs_queried']}  total_hits={result['total_hits']}")
        for h in result["hits"]:
            print(f"  [{h['score']:.3f}] {h['source_path']} | {str(h['summary'])[:80]}")

print("\nAll tests done.")
