"""Package version smoke test."""

import gutenberg_kg


def test_version_is_string():
    assert isinstance(gutenberg_kg.__version__, str)


def test_version_non_empty():
    assert gutenberg_kg.__version__ != ""
