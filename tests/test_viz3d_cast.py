"""Tests for the save-then-cast seam in the 3-D viewer.

Only the seam, not the window: constructing ``ForestMainWindow`` builds a
``QtInteractor``, which aborts the interpreter without a GL context rather
than raising (see ``tests/_render.py``). Importing the module is safe, so the
module-level helper is testable and the Qt plumbing is not.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("pyvistaqt", reason="viz3d extra not installed — needs `viz3d`")
pytest.importorskip("quiltwright", reason="quiltwright not installed — needs the `pov` extra")

from gutenberg_kg.viz3d import save_and_cast_quilt  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def spec():
    from quiltwright import QuiltSpec

    return QuiltSpec(
        columns=2, rows=1, quilt_width=64, quilt_height=24, aspect=1.33, view_cone=40.0
    )


@pytest.fixture
def image():
    return np.zeros((24, 64, 3), dtype=np.uint8)


class TestSaveAndCast:
    def test_cast_receives_a_path_not_the_array(self, tmp_path, spec, image):
        # The actual bug: cast_quilt takes a path on the Bridge host's
        # filesystem, save_quilt takes the array. Passing the array raised
        # "argument should be a str or an os.PathLike object ... not
        # 'ndarray'" — but only once a cast was attempted, which is minutes of
        # ray-tracing after the mistake was made.
        with patch("quiltwright.cast_quilt") as cast:
            out, error = save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert error is None
        (sent,) = cast.call_args.args[:1]
        assert isinstance(sent, Path), f"cast_quilt got {type(sent).__name__}"
        assert not isinstance(sent, np.ndarray)

    def test_the_path_sent_is_absolute(self, tmp_path, spec, image):
        # Bridge resolves it on its own filesystem, so a relative path is a
        # different file or no file at all.
        with patch("quiltwright.cast_quilt") as cast:
            save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert cast.call_args.args[0].is_absolute()

    def test_the_file_exists_before_bridge_is_contacted(self, tmp_path, spec, image):
        seen: dict[str, bool] = {}

        def _record(path, _spec):
            seen["existed"] = Path(path).exists()

        with patch("quiltwright.cast_quilt", side_effect=_record):
            save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert seen["existed"], "cast was attempted before the quilt was written"

    def test_a_failed_cast_still_keeps_the_quilt(self, tmp_path, spec, image):
        # No panel connected is the normal case, not an error worth losing a
        # render over.
        with patch("quiltwright.cast_quilt", side_effect=RuntimeError("no bridge")):
            out, error = save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert out.exists()
        assert error is not None and "no bridge" in error

    def test_no_cast_writes_the_file_and_contacts_nothing(self, tmp_path, spec, image):
        with patch("quiltwright.cast_quilt") as cast:
            out, error = save_and_cast_quilt(image, tmp_path / "q", spec, cast=False)
        assert out.exists() and error is None
        cast.assert_not_called()
