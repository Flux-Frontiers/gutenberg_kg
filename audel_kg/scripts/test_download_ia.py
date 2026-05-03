#!/usr/bin/env python3
"""Unit tests for download_ia.py — run with: python scripts/test_download_ia.py"""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from download_ia import clean_ocr, text_to_markdown, _is_heading, slugify


def test_slugify() -> None:
    assert slugify("Audels Electricians Guide Vol. 1") == "audels_electricians_guide_vol_1"
    assert slugify("  Spaces & Symbols!  ") == "spaces_symbols"
    print("  slugify: OK")


def test_ligatures() -> None:
    cases = [
        ("ﬃefficiency", "ffiefficiency"),  # ffi ligature
        ("ﬁlament", "filament"),
        ("ﬂoor", "floor"),
    ]
    for raw, expected in cases:
        result = clean_ocr(raw)
        assert expected in result, f"Expected {expected!r} in {result!r}"
    print("  ligatures: OK")


def test_smart_quotes() -> None:
    # Right single quote U+2019 and left single quote U+2018
    raw = "‘quoted’"
    result = clean_ocr(raw)
    assert "‘" not in result and "’" not in result
    assert "'quoted'" in result
    # Left and right double quotes U+201C, U+201D
    raw2 = "“double”"
    result2 = clean_ocr(raw2)
    assert "“" not in result2 and "”" not in result2
    assert '"double"' in result2
    print("  smart quotes: OK")


def test_hyphen_join() -> None:
    result = clean_ocr("electro-\nmagnetic field")
    assert "electromagnetic" in result
    result2 = clean_ocr("mag-\nnetism in the core")
    assert "magnetism" in result2
    print("  hyphen-join: OK")


def test_page_numbers() -> None:
    raw = "Text.\n\n42\n\nMore text.\n\n1234\n\nEnd."
    result = clean_ocr(raw)
    for num in ["42", "1234"]:
        assert f"\n{num}\n" not in result, f"Bare page number {num} not removed"
    assert "Text." in result and "More text." in result
    print("  page numbers: OK")


def test_index_strip() -> None:
    body = "\n".join(f"Sentence {i} about electricity and circuits." for i in range(200))
    index = "\nINDEX\n\nAlternating current, 12, 45\nDirect current, 8, 22\n"
    result = clean_ocr(body + index)
    assert "Alternating current, 12" not in result, "Index was not stripped"
    assert "Sentence 0" in result, "Body text was incorrectly removed"
    assert "Sentence 199" in result, "Body text was incorrectly removed"
    print("  index strip: OK")


def test_running_headers() -> None:
    header = "AUDELS ELECTRICIANS GUIDE"
    body = "\n".join(
        header + "\n" + f"Unique text about topic {i} in electrical engineering."
        for i in range(50)
    )
    result = clean_ocr(body)
    occurrences = sum(1 for ln in result.split("\n") if ln.strip() == header)
    assert occurrences == 0, f"Running header appeared {occurrences} times after cleaning"
    print("  running headers: OK")


def test_heading_detection() -> None:
    expected_headings = [
        ("CHAPTER I", 2),
        ("CHAPTER XIV", 2),
        ("CHAPTER 3. Alternating Current", 2),
        ("PART ONE", 2),
        ("PART II - WIRING METHODS", 2),
        ("SECTION 4", 2),
        ("DIVISION III", 2),
        ("DIRECT CURRENTS", 3),
        ("OHM'S LAW AND ITS APPLICATIONS", 3),
        ("MAGNETISM AND ELECTRICITY", 3),
        ("Ques. What is an electric current?", 4),
        ("Ques. How does a transformer work in practice?", 4),
    ]
    for line, expected_level in expected_headings:
        result = _is_heading(line)
        assert result is not None, f"Expected heading, got None: {line!r}"
        assert result[0] == expected_level, (
            f"{line!r}: expected h{expected_level}, got h{result[0]}"
        )

    not_headings = [
        "The current flows through the wire.",
        "Ans. The voltage is the potential difference.",
        "a",
        "42",
        "This is a long sentence that should not be treated as a heading.",
        "it starts lowercase",
    ]
    for line in not_headings:
        result = _is_heading(line)
        assert result is None, f"False positive heading: {line!r} -> {result}"

    print("  heading detection: OK")


def test_markdown_conversion() -> None:
    sample = textwrap.dedent("""
        CONTENTS
        Chapter I - Direct Currents....... 1
        Chapter II - Alternating Currents.. 45

        CHAPTER I

        DIRECT CURRENTS

        Ques. What is an electric current?

        Ans. An electric current is a flow of electrons through a conductor.
        The direction of flow determines the polarity.

        Ques. What are the units used to measure electricity?

        Ans. The ampere is the unit of current, the volt is the unit of
        electromotive force, and the ohm is the unit of resistance.

        CHAPTER II

        ALTERNATING CURRENTS

        Ques. How does alternating current differ from direct current?

        Ans. Alternating current periodically reverses direction, while
        direct current flows continuously in one direction.
    """).strip()

    meta = {
        "title": "Audels Electricians and Plumbers Guide",
        "author": "Edwin P. Anderson",
        "publisher": "Theo. Audel and Co.",
        "date": "1928",
        "series": "Audels Electricians and Plumbers Guide",
        "volume": "1",
    }
    md = text_to_markdown(sample, meta)

    checks = {
        "title h1":             "# Audels Electricians and Plumbers Guide",
        "CHAPTER I h2":         "## CHAPTER I",
        "CHAPTER II h2":        "## CHAPTER II",
        "DIRECT CURRENTS h3":   "### DIRECT CURRENTS",
        "ALTERNATING h3":       "### ALTERNATING CURRENTS",
        "first Ques h4":        "#### Ques. What is an electric current?",
        "second Ques h4":       "#### Ques. What are the units",
        "answer body text":     "Ans. An electric current is a flow",
        "publisher front matter": "*Theo. Audel and Co., 1928*",
        "series front matter":  "*Audels Electricians and Plumbers Guide, Vol. 1*",
    }
    failures = []
    for label, expected in checks.items():
        if expected not in md:
            failures.append(f"MISSING {label!r}: {expected!r}")

    toc_entries = [
        "Chapter I - Direct Currents....... 1",
        "Chapter II - Alternating Currents.. 45",
    ]
    for entry in toc_entries:
        if entry in md:
            failures.append(f"TOC entry not stripped: {entry!r}")

    if failures:
        print("\nGenerated Markdown:\n" + md)
        for f in failures:
            print("  FAIL:", f)
        sys.exit(1)

    print("  markdown conversion: OK")
    print("\n--- Generated Markdown (first 800 chars) ---")
    print(md[:800])
    print("...")


def main() -> None:
    print("Running download_ia.py unit tests...\n")
    test_slugify()
    test_ligatures()
    test_smart_quotes()
    test_hyphen_join()
    test_page_numbers()
    test_index_strip()
    test_running_headers()
    test_heading_detection()
    test_markdown_conversion()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
