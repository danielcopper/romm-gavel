#!/usr/bin/env python3
"""The strike: the gavel lifts, holds, comes down, and the marks appear.

Two things decide whether the loop reads forwards, and both are easy to get
wrong in a way that looks like the animation is playing backwards.

**The resting pose has to be the pose the blow lands in.** Rest anywhere above
the landing means the gavel must travel back up afterwards, and that climb is
the last thing still moving once the marks are out -- so the eye reads the loop
as "marks appear, then the hammer is flung backwards".

**The blow must be fast without being invisible.** Compressed into one or two
frames it is simply skipped, and again only the marks and whatever moves after
them are seen. Five frames is fast against a lift that takes sixteen and still
shows the head travelling; the easing is barely more than linear for the same
reason, because a square law spends most of a short blow hovering at the top and
does the whole travel in the last frame.

    anim.py --list                the motion names
    anim.py --plot                the schedule, frame by frame
    anim.py --frame 35            one frame's SVG
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import gen


@dataclass(frozen=True)
class Motion:
    """One loop. Frame 0 is the resting pose, and so is the landing."""

    name: str
    top: float  # wind-up angle; the head clears the rim to about 40 degrees
    frames: int = 50
    fps: int = 25  # 50 @ 25 = 2.0s
    rest: int = 6  # stillness before anything happens
    lift: int = 16
    hold: int = 6  # held at the top: separates the lift from the blow
    blow: int = 5
    flash: int = 6  # marks at full length
    fade: int = 5  # ...then shorter, and drifting outward

    @property
    def top_at(self) -> int:
        return self.rest + self.lift

    @property
    def land_at(self) -> int:
        """The frame the head arrives on the resting pose."""
        return self.top_at + self.hold + self.blow

    def at(self, i: int) -> tuple[float, float, float]:
        """(swing, marks, drift) at frame `i`."""
        i %= self.frames
        top_end = self.top_at + self.hold
        if i < self.rest:
            swing = 0.0
        elif i < self.top_at:
            swing = self.top * _smooth(_seg(i, self.rest, self.top_at))
        elif i < top_end:
            swing = self.top
        elif i < self.land_at:
            swing = self.top * (1.0 - _seg(i, top_end, self.land_at) ** 1.35)
        else:
            swing = 0.0  # landed, and stays landed

        land = self.land_at
        if i < land:
            return swing, 0.0, 0.0
        if i < land + self.flash:
            return swing, 1.0, 0.0
        if i < land + self.flash + self.fade:
            u = _seg(i, land + self.flash, land + self.flash + self.fade)
            return swing, 1.0 - 0.45 * u, 12.0 * u
        return swing, 0.0, 0.0

    def turning_points(self) -> list[int]:
        """The frames worth looking at when reviewing a change."""
        top_end = self.top_at + self.hold
        land = self.land_at
        return [0, (self.rest + self.top_at) // 2, self.top_at, top_end, (top_end + land) // 2,
                land, land + 2, land + 5, land + 9, self.frames - 2]


def _smooth(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)


def _seg(i: int, lo: int, hi: int) -> float:
    return (i - lo) / (hi - lo)


MOTIONS: list[Motion] = [
    Motion("soft", top=28.0),
    # Longer pause at the top, shorter blow. Harder, at the cost of a blow only
    # three frames wide.
    Motion("hard", top=28.0, lift=18, hold=8, blow=3),
    Motion("wide", top=38.0),
]

BY_NAME: dict[str, Motion] = {m.name: m for m in MOTIONS}

# What the shipped GIF renders from.
CHOSEN = "hard"


def frame(i: int, pal: gen.Palette, motion: Motion, g: gen.Geometry = gen.DEFAULT_GEOMETRY, size: int = 256) -> str:
    swing, marks, drift = motion.at(i)
    return gen.standalone(pal, g, size=size, swing=swing, marks=marks, drift=drift)


def plot(motion: Motion) -> str:
    rows = ["frame  swing   marks   drift"]
    for i in range(motion.frames):
        swing, marks, drift = motion.at(i)
        hit = "  <- lands" if i == motion.land_at else ""
        rows.append(f"{i:5d}  {swing:6.2f}  {marks:5.2f}  {drift:5.2f}{hit}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--motion", default=CHOSEN, help=f"motion to use (default: {CHOSEN})")
    ap.add_argument("--palette", default=gen.CHOSEN)
    ap.add_argument("--plot", action="store_true", help="print the schedule frame by frame")
    ap.add_argument("--frame", type=int, help="print one frame's SVG")
    args = ap.parse_args(argv)

    if args.list:
        print("\n".join(m.name for m in MOTIONS))
        return 0
    if args.motion not in BY_NAME or args.palette not in gen.BY_NAME:
        print("unknown motion or palette; try --list", file=sys.stderr)
        return 2

    motion = BY_NAME[args.motion]
    if args.plot:
        print(plot(motion))
    elif args.frame is not None:
        print(frame(args.frame, gen.BY_NAME[args.palette], motion))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
