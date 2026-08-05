#!/usr/bin/env python3
"""Render the mark and write every shipped copy from the same render.

    build.py --install            write assets/ (what ships)
    build.py                      write out/ instead, to look at a change first
    build.py --palette moss --motion wide --install

Needs `rsvg-convert` and `ffmpeg` on PATH.

| File                | Where it goes                        |
| ------------------- | ------------------------------------ |
| `logo.svg`          | `assets/` -- the still mark          |
| `logo.png` (512px)  | `assets/` -- raster of the same      |
| `logo-animated.gif` | `assets/` -- the loop the README uses |
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

import anim
import gen

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Flat colours, no dithering: dithering flat colour only adds grain, and costs
# about a fifth of the file because LZW cannot compress noise.
GIF_FILTER = (
    "[0:v]split[a][b];"
    "[a]palettegen=max_colors=32:stats_mode=full:reserve_transparent=1[p];"
    "[b][p]paletteuse=dither=none:diff_mode=rectangle"
)


# Sizes reach rsvg-convert as command arguments, so they are range-checked
# before they get there rather than passed through as whatever was typed.
MIN_PX, MAX_PX = 16, 4096


def checked_px(value: int, flag: str) -> int:
    if not MIN_PX <= value <= MAX_PX:
        raise SystemExit(f"{flag} must be between {MIN_PX} and {MAX_PX}, not {value}")
    return value


def require(*tools: str) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        raise SystemExit(f"not on PATH: {', '.join(missing)}")


def rasterise(svg: str, png: pathlib.Path, size: int) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(svg)
        tmp = pathlib.Path(fh.name)
    try:
        subprocess.run(["rsvg-convert", "-w", str(size), "-o", str(png), str(tmp)], check=True)
    finally:
        tmp.unlink(missing_ok=True)


def build_gif(out: pathlib.Path, pal: gen.Palette, motion: anim.Motion, size: int) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gavel-logo"))
    try:
        for i in range(motion.frames):
            rasterise(anim.frame(i, pal, motion, size=size), tmp / f"f{i:03d}.png", size)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-framerate", str(motion.fps), "-i", str(tmp / "f%03d.png"),
             "-filter_complex", GIF_FILTER, "-loop", "0", str(out)],
            check=True,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build(out: pathlib.Path, pal: gen.Palette, motion: anim.Motion, size: int, gif_size: int) -> None:
    require("rsvg-convert", "ffmpeg")
    out.mkdir(parents=True, exist_ok=True)

    svg = out / "logo.svg"
    svg.write_text(gen.standalone(pal, size=size))
    rasterise(svg.read_text(), out / "logo.png", size)
    build_gif(out / "logo-animated.gif", pal, motion, gif_size)

    for name in ("logo.svg", "logo.png", "logo-animated.gif"):
        path = out / name
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,}b)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true", help="write assets/ instead of out/")
    ap.add_argument("--palette", default=gen.CHOSEN, help=f"default: {gen.CHOSEN}")
    ap.add_argument("--motion", default=anim.CHOSEN, help=f"default: {anim.CHOSEN}")
    ap.add_argument("--size", type=int, default=512, help="the still, in px")
    ap.add_argument("--gif-size", type=int, default=256, help="the animation, in px")
    args = ap.parse_args(argv)

    if args.palette not in gen.BY_NAME:
        print(f"unknown palette {args.palette!r}; gen.py --list", file=sys.stderr)
        return 2
    if args.motion not in anim.BY_NAME:
        print(f"unknown motion {args.motion!r}; anim.py --list", file=sys.stderr)
        return 2

    out = ROOT / "assets" if args.install else pathlib.Path(__file__).parent / "out"
    build(
        out,
        gen.BY_NAME[args.palette],
        anim.BY_NAME[args.motion],
        checked_px(args.size, "--size"),
        checked_px(args.gif_size, "--gif-size"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
