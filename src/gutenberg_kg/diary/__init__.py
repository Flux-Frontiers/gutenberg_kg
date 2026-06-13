"""Gutenberg diary parsing — convert raw Gutenberg markdown to dated PSV entries.

Stage ① of the diary pipeline: the Gutenberg-specific date parsing that turns a
raw book ``.md`` into a ``DiaryTransformer``-compatible ``.diary_source.psv``.
Downstream chunking (PSV → ``.diary/``) and indexing (``.diary/`` → ``.diarykg/``)
are handled by the native ``diary_kg`` / ``diary_transformer`` packages.
"""

from .parser import BaseDiaryParser, ParsedEntry, get_parser, parse, write_psv

__all__ = [
    "BaseDiaryParser",
    "ParsedEntry",
    "get_parser",
    "parse",
    "write_psv",
]
