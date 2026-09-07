"""Unit tests for the ``gutenkg bundle`` CLI -- validate, resolve, build,
export, image, make.

The first tests this CLI module has had. Scoped the same way
test_build_corpus.py and test_export_swift.py are: real spec files against a
synthetic corpus tree, with the heavy internals (run_build_corpus,
export_swift, subprocess.run) monkeypatched out so these run in milliseconds
and never touch doc_kg, a real embedder, or an actual container runtime. The
underlying functions already have their own real, end-to-end-verified test
coverage and manual verification; what these guard is the CLI's own wiring —
which branch runs for which materialize mode, which guard fires when, what
gets passed to the layer underneath.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from gutenberg_kg.cli import cmd_bundle
from gutenberg_kg.export_swift import ExportOptions, ExportReport


def _write_spec(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _make_book(corpus_root: Path, genre: str, title: str, *, ebook_id: int | None = None) -> None:
    book_dir = corpus_root / genre / title
    book_dir.mkdir(parents=True)
    lines = [f"# Reference: {title}", "", "## Source", ""]
    if ebook_id is not None:
        lines.append(f"- **Project Gutenberg ID**: {ebook_id}")
    (book_dir / "reference.md").write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    _make_book(root, "philosophy", "The Republic", ebook_id=1497)
    return root


@pytest.fixture(autouse=True)
def _patch_corpus_root(corpus: Path, monkeypatch):
    """Every resolver this CLI calls reads the real CORPUS_ROOT by default;
    point all of them at the fixture tree so no test depends on the real
    corpus's contents."""
    monkeypatch.setattr("gutenberg_kg.bundle_spec.CORPUS_ROOT_PATH", corpus)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


NONE_SPEC = """
name = "austen-mini"
version = "0.1.0"
books = ["philosophy/The Republic"]
diaries = false
materialize = "none"
source_bundle = "bundles/gutenberg-all"
golden_queries = ["a", "b", "c"]
"""

REBUILD_SPEC = """
name = "philosophy-mini"
version = "0.1.0"
books = ["philosophy/The Republic"]
diaries = false
golden_queries = ["a", "b", "c"]
"""

INVALID_SPEC = """
name = "bad"
version = "0.1.0"
books = ["totally-nonexistent-book"]
golden_queries = ["a"]
"""


class TestBundleValidate:
    def test_valid_spec_reports_ok(self, tmp_path, runner):
        spec_path = _write_spec(tmp_path, "ok", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_validate, [str(spec_path)])
        assert result.exit_code == 0
        assert "ok" in result.output

    def test_invalid_spec_lists_every_problem_and_exits_nonzero(self, tmp_path, runner):
        spec_path = _write_spec(tmp_path, "bad", INVALID_SPEC)
        result = runner.invoke(cmd_bundle.bundle_validate, [str(spec_path)])
        assert result.exit_code != 0
        assert "golden_queries" in result.output
        assert "nonexistent-book" in result.output


class TestBundleResolve:
    def test_print_bundle_name_needs_no_resolution(self, tmp_path, runner):
        """A selector that would fail to resolve must not block --print-bundle-name
        -- a Makefile recipe asking for the name alone should not pay for, or
        fail on, a full corpus resolve."""
        spec_path = _write_spec(tmp_path, "bad", INVALID_SPEC)
        result = runner.invoke(cmd_bundle.bundle_resolve, [str(spec_path), "--print-bundle-name"])
        assert result.exit_code == 0
        assert result.output.strip() == "bad"

    def test_print_image_tag(self, tmp_path, runner):
        spec_path = _write_spec(tmp_path, "ok", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_resolve, [str(spec_path), "--print-image-tag"])
        assert result.exit_code == 0
        assert result.output.strip() == "philosophy-mini-0.1.0"

    def test_default_report_lists_books_and_genres(self, tmp_path, runner):
        spec_path = _write_spec(tmp_path, "ok", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_resolve, [str(spec_path)])
        assert result.exit_code == 0
        assert "philosophy/The Republic" in result.output


class TestExportOptionsForSpec:
    """The pure branch that decides how export reads a spec -- tested
    directly, without going through the CLI at all."""

    def test_materialize_none_reads_source_bundle(self, tmp_path):
        from gutenberg_kg.bundle_spec import load_spec, resolve_selection

        spec_path = _write_spec(tmp_path, "none", NONE_SPEC)
        spec = load_spec(spec_path)
        resolved = resolve_selection(spec)
        options = cmd_bundle._export_options_for_spec(
            spec, resolved, out=None, verify=False, force=False
        )
        assert options.bundle == Path("bundles/gutenberg-all")
        assert options.catalog_keys == resolved.catalog_keys
        assert options.out == Path("bundles/austen-mini/swift")

    def test_materialize_rebuild_reads_the_named_bundle_dir(self, tmp_path, monkeypatch):
        from gutenberg_kg.bundle_spec import load_spec, resolve_selection

        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        spec = load_spec(spec_path)
        resolved = resolve_selection(spec)
        bundle_dir = tmp_path / "bundles" / "philosophy-mini"
        (bundle_dir / ".dockg").mkdir(parents=True)
        monkeypatch.setattr(cmd_bundle, "_bundle_dir", lambda _spec: bundle_dir)

        options = cmd_bundle._export_options_for_spec(
            spec, resolved, out=None, verify=False, force=False
        )
        assert options.bundle == bundle_dir
        assert options.out == bundle_dir / "swift"
        # Passed through even though it does no filtering work here (every
        # book in an already-rebuilt bundle matches) -- the manifest's
        # "product" block is gated on this being set.
        assert options.catalog_keys == resolved.catalog_keys

    def test_materialize_rebuild_without_a_built_bundle_refuses(self, tmp_path, monkeypatch):
        import click

        from gutenberg_kg.bundle_spec import load_spec, resolve_selection

        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        spec = load_spec(spec_path)
        resolved = resolve_selection(spec)
        monkeypatch.setattr(cmd_bundle, "_bundle_dir", lambda _spec: tmp_path / "never-built")

        with pytest.raises(click.ClickException, match="does not exist"):
            cmd_bundle._export_options_for_spec(spec, resolved, out=None, verify=False, force=False)


class TestBundleBuild:
    def test_materialize_none_is_a_no_op(self, tmp_path, runner, monkeypatch):
        called = []
        monkeypatch.setattr(
            cmd_bundle, "run_build_corpus", lambda *a, **k: called.append((a, k)) or 0
        )
        spec_path = _write_spec(tmp_path, "none", NONE_SPEC)
        result = runner.invoke(cmd_bundle.bundle_build, [str(spec_path)])
        assert result.exit_code == 0
        assert "nothing to build" in result.output
        assert called == []

    def test_rebuild_calls_run_build_corpus_with_the_resolved_selection(
        self, tmp_path, runner, monkeypatch
    ):
        captured = {}

        def fake_run_build_corpus(genres, opts):
            captured["genres"] = genres
            captured["opts"] = opts
            return 0

        monkeypatch.setattr(cmd_bundle, "run_build_corpus", fake_run_build_corpus)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_build, [str(spec_path)])
        assert result.exit_code == 0
        assert captured["genres"] == ["philosophy"]
        assert captured["opts"].catalog_keys == frozenset({"philosophy/The Republic"})
        assert captured["opts"].product_name == "philosophy-mini"
        assert captured["opts"].product_version == "0.1.0"

    def test_existing_bundle_refuses_without_force(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        graph = tmp_path / "bundles" / "philosophy-mini" / ".dockg" / "graph.sqlite"
        graph.parent.mkdir(parents=True)
        graph.write_bytes(b"already built")
        called = []
        monkeypatch.setattr(cmd_bundle, "run_build_corpus", lambda *a, **k: called.append(1) or 0)

        result = runner.invoke(cmd_bundle.bundle_build, [str(spec_path)])
        assert result.exit_code != 0
        assert "--force" in str(result.output) + str(result.exception)
        assert called == []

    def test_existing_bundle_with_force_proceeds(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        graph = tmp_path / "bundles" / "philosophy-mini" / ".dockg" / "graph.sqlite"
        graph.parent.mkdir(parents=True)
        graph.write_bytes(b"already built")
        monkeypatch.setattr(cmd_bundle, "run_build_corpus", lambda *a, **k: 0)

        result = runner.invoke(cmd_bundle.bundle_build, [str(spec_path), "--force"])
        assert result.exit_code == 0


class TestBundleImage:
    def test_materialize_none_refuses(self, tmp_path, runner):
        spec_path = _write_spec(tmp_path, "none", NONE_SPEC)
        result = runner.invoke(cmd_bundle.bundle_image, [str(spec_path)])
        assert result.exit_code != 0
        assert "Swift-only" in str(result.output) + str(result.exception)

    def test_no_built_bundle_refuses(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_image, [str(spec_path)])
        assert result.exit_code != 0
        assert "bundle build" in str(result.output) + str(result.exception)

    def test_no_runtime_available_refuses(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        dockg = tmp_path / "bundles" / "philosophy-mini" / ".dockg"
        dockg.mkdir(parents=True)
        monkeypatch.setattr(cmd_bundle, "_detect_runtime", lambda: None)

        result = runner.invoke(cmd_bundle.bundle_image, [str(spec_path)])
        assert result.exit_code != 0
        assert "CLI is available" in result.output

    def test_builds_the_correct_tag_and_build_arg(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        dockg = tmp_path / "bundles" / "philosophy-mini" / ".dockg"
        dockg.mkdir(parents=True)
        monkeypatch.setattr(cmd_bundle, "_detect_runtime", lambda: "docker")

        captured = {}

        class FakeResult:
            returncode = 0

        def fake_run(command, check=False):  # noqa: ARG001
            captured["command"] = command
            return FakeResult()

        monkeypatch.setattr(cmd_bundle.subprocess, "run", fake_run)

        result = runner.invoke(cmd_bundle.bundle_image, [str(spec_path)])
        assert result.exit_code == 0
        assert captured["command"][0] == "docker"
        assert "--build-arg" in captured["command"]
        assert "BUNDLE=philosophy-mini" in captured["command"]
        assert "corpus-gutenberg:philosophy-mini-0.1.0" in captured["command"]

    def test_a_failed_build_propagates_the_exit_code(self, tmp_path, runner, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        dockg = tmp_path / "bundles" / "philosophy-mini" / ".dockg"
        dockg.mkdir(parents=True)
        monkeypatch.setattr(cmd_bundle, "_detect_runtime", lambda: "docker")

        class FailedResult:
            returncode = 7

        monkeypatch.setattr(cmd_bundle.subprocess, "run", lambda *a, **k: FailedResult())

        result = runner.invoke(cmd_bundle.bundle_image, [str(spec_path)])
        assert result.exit_code == 7


class TestBundleMake:
    def test_image_with_materialize_none_refuses_before_doing_anything(
        self, tmp_path, runner, monkeypatch
    ):
        spec_path = _write_spec(tmp_path, "none", NONE_SPEC)
        called = []
        monkeypatch.setattr(
            cmd_bundle,
            "export_swift",
            lambda *a, **k: called.append(1) or ExportReport(out=Path("x")),
        )
        result = runner.invoke(cmd_bundle.bundle_make, [str(spec_path), "--image"])
        assert result.exit_code != 0
        assert called == []

    def test_materialize_none_skips_build_then_exports(self, tmp_path, runner, monkeypatch):
        exported = {}

        def fake_export_swift(options: ExportOptions, progress=None):  # noqa: ARG001
            exported["options"] = options
            return ExportReport(out=options.resolved_out())

        monkeypatch.setattr(cmd_bundle, "export_swift", fake_export_swift)
        build_called = []
        monkeypatch.setattr(
            cmd_bundle, "run_build_corpus", lambda *a, **k: build_called.append(1) or 0
        )

        spec_path = _write_spec(tmp_path, "none", NONE_SPEC)
        result = runner.invoke(cmd_bundle.bundle_make, [str(spec_path)])
        assert result.exit_code == 0
        assert build_called == []
        assert "options" in exported

    def test_rebuild_builds_then_exports(self, tmp_path, runner, monkeypatch):
        build_called = []
        monkeypatch.setattr(
            cmd_bundle, "run_build_corpus", lambda *a, **k: build_called.append(1) or 0
        )
        exported = {}

        def fake_export_swift(options: ExportOptions, progress=None):  # noqa: ARG001
            exported["options"] = options
            return ExportReport(out=options.resolved_out())

        monkeypatch.setattr(cmd_bundle, "export_swift", fake_export_swift)
        # export step reads bundles/<name>/.dockg -- present it as already
        # built by the (faked) build step, matching what a real one produces.
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bundles" / "philosophy-mini" / ".dockg").mkdir(parents=True)

        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_make, [str(spec_path)])
        assert result.exit_code == 0
        assert build_called == [1]
        assert "options" in exported

    def test_existing_bundle_skips_build_without_force(self, tmp_path, runner, monkeypatch):
        build_called = []
        monkeypatch.setattr(
            cmd_bundle, "run_build_corpus", lambda *a, **k: build_called.append(1) or 0
        )
        monkeypatch.setattr(
            cmd_bundle,
            "export_swift",
            lambda options, progress=None: ExportReport(out=options.resolved_out()),
        )
        monkeypatch.chdir(tmp_path)
        graph = tmp_path / "bundles" / "philosophy-mini" / ".dockg" / "graph.sqlite"
        graph.parent.mkdir(parents=True)
        graph.write_bytes(b"already built")

        spec_path = _write_spec(tmp_path, "reb", REBUILD_SPEC)
        result = runner.invoke(cmd_bundle.bundle_make, [str(spec_path)])
        assert result.exit_code == 0
        assert build_called == []
        assert "already exists" in result.output
