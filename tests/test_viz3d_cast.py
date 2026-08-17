"""Tests for the save-then-cast seam in the 3-D viewer.

Only the seam, not the window: constructing ``ForestMainWindow`` builds a
``QtInteractor``, which aborts the interpreter without a GL context rather
than raising (see ``tests/_render.py``). Importing the module is safe, so the
seam is testable and the Qt plumbing is not.

The seam moved down a layer.  ``save_and_cast_quilt`` is ``quiltwright``'s as
of 0.6.0 and the render lifecycle is ``kg_utils.viz3d.qt``'s, so what is left
to pin here is that this package really does use them — a re-introduced local
copy would drift the same way it drifted from ``pycode_kg`` — plus the one
behaviour the viewer's error handling is written against.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("pyvistaqt", reason="viz3d extra not installed — needs `viz3d`")
pytest.importorskip("quiltwright", reason="quiltwright not installed — needs the `pov` extra")

from gutenberg_kg import viz3d  # noqa: E402

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


class TestTheMachineryIsNotOursAnyMore:
    """Guards against a local copy creeping back in."""

    def test_no_local_save_and_cast_helper(self):
        assert not hasattr(viz3d, "save_and_cast_quilt")

    def test_no_local_render_worker(self):
        assert not hasattr(viz3d, "PovRenderWorker")

    @pytest.mark.parametrize(
        "name", ["PovRenderSession", "ImagePopup", "cast_scene_to_looking_glass"]
    )
    def test_the_sdk_supplies_it(self, name):
        assert getattr(viz3d, name).__module__ == "kg_utils.viz3d.qt"

    @pytest.mark.parametrize(
        "gone",
        [
            "_start_pov_render",
            "_poll_pov_progress",
            "_finish_pov_render",
            "_on_pov_failed",
            "_on_pov_done",
        ],
    )
    def test_the_window_no_longer_runs_the_lifecycle(self, gone):
        assert not hasattr(viz3d.ForestMainWindow, gone)

    def test_the_window_shuts_the_session_down_on_cleanup(self):
        """The crash-on-close fix: a live QThread must not outlive the window."""
        import inspect

        assert "_pov_session.shutdown()" in inspect.getsource(viz3d.ForestMainWindow.cleanup)


class TestTheContractTheViewerReliesOn:
    """`_save_pov_result` and `cast_to_looking_glass` branch on this shape."""

    def test_returns_a_path_and_an_error_slot(self, tmp_path, spec, image):
        from quiltwright import save_and_cast_quilt

        with patch("quiltwright.lfd.cast_quilt"):
            out, error = save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert isinstance(out, Path) and error is None

    def test_a_failed_cast_is_returned_not_raised(self, tmp_path, spec, image):
        # No panel connected is the normal case, not an error worth losing a
        # render over — the viewer reports it and keeps the file.
        from quiltwright import save_and_cast_quilt

        with patch("quiltwright.lfd.cast_quilt", side_effect=RuntimeError("no bridge")):
            out, error = save_and_cast_quilt(image, tmp_path / "q", spec, cast=True)
        assert out.exists()
        assert error is not None and "no bridge" in error


class TestCastScaling:
    """`CAST_SCALE` is applied through the spec, not by hand."""

    def test_the_scaled_spec_keeps_whole_tiles(self):
        from quiltwright import QUILT_PRESETS

        scaled = QUILT_PRESETS[viz3d.QUILT_SPEC].scaled(viz3d.CAST_SCALE)
        assert scaled.quilt_width % scaled.columns == 0
        assert scaled.quilt_height % scaled.rows == 0

    def test_the_view_grid_is_unchanged(self):
        from quiltwright import QUILT_PRESETS

        preset = QUILT_PRESETS[viz3d.QUILT_SPEC]
        assert preset.scaled(viz3d.CAST_SCALE).n_views == preset.n_views
