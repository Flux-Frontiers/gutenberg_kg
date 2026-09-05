#!/usr/bin/env python3
"""Render The Knowledge Press app icon from the brand system.

Nothing here is invented. ``assets/brand-system/GutenbergKG Brand.dc.html``
already specifies this mark and even names its purpose:

    APP ICON / FAVICON — The graph collapses into a dark disc: the
    movable-type G at the press hub, six satellites for the ingest sources.
    Reads cleanly at 32 px.

This is a transcription of that file's ``badgeSVG()`` into Pillow, at the
sizes Xcode wants. The geometry is its 96x96 viewBox scaled to the target;
the accent and glyph come from its module table, where GutenbergKG is
``accent: '#2ECC71', serif: 'G'``.

The brain remains the flagship lockup — the brand system is explicit that the
brain is "flagship equity" and the badge is what "carries the family down to a
32 px favicon". An icon cannot carry the wordmark or the brain's interior
detail, so the badge is the correct mark here, not a reduction of the wrong one.

One substitution, deliberate: the glyph should be Fraunces, which is not
installed. Charter is the nearest local serif with comparable weight and
small-size sturdiness. Swap FONT_CANDIDATES if Fraunces ever lands.

Run:
    python scripts/make_app_icon.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# Drawn at SS x and downsampled — Pillow has no antialiased primitives.
BASE = 1024
SS = 4

# From the module table in the brand system.
INK = (0x16, 0x1D, 0x2B)
ACCENT = (0x2E, 0xCC, 0x71)

# The badge inside the square. The brand's disc already fills its own box
# (r=46 of 96), so this is the icon's outer breathing room, not the disc's.
BADGE_FRACTION = 0.86

# badgeSVG()'s 96x96 viewBox, verbatim.
VIEW = 96.0
CENTRE = 48.0
DISC_R = 46.0
RING_W = 2.0
RING_ALPHA = 0.5
EDGE_W = 2.4
EDGE_ALPHA = 0.9
SATELLITES = [(26, 28), (48, 20), (70, 28), (26, 68), (48, 76), (70, 68)]
SATELLITE_R = 5.0
HUB_R = 16.0
GLYPH = "G"
GLYPH_SIZE = 0.20  # of the badge box, per glyphHTML()

FONT_CANDIDATES = [
    "/Library/Fonts/Fraunces.ttf",
    "/System/Library/Fonts/Supplemental/Charter.ttc",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Times.ttc",
]

MACOS_SIZES = [
    (16, 1),
    (16, 2),
    (32, 1),
    (32, 2),
    (128, 1),
    (128, 2),
    (256, 1),
    (256, 2),
    (512, 1),
    (512, 2),
]


def _blend(colour: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Flatten a translucent accent against the ink.

    The badge's ring and edges carry opacity. Compositing them for real would
    need a second layer per stroke; against a known opaque ink the blend is
    exact and costs nothing.

    :param colour: Foreground.
    :param alpha: 0 is pure ink, 1 is pure ``colour``.
    :returns: The flattened colour.
    """
    return tuple(int(round(INK[i] + (colour[i] - INK[i]) * alpha)) for i in range(3))


def _serif(px: int) -> ImageFont.FreeTypeFont:
    """Load the heaviest available serif at ``px``.

    :param px: Font size in pixels.
    :returns: A usable font; Pillow's default only if nothing else exists.
    """
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        for index in (1, 0):  # Charter.ttc and Times.ttc put bold at 1.
            try:
                return ImageFont.truetype(path, px, index=index)
            except Exception:  # noqa: BLE001 — try the next face or file.
                continue
    return ImageFont.load_default()


def render_icon(size: int = BASE) -> Image.Image:
    """Draw the badge, centred on an ink square.

    :param size: Final edge in pixels.
    :returns: An RGB image, full bleed. iOS masks the corners itself, so no
        rounding is applied.
    """
    canvas = size * SS
    img = Image.new("RGB", (canvas, canvas), INK)
    draw = ImageDraw.Draw(img)

    badge = canvas * BADGE_FRACTION
    origin = (canvas - badge) / 2.0
    unit = badge / VIEW

    def at(x: float, y: float) -> tuple[float, float]:
        return origin + x * unit, origin + y * unit

    def disc(x: float, y: float, r: float, fill) -> None:
        cx, cy = at(x, y)
        rr = r * unit
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=fill)

    # The disc is ink on ink; the ring is what gives it an edge.
    disc(CENTRE, CENTRE, DISC_R, INK)
    cx, cy = at(CENTRE, CENTRE)
    rr = DISC_R * unit
    draw.ellipse(
        [cx - rr, cy - rr, cx + rr, cy + rr],
        outline=_blend(ACCENT, RING_ALPHA),
        width=max(1, round(RING_W * unit)),
    )

    edge_colour = _blend(ACCENT, EDGE_ALPHA)
    edge_w = max(1, round(EDGE_W * unit))
    for sx, sy in SATELLITES:
        draw.line([at(CENTRE, CENTRE), at(sx, sy)], fill=edge_colour, width=edge_w)
        # Pillow's line has no round cap; a disc at each end supplies it.
        for px, py in ((CENTRE, CENTRE), (sx, sy)):
            hx, hy = at(px, py)
            h = edge_w / 2.0
            draw.ellipse([hx - h, hy - h, hx + h, hy + h], fill=edge_colour)

    for sx, sy in SATELLITES:
        disc(sx, sy, SATELLITE_R, ACCENT)

    disc(CENTRE, CENTRE, HUB_R, ACCENT)

    glyph_px = max(1, round(badge * GLYPH_SIZE))
    font = _serif(glyph_px)
    # Centre on the glyph's inked bounds, not its metrics: a serif capital
    # sits well above the baseline and metric-centring drops it low in the hub.
    box = draw.textbbox((0, 0), GLYPH, font=font)
    draw.text(
        (cx - (box[0] + box[2]) / 2.0, cy - (box[1] + box[3]) / 2.0),
        GLYPH,
        font=font,
        fill=INK,
    )

    return img.resize((size, size), Image.LANCZOS)


def _macos_variant(icon: Image.Image, size: int) -> Image.Image:
    """Inset the mark in a rounded square, the way macOS icons are drawn.

    A full-bleed square looks foreign in the Dock, where every neighbour is a
    rounded rectangle with air around it. iOS is the opposite: it masks the
    corners itself, and full bleed is correct there.

    :param icon: The full-bleed mark.
    :param size: Target edge.
    :returns: An RGBA image with transparent margins.
    """
    inset = round(size * 0.094)
    inner = size - inset * 2
    if inner <= 0:
        return icon.resize((size, size), Image.LANCZOS).convert("RGBA")

    ss = 4 if size < 256 else 2
    mask = Image.new("L", (inner * ss, inner * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, inner * ss - 1, inner * ss - 1],
        radius=int(inner * ss * 0.2237),  # Apple's continuous-corner ratio
        fill=255,
    )
    mask = mask.resize((inner, inner), Image.LANCZOS)

    body = icon.resize((inner, inner), Image.LANCZOS).convert("RGBA")
    body.putalpha(mask)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(body, (inset, inset), body)
    return out


def write_catalogs() -> None:
    """Render the icon and write both asset catalogs."""
    icon = render_icon(BASE)

    master = ROOT / "app" / "icon"
    master.mkdir(parents=True, exist_ok=True)
    icon.save(master / "AppIcon-1024.png")
    # A proof sheet at the sizes the brand system calls out, so a regression
    # in small-size legibility is visible without installing anything.
    sheet = Image.new("RGB", (96 + 56 + 32 + 20 + 5 * 16, 96 + 32), INK)
    x = 16
    for s in (96, 56, 32, 20):
        sheet.paste(icon.resize((s, s), Image.LANCZOS), (x, 16 + (96 - s) // 2))
        x += s + 16
    sheet.save(master / "AppIcon-proof.png")

    ios = ROOT / "app" / "ios" / "Assets.xcassets" / "AppIcon.appiconset"
    ios.mkdir(parents=True, exist_ok=True)
    icon.save(ios / "AppIcon-1024.png")
    (ios / "Contents.json").write_text(
        json.dumps(
            {
                "images": [
                    {
                        "idiom": "universal",
                        "platform": "ios",
                        "size": "1024x1024",
                        "filename": "AppIcon-1024.png",
                    }
                ],
                "info": {"author": "xcode", "version": 1},
            },
            indent=2,
        )
        + "\n"
    )

    mac = ROOT / "app" / "macos" / "Assets.xcassets" / "AppIcon.appiconset"
    mac.mkdir(parents=True, exist_ok=True)
    entries = []
    for pt, scale in MACOS_SIZES:
        name = f"AppIcon-{pt}x{pt}@{scale}x.png"
        _macos_variant(icon, pt * scale).save(mac / name)
        entries.append(
            {"idiom": "mac", "size": f"{pt}x{pt}", "scale": f"{scale}x", "filename": name}
        )
    (mac / "Contents.json").write_text(
        json.dumps({"images": entries, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n"
    )

    for catalog in (ios.parent, mac.parent):
        (catalog / "Contents.json").write_text(
            json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n"
        )

    print(f"wrote {master / 'AppIcon-1024.png'}")
    print(f"wrote {master / 'AppIcon-proof.png'}")
    print(f"wrote {ios.relative_to(ROOT)} (1 image)")
    print(f"wrote {mac.relative_to(ROOT)} ({len(entries)} images)")


if __name__ == "__main__":
    write_catalogs()
