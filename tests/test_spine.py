"""Unit tests for gutenberg_kg.spine — the structural profiler (Step 1 of
analysis/STRUCTURAL_PARSER_PLAN.md)."""

from __future__ import annotations

from gutenberg_kg.spine import (
    Hit,
    classify,
    find_candidates,
    numeral_value,
    profile,
    split_runs,
)

# ---------------------------------------------------------------------------
# numeral_value
# ---------------------------------------------------------------------------


def test_numeral_value_digits():
    assert numeral_value("135") == 135


def test_numeral_value_roman():
    assert numeral_value("XIV") == 14


def test_numeral_value_word():
    assert numeral_value("Fourteen") == 14


def test_numeral_value_word_compound():
    assert numeral_value("Twenty-Three") == 23


def test_numeral_value_not_a_numeral():
    assert numeral_value("Castaway") is None


def test_numeral_value_empty():
    assert numeral_value("") is None


# ---------------------------------------------------------------------------
# find_candidates
# ---------------------------------------------------------------------------


def test_find_candidates_keyword_and_numeral():
    hits = find_candidates(["CHAPTER 1. Loomings.", "some text", "CHAPTER 2. The Carpet-Bag."])
    assert [h.number for h in hits["CHAPTER"]] == [1, 2]
    assert [h.line for h in hits["CHAPTER"]] == [0, 2]


def test_find_candidates_bare_roman():
    hits = find_candidates(["I.", "some text", "II."])
    assert [h.number for h in hits["ROMAN"]] == [1, 2]


def test_find_candidates_ignores_a_long_line():
    long_line = "CHAPTER 1. " + "x" * 90
    assert find_candidates([long_line]) == {}


def test_find_candidates_ignores_non_matching_prose():
    hits = find_candidates(["Chapter one was the longest of them all."])
    assert hits == {}


# ---------------------------------------------------------------------------
# split_runs
# ---------------------------------------------------------------------------


def test_split_runs_single_ascending_run():
    hits = [Hit(0, 1), Hit(1, 2), Hit(2, 3)]
    runs = split_runs("CHAPTER", hits)
    assert len(runs) == 1
    assert [h.number for h in runs[0].hits] == [1, 2, 3]


def test_split_runs_breaks_on_a_decrease():
    """A contents list (1..3) followed by the body restarting at 1 is two runs."""
    hits = [Hit(0, 1), Hit(1, 2), Hit(2, 3), Hit(10, 1), Hit(20, 2)]
    runs = split_runs("CHAPTER", hits)
    assert len(runs) == 2
    assert [h.number for h in runs[0].hits] == [1, 2, 3]
    assert [h.number for h in runs[1].hits] == [1, 2]


def test_split_runs_empty():
    assert split_runs("CHAPTER", []) == []


# ---------------------------------------------------------------------------
# profile / classify — shaped after the real corpus measurements in
# analysis/STRUCTURAL_PARSER_PLAN.md
# ---------------------------------------------------------------------------


def _moby_dick_shaped_lines():
    """A contents list (dense) followed by the body (sparse) for the same
    CHAPTER 1..135 sequence -- the exact shape measured in Moby Dick."""
    lines = ["CONTENTS", ""]
    for n in range(1, 136):
        lines.append(f"CHAPTER {n}. Some Title.")
    lines += [""] * 4
    for n in range(1, 136):
        lines.append(f"CHAPTER {n}. Some Title.")
        lines += ["Body prose for this chapter, several lines of it."] * 30
    return lines


def test_profile_finds_both_the_contents_run_and_the_body_run():
    result = profile(_moby_dick_shaped_lines())
    assert "CHAPTER" in result
    runs = result["CHAPTER"]
    assert len(runs) == 2
    densities = sorted(r.density for r in runs)
    # Contents is dense (near 1.0, one heading per line); the body is
    # diluted by ~30 prose lines per chapter. Order-of-magnitude apart,
    # matching what was measured on the real corpus.
    assert densities[0] < densities[1] / 8


def test_classify_labels_the_dense_run_as_contents():
    runs = profile(_moby_dick_shaped_lines())["CHAPTER"]
    result = classify(runs)
    assert result is not None
    assert result.contents is not None
    assert result.spine is not None
    assert result.contents.density > result.spine.density
    assert result.contents.first_number == 1
    assert result.spine.first_number == 1


def test_classify_finds_no_contents_list_when_there_is_only_one_run():
    """A book with no separate contents list -- just chapters in the body."""
    lines = []
    for n in range(1, 20):
        lines.append(f"CHAPTER {n}.")
        lines += ["Body prose."] * 20
    runs = profile(lines)["CHAPTER"]
    result = classify(runs)
    assert result is not None
    assert result.contents is None
    assert result.spine is not None
    assert result.spine.first_number == 1


def test_classify_does_not_pair_runs_covering_different_number_ranges():
    """Two unrelated dense/sparse runs for the same keyword, e.g. a Bible's
    numbered chapters restarting in each of several books, must not be read
    as one contents/spine pair when their ranges don't overlap."""
    lines = []
    for n in range(1, 8):
        lines.append(f"CHAPTER {n}.")
    lines += [""] * 5
    for n in range(50, 57):
        lines.append(f"CHAPTER {n}.")
        lines += ["prose"] * 30
    runs = profile(lines)["CHAPTER"]
    result = classify(runs)
    assert result is not None
    assert result.contents is None


def test_a_lone_false_heading_never_forms_a_qualifying_run():
    """'Volume containing several works' -- VOLUME + a stray roman 'C' --
    is a single hit, well under MIN_RUN_LENGTH, so it profiles as nothing."""
    lines = ["Volume containing several works; and among them _Marchi_ (Pauli)"]
    assert profile(lines) == {}


def test_hobbes_style_marginal_notes_do_not_form_a_sequence():
    """552 ALL-CAPS marginal notes with no numbering at all -- none of them
    match a keyword+numeral template, so nothing here is even a candidate."""
    lines = ["Of The Right Of Succession", "Of The Books Of Holy Scripture"] * 30
    assert profile(lines) == {}
