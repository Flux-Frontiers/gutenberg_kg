"""
Species leaf outlines for the hero tree.

Each species grows a leaf of its own outline rather than one flattened
ellipsoid: a lobed oak leaf, a palmate plane leaf, a fir or pine needle spray,
and ovate leaves of different widths for the rest.  The outlines are the Knowledge
Press web forest's (``web/src/game/species.ts`` in knowledge_press), in true
proportions: a leaf runs from its stalk at ``y = -1`` to its tip at ``y = 1``,
``x`` across it.

Pure NumPy; :func:`leaf_prototype` turns an outline into the PyVista mesh a
glyph call stamps at every leaf.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyvista as pv

__author__ = "Eric G. Suchanek, PhD"

#: Where the blade meets the stalk; the stalk runs from here down to ``y = -1``.
STALK_TOP: float = -0.62
#: Half the stalk's width.
STALK_HALF_WIDTH: float = 0.04
#: The web draws leaves on instances scaled 1.12 wide by 1.78 long and shapes
#: its ovate leaf for that; this puts the ovate leaf back in true proportions.
_OVATE_TRUE = 1.12 / 1.78
#: Face area of the leaf every species replaces -- ``leaf_glyphs``' ellipsoid,
#: radius 1 flattened by ``LEAF_ASPECT`` (1, 0.55) -- in units of size squared.
#: A species leaf is scaled to cover the same area, so the canopy keeps its
#: density whatever the outline.
ELLIPSOID_LEAF_AREA: float = float(np.pi * 0.55)
#: Most a species leaf is enlarged to match that area, so a narrow leaf (the
#: willow's) grows at most twice as long rather than absurdly so.
MAX_LEAF_SCALE: float = 2.0


@dataclass(frozen=True)
class LeafShape:
    """
    A leaf outline.

    :param half: For an outlined leaf, the right half from just below the tip
        down to the stalk, as ``(x, y)`` pairs; mirrored for the left half.
        ``None`` for an ovate leaf.
    :param width: For an ovate leaf, its width relative to a chestnut leaf's.
    :param smooth: Round the outline through a Catmull-Rom spline; otherwise
        the corners stay sharp (needles, the plane leaf's points).
    """

    half: tuple[tuple[float, float], ...] | None = None
    width: float = 0.36
    smooth: bool = False


# English oak: rounded lobes, widest above the middle, small ears at the base.
_OAK_HALF = (
    (0.16, 0.97), (0.27, 0.86), (0.19, 0.74), (0.4, 0.64), (0.45, 0.5), (0.26, 0.42),
    (0.47, 0.31), (0.49, 0.16), (0.29, 0.1), (0.44, -0.02), (0.42, -0.17), (0.24, -0.22),
    (0.32, -0.36), (0.27, -0.5), (0.13, -0.55), (0.18, -0.68), (0.1, -0.8), (0.03, -0.86),
)  # fmt: skip

# London plane: three broad upper lobes, two smaller outward ones, a rounded base.
_PLANE_HALF = (
    (0.06, 0.84), (0.11, 0.66), (0.17, 0.46), (0.33, 0.58), (0.55, 0.72), (0.5, 0.52),
    (0.44, 0.34), (0.38, 0.24), (0.56, 0.2), (0.8, 0.12), (0.66, -0.02), (0.52, -0.16),
    (0.36, -0.26), (0.2, -0.3), (0.07, -0.26), (0.04, -0.32), (0.03, -0.75),
)  # fmt: skip


def _needle_spray(n: int, top: float, span: float, base: float, amp: float, rise: float) -> tuple:
    """Half a spray of blunt needles either side of a stem, longest mid-spray."""
    out: list[tuple[float, float]] = []
    for k in range(n):
        y = top - span * k / (n - 1)
        reach = base + amp * np.sin(np.pi * (k + 1) / (n + 1))
        out += [
            (0.05, y + 0.045 * rise),
            (reach, y + 0.12 * rise),
            (reach + 0.01, y + 0.08 * rise),
            (0.05, y - 0.04),
        ]
    out.append((0.04, -1.0))
    return tuple(out)


def _pine_tuft() -> tuple:
    """Half a pine tuft: fewer, longer needles than the fir, fanning toward the tip."""
    out: list[tuple[float, float]] = []
    n = 7
    for k in range(n):
        y = 0.68 - 1.2 * k / (n - 1)
        reach = 0.3 + 0.28 * np.sin(np.pi * (k + 1) / (n + 1))
        out += [(0.04, y + 0.03), (reach, y + 0.3), (reach + 0.015, y + 0.26), (0.04, y - 0.05)]
    out.append((0.035, -1.0))
    return tuple(out)


#: Species -> leaf outline; every key of :data:`kg_utils.viz3d.SPECIES`.
LEAF_SHAPES: dict[str, LeafShape] = {
    "oak": LeafShape(half=_OAK_HALF, smooth=True),
    "chestnut": LeafShape(width=0.36),
    "fir": LeafShape(half=_needle_spray(12, 0.86, 1.62, 0.12, 0.2, 1.0)),
    "plane": LeafShape(half=_PLANE_HALF),
    "blackthorn": LeafShape(width=0.7),
    "pine": LeafShape(half=_pine_tuft()),
    "birch": LeafShape(width=0.5),
    "willow": LeafShape(width=0.16),
    "poplar": LeafShape(width=0.62),
}


def _cubic(p0, p1, p2, p3, n: int) -> list[tuple[float, float]]:
    """``n + 1`` samples of a cubic Bezier through four ``(x, y)`` points."""
    pts = np.array([p0, p1, p2, p3], dtype=float)
    t = np.linspace(0.0, 1.0, n + 1)[:, None]
    u = 1.0 - t
    out = u**3 * pts[0] + 3 * u**2 * t * pts[1] + 3 * u * t**2 * pts[2] + t**3 * pts[3]
    return [tuple(p) for p in out]


def _catmull_rom(pts: list[tuple[float, float]], per: int) -> list[tuple[float, float]]:
    """Resample a polyline through a uniform Catmull-Rom spline, *per* samples a span."""
    a = np.asarray(pts, dtype=float)
    out: list[tuple[float, float]] = []
    for i in range(len(a) - 1):
        p0, p1, p2, p3 = a[max(0, i - 1)], a[i], a[i + 1], a[min(len(a) - 1, i + 2)]
        for s in range(per):
            t = s / per
            q = 0.5 * (
                2 * p1
                + (p2 - p0) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                + (3 * p1 - p0 - 3 * p2 + p3) * t**3
            )
            out.append((float(q[0]), float(q[1])))
    out.append((float(a[-1, 0]), float(a[-1, 1])))
    return out


def _with_stalk(pts: list[tuple[float, float]]) -> np.ndarray:
    """Squeeze the blade into ``y`` in ``[STALK_TOP, 1]`` and hang it on a stalk to ``y = -1``."""
    sq = [(x, STALK_TOP + (y + 1.0) * (1.0 - STALK_TOP) / 2.0) for x, y in pts]
    low = min(range(len(sq)), key=lambda i: sq[i][1])
    y0 = sq[low][1]
    stalk = [
        (STALK_HALF_WIDTH, y0),
        (STALK_HALF_WIDTH, -1.0),
        (-STALK_HALF_WIDTH, -1.0),
        (-STALK_HALF_WIDTH, y0),
    ]
    return np.array(sq[:low] + stalk + sq[low + 1 :], dtype=float)


def leaf_outline(shape: LeafShape) -> np.ndarray:
    """
    A closed leaf polygon, starting at the tip, stalk at ``y = -1``.

    :param shape: The leaf.
    :return: ``(K, 2)`` outline, mirror-symmetric about ``x = 0``.
    """
    if shape.half is None:
        k = shape.width / 0.36 * _OVATE_TRUE
        right = _cubic((0, 1), (0.62, 0.58), (0.48, -0.12), (0.1, -0.82), 7)
        left = _cubic((-0.1, -0.82), (-0.48, -0.12), (-0.62, 0.58), (0, 1), 7)
        pts = [*right, (0.0, -1.0), *left[:-1]]
        return _with_stalk([(x * k, y) for x, y in pts])
    right = [(0.0, 1.0), *shape.half]
    half = _catmull_rom(right, 2) if shape.smooth else right
    bottom = half[-1]
    full = [*half, (0.0, bottom[1] - 0.02), *[(-x, y) for x, y in reversed(half[1:])]]
    return _with_stalk(full)


def outline_area(outline: np.ndarray) -> float:
    """Area enclosed by a closed ``(K, 2)`` outline (shoelace formula)."""
    x, y = outline[:, 0], outline[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def leaf_scale(species: str) -> float:
    """
    How much a species' outline is enlarged so its leaf covers as much as the
    ellipsoid leaf it replaces, between 1 and :data:`MAX_LEAF_SCALE`.

    :param species: A key of :data:`LEAF_SHAPES`.
    :return: Uniform scale on the unit outline.
    """
    area = outline_area(leaf_outline(LEAF_SHAPES.get(species, LEAF_SHAPES["chestnut"])))
    return float(np.clip(np.sqrt(ELLIPSOID_LEAF_AREA / area), 1.0, MAX_LEAF_SCALE))


def leaf_prototype(species: str, size: float) -> pv.PolyData:
    """
    One species leaf as a flat triangulated mesh, ready to stamp as a glyph.

    The blade runs along ``+x`` -- the axis a glyph call turns onto each
    leaf's direction -- and lies in the ``xy`` plane.  It is ``size`` from
    centre to tip before :func:`leaf_scale` enlarges it to cover the same
    area as the ellipsoid leaf of that size.

    :param species: A key of :data:`LEAF_SHAPES`; unknown species get the
        chestnut leaf.
    :param size: The ellipsoid leaf's radius this leaf replaces, in scene units.
    :return: The prototype ``PolyData``.
    """
    import pyvista as pv

    size = size * leaf_scale(species)
    outline = leaf_outline(LEAF_SHAPES.get(species, LEAF_SHAPES["chestnut"]))
    pts = np.column_stack([outline[:, 1] * size, outline[:, 0] * size, np.zeros(len(outline))])
    face = np.concatenate([[len(pts)], np.arange(len(pts))])
    return pv.PolyData(pts, face).triangulate()
