#!/usr/bin/env python3
"""Draw the GutenbergKG logo in Art Techno and write every size the repo uses.

The mark is an open book drawn as four traces at one pitch, notched at the
gutter. A die sits in the gutter and a graph fan rises from it: text in,
knowledge graph out. The palette, drawing helpers and outlined lettering come
from the Art Techno brand build, so the SVGs render the same everywhere.

Usage::

    python scripts/build_logo.py

Needs ``fonttools`` and Pillow, Google Chrome for the PNG renders, and a clone
of https://github.com/Flux-Frontiers/art_techno beside this repo. Set ``CHROME``
to the browser binary if it is not at the default macOS path.

Writes, under the repo root:

- ``assets/gutenbergkg_logo.svg`` and ``.png``: the square mark (1024 px PNG)
- ``assets/logos/gutenbergkg_logo.svg``, ``gutenbergkg_icon.svg`` and
  ``gutenbergkg_banner.svg`` and ``.png``
- ``assets/logos/logo_{512,256,128}.png`` from the mark and
  ``logo_{64,32}.png`` from the icon
- ``assets/badges/badge_200.png`` from the mark and ``badge_{80,40,20}.png``
  from the icon
- ``docs/assets/logo.png`` and ``docs/assets/favicon.png`` from the icon
"""

import importlib.util
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
AT_BUILD = ROOT.parent / "art_techno" / "docs" / "brand" / "build.py"

_spec = importlib.util.spec_from_file_location("at_build", AT_BUILD)
at = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(at)

f, line, pad, via, diamond, clipped_rect = (
    at.f,
    at.line,
    at.pad,
    at.via,
    at.diamond,
    at.clipped_rect,
)
OBSIDIAN, COPPER, GOLD, GREEN, MINT = at.OBSIDIAN, at.COPPER, at.GOLD, at.GREEN, at.MINT

NAME = "GUTENBERGKG"
PART = "THE KNOWLEDGE PRESS"


def lozenge(x: float, y: float, r: float) -> str:
    """The die lozenge: a green diamond in a gold line with a gold core."""
    return (
        f'<path d="M{f(x)} {f(y - r)}L{f(x + r)} {f(y)}L{f(x)} {f(y + r)}L{f(x - r)} {f(y)}Z" '
        f'fill="{GREEN}" stroke="{GOLD}" stroke-width="{f(r / 8)}"/>' + diamond(x, y, r / 3, GOLD)
    )


def book() -> str:
    """The open book and its graph fan on a 512 field, centered on x = 256."""
    out = []
    ox, oy = 256, 268
    y0, a = 270, 36
    # Wavefront arcs through each ring of nodes.
    for r, a0 in ((125, 15), (200, 30)):
        dx, dy = r * math.cos(math.radians(a0)), r * math.sin(math.radians(a0))
        out.append(
            f'<path d="M{f(ox - dx)} {f(oy - dy)}A{r} {r} 0 0 1 {f(ox + dx)} {f(oy - dy)}" '
            f'fill="none" stroke="{GOLD}" stroke-width="2" stroke-opacity=".6"/>'
        )
    # Rays from the die: long gold to the outer ring, short copper to the inner.
    nodes = []
    for deg in range(15, 166, 15):
        long = deg % 30 == 0
        r1 = 200 if long else 125
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        out.append(
            line(
                [(ox + 46 * c, oy - 46 * s), (ox + r1 * c, oy - r1 * s)],
                GOLD if long else COPPER,
                5 if long else 4,
            )
        )
        nodes.append((ox + r1 * c, oy - r1 * s, long))
    for x, y, long in nodes:
        out.append(pad(x, y, 13, GOLD) + pad(x, y, 5.5, GREEN) if long else via(x, y, 9, COPPER))
    # Pages: four traces at one pitch, each notched at the gutter. The corner
    # moves out by d * tan(22.5 deg) so the pitch holds through the bend.
    t = math.tan(math.radians(22.5))
    for j, (col, w) in enumerate(((GOLD, 6), (COPPER, 5), (COPPER, 5), (GOLD, 6))):
        d = 12 * j
        y = y0 + d
        cx = a + t * d
        end = 84 + 12 * j
        pts = [
            (end, y),
            (ox - cx, y),
            (ox, y0 + a + d * math.sqrt(2)),
            (ox + cx, y),
            (512 - end, y),
        ]
        out.append(line(pts, col, w))
        out.append(via(end - 6, y, 7.5, col) + via(512 - end + 6, y, 7.5, col))
    # The die in the gutter: the origin of the fan.
    out.append(lozenge(ox, oy, 32))
    return "".join(out)


def book_small() -> str:
    """The book reduced for 64 px and below: the die, two pages, three rays."""
    out = []
    ox, oy = 32, 30
    d = 1 / math.sqrt(2)
    for dx, dy in ((0, -1), (-d, -d), (d, -d)):
        out.append(line([(ox + 10 * dx, oy + 10 * dy), (ox + 20 * dx, oy + 20 * dy)], GOLD, 3))
        out.append(pad(ox + 20 * dx, oy + 20 * dy, 4, GOLD))
    for y, apex, col in ((32, 44, GOLD), (39, 53.9, COPPER)):
        cx = apex - y
        out.append(line([(9, y), (ox - cx, y), (ox, apex), (ox + cx, y), (55, y)], col, 3.2))
    out.append(lozenge(ox, oy, 9))
    return "".join(out)


def frame(w: float, h: float, inset: float, c: float, heavy: float) -> str:
    """Double frame with 45-degree corners and a green diamond at each corner.

    :param w: Canvas width.
    :param h: Canvas height.
    :param inset: Distance of the heavy line from the canvas edge.
    :param c: Corner cut of the heavy line.
    :param heavy: Stroke width of the heavy line.
    """
    out = [
        f'<path d="{clipped_rect(inset, inset, w - 2 * inset, h - 2 * inset, c)}" fill="none" stroke="{GOLD}" stroke-width="{f(heavy)}"/>',
        f'<path d="{clipped_rect(inset * 1.9, inset * 1.9, w - 3.8 * inset, h - 3.8 * inset, c * 0.75)}" fill="none" stroke="{GOLD}" stroke-width="{f(heavy * 0.4)}" stroke-opacity=".6"/>',
    ]
    d = inset * 1.45 + c * 0.4375
    for cx, cy in ((d, d), (w - d, d), (d, h - d), (w - d, h - d)):
        out.append(diamond(cx, cy, inset * 0.5, GREEN))
    return "".join(out)


def svg(w: int, h: int, title: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"<title>{title}</title>"
        f'<rect width="{w}" height="{h}" fill="{OBSIDIAN}"/>{body}</svg>\n'
    )


def mark(display, mono) -> str:
    """512 square mark: the book, the name and the part line beneath."""
    body = frame(512, 512, 10, 26, 5) + book()
    size = min(40, 40 * 384 / display.width(NAME, 40, 0.2))
    body += display.path(NAME, 256, 430, size, 0.2, "middle", GOLD)
    body += mono.path(PART, 256, 462, 13.5, 0.3, "middle", MINT)
    return svg(512, 512, "GutenbergKG mark, Art Techno", body)


def icon() -> str:
    """64 icon: the reduced book in one heavy frame, no lettering."""
    body = f'<path d="{clipped_rect(2.5, 2.5, 59, 59, 7.5)}" fill="none" stroke="{GOLD}" stroke-width="3"/>'
    return svg(64, 64, "GutenbergKG icon, Art Techno", body + book_small())


def banner(display, mono) -> str:
    """1280 x 320 banner: the book left, the name and part line right."""
    s = 0.78
    body = frame(1280, 320, 10, 18, 3)
    body += (
        f'<g transform="translate({f(230 - 256 * s)} {f(160 - 213 * s)}) scale({s})">{book()}</g>'
    )
    cx = (450 + 1240) / 2
    size = min(68, 68 * 740 / display.width(NAME, 68, 0.2))
    body += display.path(NAME, cx, 172, size, 0.2, "middle", GOLD)
    body += mono.path(PART, cx, 222, 17, 0.3, "middle", MINT)
    return svg(1280, 320, "GutenbergKG banner, Art Techno", body)


def render(src: Path, out: Path, w: int, h: int) -> None:
    """Render the SVG ``src`` to ``out`` at ``w`` x ``h`` px with headless Chrome.

    :param src: SVG file; its ``width`` attribute sets the CSS width.
    :param out: PNG to write.
    :param w: Output width in px.
    :param h: Output height in px.
    """
    svg_w = int(src.read_text().split('width="', 1)[1].split('"', 1)[0])
    subprocess.run(
        [
            at.CHROME,
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={svg_w},{svg_w * h // w}",
            f"--force-device-scale-factor={w / svg_w}",
            f"--screenshot={out}",
            src.as_uri(),
        ],
        check=True,
        capture_output=True,
    )


def resized(master: Path, dest: Path, px: int) -> None:
    Image.open(master).convert("RGB").resize((px, px), Image.LANCZOS).save(dest, optimize=True)


def main() -> None:
    at.fetch_fonts()
    display = at.Face(at.CACHE / "JosefinSans.ttf", weight=600)
    mono = at.Face(at.CACHE / "IBMPlexMono-Medium.ttf")

    assets = ROOT / "assets"
    logos = assets / "logos"
    badges = assets / "badges"
    docs = ROOT / "docs" / "assets"

    mark_svg = assets / "gutenbergkg_logo.svg"
    icon_svg = logos / "gutenbergkg_icon.svg"
    banner_svg = logos / "gutenbergkg_banner.svg"
    mark_svg.write_text(mark(display, mono))
    (logos / "gutenbergkg_logo.svg").write_text(mark_svg.read_text())
    icon_svg.write_text(icon())
    banner_svg.write_text(banner(display, mono))

    render(mark_svg, assets / "gutenbergkg_logo.png", 1024, 1024)
    render(banner_svg, banner_svg.with_suffix(".png"), 2560, 640)
    with tempfile.TemporaryDirectory() as tmp:
        icon_png = Path(tmp) / "icon.png"
        render(icon_svg, icon_png, 1024, 1024)
        for px in (512, 256, 128):
            resized(assets / "gutenbergkg_logo.png", logos / f"logo_{px}.png", px)
        for px in (64, 32):
            resized(icon_png, logos / f"logo_{px}.png", px)
        resized(assets / "gutenbergkg_logo.png", badges / "badge_200.png", 200)
        for px in (80, 40, 20):
            resized(icon_png, badges / f"badge_{px}.png", px)
        resized(icon_png, docs / "logo.png", 256)
        resized(icon_png, docs / "favicon.png", 32)


if __name__ == "__main__":
    main()
