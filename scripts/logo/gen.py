#!/usr/bin/env python3
"""The gavel mark: a hammer set in a disc that is split along a facet.

Built on the same recipe as decky-romm-sync's plugin mark, so the two read as
related: a 200-unit disc, a facet running through its centre with the darker
tone below-right, flat two-tone ink, and two warm accent dots sitting on the
ink. What differs is the body and the palette.

Two config objects and nothing else worth editing: a `Palette` (colours, one row
per candidate in `PALETTES`, `CHOSEN` names the one that ships) and a `Geometry`
(every position and size, in a 200-unit square).

    gen.py --list                 the palette names
    gen.py                        the chosen mark, to stdout
    gen.py --palette glacier      another one
    gen.py --no-dots              the bare body, for judging silhouette
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass

VIEW = 200.0
CX = CY = VIEW / 2.0


@dataclass(frozen=True)
class Palette:
    """Two facet pairs, each given as (above-left, below-right), plus the two
    warm dots. The dots sit *on* the ink, so the ink has to stay dark enough to
    carry them -- inverting the mark is not an option."""

    name: str
    disc: tuple[str, str]
    ink: tuple[str, str]
    dot_a: str
    dot_b: str


_TAN, _PEACH = "#e8c49c", "#dd9880"
_BRASS_A, _BRASS_B = "#f0c46a", "#d9992f"
_OAK_DISC = ("#e2c49a", "#c9a677")
_OAK_INK = ("#402a19", "#231710")

PALETTES: list[Palette] = [
    # The plugin's own palette -- the reference point.
    Palette("glacier", ("#92b7e3", "#779cc5"), ("#1f384b", "#1a1f25"), _TAN, _PEACH),
    # Same disc and ink, accents pulled to brass.
    Palette("brass", ("#92b7e3", "#779cc5"), ("#1f384b", "#1a1f25"), _BRASS_A, _BRASS_B),
    # The inversion: a warm disc with cool accents where the plugin has a cool
    # disc with warm ones. Same recipe, opposite temperature.
    Palette("oak", _OAK_DISC, _OAK_INK, "#9cc4e8", "#7fa8d8"),
    Palette("oak-teal", _OAK_DISC, _OAK_INK, "#7fc9bb", "#4fa596"),
    Palette("oak-plum", _OAK_DISC, _OAK_INK, "#e2a3bd", "#c07f9e"),
    Palette("oak-ember", _OAK_DISC, _OAK_INK, "#f4dcb2", "#df8a4e"),
    Palette("verdict", ("#d59a9a", "#b87b7b"), ("#4a1f24", "#25171a"), _TAN, _PEACH),
    Palette("moss", ("#93cbb0", "#77ab93"), ("#1f4b3b", "#1a2521"), _TAN, _PEACH),
    Palette("indigo", ("#b0a4e3", "#9285c5"), ("#2b1f4b", "#1c1a25"), _TAN, _PEACH),
    Palette("graphite", ("#b9c3cd", "#9ba6b1"), ("#23282e", "#15181c"), _BRASS_A, _BRASS_B),
]

BY_NAME: dict[str, Palette] = {p.name: p for p in PALETTES}

# What the shipped assets render from.
CHOSEN = "oak-teal"


@dataclass(frozen=True)
class Geometry:
    """Everything in a 200-unit square, measured from the disc's centre.

    The body is laid out in a frame rotated onto the facet, so +x runs along the
    seam and +y points into the darker half. That is what keeps the head's long
    axis parallel to the split instead of cutting across it."""

    disc_r: float = 100.0

    # The facet. Not 45 degrees: it comes from the plugin mark, where it runs
    # parallel to the button bars, which are slanted because the diamond they
    # sit on is wider than it is tall.
    facet_deg: float = 141.64

    head_y: float = -16.0
    head_w: float = 108.0
    head_h: float = 42.0

    handle_y: float = 26.0
    handle_w: float = 22.0
    handle_h: float = 60.0

    # The three strike marks, fanned off the head's striking end.
    mark_off: float = 17.0
    mark_len: float = 24.0
    mark_w: float = 9.0
    mark_fan: tuple[float, float, float] = (-30.0, 0.0, 30.0)

    dot_x: float = 28.0
    dot_r: float = 14.0

    # The gavel turns about its grip, not about the disc's centre.
    pivot_y: float = 50.0

    @property
    def rot_deg(self) -> float:
        """The rotation that puts a horizontal shape onto the facet."""
        return self.facet_deg - 180.0

    @property
    def strike_x(self) -> float:
        """Where the marks are anchored: the head's striking end."""
        return -self.head_w / 2.0

    def facet_polygon(self, reach: float = 800.0) -> str:
        """The darker half-plane, as a polygon far larger than the disc.

        A half-plane has no finite outline, so it is drawn as a rectangle long
        enough that its far edges never enter the disc."""
        a = math.radians(self.facet_deg)
        dx, dy = math.cos(a), math.sin(a)
        nx, ny = dy, -dx  # the seam's normal, pointing into the darker half
        corners = [
            (CX - dx * reach, CY - dy * reach),
            (CX + dx * reach, CY + dy * reach),
            (CX + dx * reach + nx * reach, CY + dy * reach + ny * reach),
            (CX - dx * reach + nx * reach, CY - dy * reach + ny * reach),
        ]
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in corners)


DEFAULT_GEOMETRY = Geometry()


# --------------------------------------------------------------------------- #
# Primitives. Offsets are from the disc's centre, in the rotated frame.
# --------------------------------------------------------------------------- #
def rounded(cx: float, cy: float, w: float, h: float, r: float, fill: str) -> str:
    if w <= 0.01 or h <= 0.01:
        return ""
    return (
        f'<rect x="{CX + cx - w / 2:.2f}" y="{CY + cy - h / 2:.2f}" '
        f'width="{w:.2f}" height="{h:.2f}" rx="{r:.2f}" fill="{fill}"/>'
    )


def circle(cx: float, cy: float, r: float, fill: str) -> str:
    return f'<circle cx="{CX + cx:.2f}" cy="{CY + cy:.2f}" r="{r:.2f}" fill="{fill}"/>'


def bar_at(px: float, py: float, deg: float, off: float, length: float, w: float, fill: str) -> str:
    """A rounded bar `off` out from an anchor, pointing along `deg`."""
    if length <= 0.01:
        return ""
    return (
        f'<g transform="rotate({deg:.2f} {CX + px:.2f} {CY + py:.2f})">'
        f"{rounded(px + off, py, length, w, w / 2.0, fill)}</g>"
    )


def turn(inner: str, g: Geometry) -> str:
    return f'<g transform="rotate({g.rot_deg:.2f} {CX} {CY})">{inner}</g>'


# --------------------------------------------------------------------------- #
# The body
# --------------------------------------------------------------------------- #
def body(fill: str, g: Geometry, swing: float = 0.0, marks: float = 0.0, drift: float = 0.0) -> str:
    """The gavel at one instant, in one ink tone.

    `swing` turns it about its grip. `marks` grows the three strike marks out of
    the striking end; `drift` pushes them further out as they go, so they read as
    dissipating rather than as the pop played backwards."""
    shapes = rounded(0.0, g.head_y, g.head_w, g.head_h, g.head_h / 2.0, fill)
    shapes += rounded(0.0, g.handle_y, g.handle_w, g.handle_h, g.handle_w / 2.0, fill)
    shapes += "".join(
        bar_at(
            g.strike_x,
            g.head_y,
            180.0 + fan,
            g.mark_off * marks + drift,
            g.mark_len * marks,
            g.mark_w,
            fill,
        )
        for fan in g.mark_fan
    )
    return _swung(shapes, swing, g)


def dots(pal: Palette, g: Geometry, swing: float = 0.0) -> str:
    pair = circle(-g.dot_x, g.head_y, g.dot_r, pal.dot_a) + circle(g.dot_x, g.head_y, g.dot_r, pal.dot_b)
    return _swung(pair, swing, g)


def _swung(shapes: str, swing: float, g: Geometry) -> str:
    if math.isclose(swing, 0.0):
        return shapes
    return f'<g transform="rotate({swing:.2f} {CX} {CY + g.pivot_y})">{shapes}</g>'


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def mark(
    uid: str,
    pal: Palette,
    g: Geometry = DEFAULT_GEOMETRY,
    swing: float = 0.0,
    marks: float = 0.0,
    drift: float = 0.0,
    show_dots: bool = True,
) -> str:
    """The disc, the body in both ink tones, and the dots.

    The facet clip sits OUTSIDE the rotation on purpose. `clipPathUnits` defaults
    to userSpaceOnUse, so the polygon is read in the user space of whatever
    references it; inside the rotation the ink's seam turns with the body and
    lands 38.36 degrees off the disc's own, which shows up as a shadow inside the
    mark running at a different angle to the one across the disc."""
    facet = g.facet_polygon()
    light = body(pal.ink[0], g, swing, marks, drift)
    dark = body(pal.ink[1], g, swing, marks, drift)
    return (
        f'<defs><clipPath id="d{uid}"><circle cx="{CX}" cy="{CY}" r="{g.disc_r}"/></clipPath>'
        f'<clipPath id="f{uid}"><polygon points="{facet}"/></clipPath></defs>'
        f'<g clip-path="url(#d{uid})">'
        f'<circle cx="{CX}" cy="{CY}" r="{g.disc_r}" fill="{pal.disc[0]}"/>'
        f'<polygon points="{facet}" fill="{pal.disc[1]}"/>'
        f"{turn(light, g)}"
        f'<g clip-path="url(#f{uid})">{turn(dark, g)}</g>'
        f"{turn(dots(pal, g, swing), g) if show_dots else ''}"
        f"</g>"
    )


def standalone(
    pal: Palette,
    g: Geometry = DEFAULT_GEOMETRY,
    size: int = 512,
    swing: float = 0.0,
    marks: float = 0.0,
    drift: float = 0.0,
    show_dots: bool = True,
) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {VIEW:.0f} {VIEW:.0f}">'
        f'{mark("m", pal, g, swing, marks, drift, show_dots)}</svg>'
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the palette names and exit")
    ap.add_argument("--palette", default=CHOSEN, help=f"palette to render (default: {CHOSEN})")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--no-dots", action="store_true", help="the bare body, for judging silhouette")
    args = ap.parse_args(argv)

    if args.list:
        print("\n".join(p.name for p in PALETTES))
        return 0
    if args.palette not in BY_NAME:
        print(f"unknown palette {args.palette!r}; try --list", file=sys.stderr)
        return 2
    print(standalone(BY_NAME[args.palette], size=args.size, show_dots=not args.no_dots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
