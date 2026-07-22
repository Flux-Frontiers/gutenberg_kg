"""Tests for the live handler's standard-query relevance checks."""

import runpy
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "check_standard_queries.py"
_has_expected_title = runpy.run_path(_SCRIPT, run_name="check_standard_queries_test")[
    "_has_expected_title"
]


def test_has_expected_title_accepts_fragment_within_rank():
    hits = [{"title": "Unrelated"}, {"title": "The Divine Comedy (Cary's Translation)"}]

    assert _has_expected_title(hits, ("The Divine Comedy",), rank=2)


def test_has_expected_title_rejects_fragment_below_rank():
    hits = [{"title": "Unrelated"}, {"title": "War and Peace"}]

    assert not _has_expected_title(hits, ("War and Peace",), rank=1)


def test_has_expected_title_falls_back_to_name_case_insensitively():
    hits = [{"name": "THE DIARY OF SAMUEL PEPYS — COMPLETE"}]

    assert _has_expected_title(hits, ("Samuel Pepys",), rank=1)
