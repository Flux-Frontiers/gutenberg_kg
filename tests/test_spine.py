"""Unit tests for gutenberg_kg.spine — the structural profiler (Step 1 of
analysis/STRUCTURAL_PARSER_PLAN.md)."""

from __future__ import annotations

from gutenberg_kg.spine import (
    Hit,
    cluster_hits,
    contents_regions,
    find_candidates,
    numeral_value,
    profile,
    spine_hits,
)

# A body-prose line has to clear the 60-character bar the prose detector
# uses; a short placeholder would silently read as listing.
PROSE = "A line of real narrative prose, long enough to be read as a sentence of the story itself."

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


def test_find_candidates_bare_roman_with_subtitle():
    """Longfellow's Purgatorio and Paradiso list their contents as
    "I. The Shores of Purgatory...", not "Canto I." like Inferno's -- the
    same document uses two shapes for the same thing."""
    hits = find_candidates(["I. The Shores of Purgatory. The Four Stars."])
    assert [h.number for h in hits["ROMAN"]] == [1]


def test_find_candidates_ignores_a_long_line():
    long_line = "CHAPTER 1. " + "x" * 90
    assert find_candidates([long_line]) == {}


def test_find_candidates_ignores_non_matching_prose():
    hits = find_candidates(["Chapter one was the longest of them all."])
    assert hits == {}


def test_find_candidates_ignores_a_lone_false_positive():
    """ "Volume containing several works" -- VOLUME + a stray roman-looking
    word -- was the exact bug (?![A-Za-z]) fixed in gutenberg_kg.headings;
    the whole-token numeral parser here never had it, since it validates
    the complete word rather than a greedy character-class prefix."""
    hits = find_candidates(["Volume containing several works; and among them"])
    assert hits == {}


# ---------------------------------------------------------------------------
# cluster_hits — gap-and-prose clustering
# ---------------------------------------------------------------------------


def _spaced_hits(numbers_and_lines):
    return [Hit(line, n) for n, line in numbers_and_lines]


def test_cluster_hits_groups_close_hits_together():
    lines = [""] * 20
    hits = _spaced_hits([(1, 0), (2, 2), (3, 4)])
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert len(clusters) == 1
    assert len(clusters[0].hits) == 3


def test_cluster_hits_splits_hits_far_apart():
    lines = [""] * 200
    hits = _spaced_hits([(1, 0), (2, 150)])
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert len(clusters) == 2


def test_cluster_hits_ignores_number_order():
    """A contents list (1, 2, 3) immediately followed by the body
    restarting at 1 must still be one cluster if the lines are close --
    clustering by line position, not by monotonic sequence, is what makes a
    multi-volume book's restarting numbering collapse into one contents
    region instead of shattering into one fragment per volume."""
    lines = [""] * 10
    hits = _spaced_hits([(1, 0), (2, 2), (3, 4), (1, 6), (2, 8)])
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert len(clusters) == 1
    assert len(clusters[0].hits) == 5


def test_cluster_hits_tolerates_a_wrapped_listing_entry():
    """Innocents Abroad's contents entries run onto a second line that ends
    in a closing quote -- one prose-shaped line between consecutive hits,
    measured across every gap in that listing. That is a wrapped entry, not
    a chapter, and must not break the cluster."""
    lines = [
        "CHAPTER I.",
        "Popular Talk of the Excursion--Programme of the Trip--Duly Ticketed",
        "--The Mystery of “Ship Time”--The Denizens of the Deep--“Land Hoh.”",
        "",
        "CHAPTER II.",
        "Grand Preparations--An Imposing Dignitary--The European Exodus.",
        "",
        "CHAPTER III.",
    ]
    hits = find_candidates(lines)["CHAPTER"]
    assert len(cluster_hits(lines, hits, "CHAPTER")) == 1


def test_cluster_hits_a_chapter_of_prose_between_hits_breaks():
    """Two hits close enough in line count to cluster, but with a
    chapter's worth of narrative between them, are two clusters -- the
    difference between a listing and genuinely short body chapters."""
    lines = ["CHAPTER 1", "", PROSE, PROSE, PROSE, "", "CHAPTER 2"]
    hits = find_candidates(lines)["CHAPTER"]
    assert len(cluster_hits(lines, hits, "CHAPTER")) == 2


def test_cluster_hits_splits_off_the_bodys_first_heading():
    """Emma's contents end with Volume III's last chapter; two blank lines
    later is the body's own CHAPTER I, and two lines after that the novel
    begins. Nothing between the two headings tells them apart. What comes
    after the second one does, and that hit must not be deleted as
    contents."""
    lines = []
    for n in range(1, 8):
        lines.append(f"CHAPTER {n}")
    lines += ["", "", "CHAPTER 1", "", ""] + [PROSE] * 6
    hits = find_candidates(lines)["CHAPTER"]
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert len(clusters) == 2
    assert len(clusters[0].hits) == 7
    assert clusters[1].hits[0].line == 9  # the body's CHAPTER 1, on its own


def test_cluster_hits_recognises_wrapped_prose_that_ends_mid_sentence():
    """Real prose wraps mid-sentence: only a paragraph's last line carries
    a full stop, and it is often short. A detector that wanted terminal
    punctuation saw no prose at all in Emma's opening and deleted the
    body's CHAPTER I as the contents' last entry. These are Emma's actual
    first four lines; the heading above them must be split off."""
    lines = [
        "CHAPTER XVIII",
        "CHAPTER XIX",
        "",
        "",
        "CHAPTER I",
        "",
        "",
        "Emma Woodhouse, handsome, clever, and rich, with a comfortable home and",
        "happy disposition, seemed to unite some of the best blessings of",
        "existence; and had lived nearly twenty-one years in the world with very",
        "little to distress or vex her.",
    ]
    hits = find_candidates(lines)["CHAPTER"]
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert [len(c.hits) for c in clusters] == [2, 1]
    assert clusters[1].hits[0].line == 4


def test_cluster_hits_keeps_the_listings_last_entry_before_a_preface():
    """Moby Dick's contents end at CHAPTER 135, and a transcriber's note
    begins a few lines later. Prose after a trailing hit is not enough to
    call it a body heading -- this one continues the sequence (134, 135)
    rather than restarting it, so it stays in the listing."""
    lines = [
        "CHAPTER 133. The Chase.—First Day.",
        "CHAPTER 134. The Chase.—Second Day.",
        "CHAPTER 135. The Chase.—Third Day.",
        "",
        "Original Transcriber's Notes:",
        "",
        "This text is a combination of etexts, one from the now-defunct ERIS",
        "project at Virginia Tech and one from Project Gutenberg's archives.",
        "The proofreaders of this version are indebted to the earlier work.",
    ]
    hits = find_candidates(lines)["CHAPTER"]
    clusters = cluster_hits(lines, hits, "CHAPTER")
    assert [len(c.hits) for c in clusters] == [3]


def test_cluster_hits_a_title_case_listing_entry_is_not_prose():
    """Twain's descriptive contents entries are half lowercase purely on
    their articles and prepositions. Judged on content words they are
    Title Case, and three of them in a row must not break the cluster."""
    lines = [
        "CHAPTER I.",
        "Popular Talk of the Excursion--Programme of the Trip--Duly Ticketed",
        "for the Excursion--Defection of the Celebrities--Grand Preparations",
        "--An Imposing Dignitary--The European Exodus--Mr. Blucher's Opinions",
        "",
        "CHAPTER II.",
    ]
    hits = find_candidates(lines)["CHAPTER"]
    assert len(cluster_hits(lines, hits, "CHAPTER")) == 1


def test_cluster_hits_empty():
    assert cluster_hits([], [], "CHAPTER") == []


# ---------------------------------------------------------------------------
# profile / contents_regions / spine_hits
# ---------------------------------------------------------------------------


def _moby_dick_shaped_lines():
    """A contents list (dense) followed by the body (sparse) for the same
    CHAPTER 1..135 sequence -- the exact shape measured in Moby Dick, with
    the body's first chapter sitting only a few blank lines after the
    listing's last entry, as in Emma."""
    lines = ["CONTENTS", ""]
    for n in range(1, 136):
        lines.append(f"CHAPTER {n}. Some Title.")
    lines += [""] * 4
    for n in range(1, 136):
        lines.append(f"CHAPTER {n}. Some Title.")
        lines += [PROSE] * 30
    return lines


def test_profile_finds_the_contents_cluster_and_scattered_spine_hits():
    result = profile(_moby_dick_shaped_lines())
    contents = [c for c in result["CHAPTER"] if c.is_contents_shaped]
    assert len(contents) == 1
    assert len(contents[0].hits) == 135


def test_profile_ignores_a_template_under_the_threshold():
    """A single hit -- or a few -- never even qualify for reporting; this
    is the same rejection that keeps a lone false positive like "Volume
    containing several works" out of the corpus-wide report entirely."""
    lines = ["CHAPTER 1", "", "prose", "", "CHAPTER 2"]
    assert profile(lines) == {}


def test_contents_regions_bounds_moby_dick_exactly():
    lines = _moby_dick_shaped_lines()
    assert contents_regions(lines) == [(2, 136)]


def test_contents_regions_merges_adjacent_templates():
    """Divine Comedy's Inferno contents ("Canto I..XXXIV") and Purgatorio's
    ("I..XXXIII", a bare roman with no "Canto") are different templates a
    few lines apart -- one contents listing split across two keywords."""
    lines = [""] * 200
    for n in range(1, 6):
        lines[n * 2] = f"Canto {n}. A Title."
    for n in range(1, 6):
        lines[15 + n * 2] = f"{n}. A Title."
    assert len(contents_regions(lines)) == 1


def test_spine_hits_excludes_the_contents_and_keeps_every_body_chapter():
    lines = _moby_dick_shaped_lines()
    spines = spine_hits(lines)
    assert len(spines["CHAPTER"]) == 135
    assert spines["CHAPTER"][0].line > 136  # past the contents region


def test_spine_hits_a_book_with_no_contents_list_at_all():
    """No separate listing exists -- every hit is a real body heading."""
    lines = []
    for n in range(1, 20):
        lines.append(f"CHAPTER {n}.")
        lines += [PROSE] * 20
    assert len(spine_hits(lines)["CHAPTER"]) == 19


def test_spine_hits_short_real_chapters_are_not_swept_up_as_contents():
    """The negative case this whole design exists to get right: chapters
    genuinely spaced close together, but each followed by real prose, must
    read as real headings, not as a fake contents listing to delete."""
    lines = []
    for n in range(1, 21):
        lines += [f"CHAPTER {n}", "", PROSE, PROSE, PROSE] + [""] * 10
    assert contents_regions(lines) == []
    assert len(spine_hits(lines)["CHAPTER"]) == 20


def test_spine_hits_a_book_with_no_numbered_structure_at_all():
    """Jekyll and Hyde's chapters are named, not numbered -- a different
    signal class (see headings._repeated_title_lines), entirely outside
    what this module looks for. It must report nothing, not guess."""
    lines = ["Contents", "", "STORY OF THE DOOR", "", "SEARCH FOR MR. HYDE", "", "prose"]
    assert profile(lines) == {}
    assert contents_regions(lines) == []
    assert spine_hits(lines) == {}
