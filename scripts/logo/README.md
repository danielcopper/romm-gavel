# Logo

The mark: a gavel set in a disc, split along a facet that runs parallel to the head. It animates — the gavel lifts,
holds, and comes down, and the strike marks appear on the frame it lands.

It is built on the same recipe as [decky-romm-sync](https://github.com/danielcopper/decky-romm-sync)'s plugin mark, so
the two read as related: a 200-unit disc, a facet through its centre with the darker tone below-right, flat two-tone
ink, two warm accent dots on the ink. The body and the palette are what differ.

## Regenerating

```sh
python3 build.py --install
```

That renders everything and writes each shipped copy from the same render. Needs `rsvg-convert` and `ffmpeg` on PATH.
Without `--install` it writes to `out/` instead, which is the way to look at a change before it lands.

| File                        | Where it goes                         |
| --------------------------- | ------------------------------------- |
| `logo.svg`                  | `assets/` — the still mark            |
| `logo.png` (512px)          | `assets/` — a raster of the same      |
| `logo-animated.gif` (256px) | `assets/` — the loop the README shows |

`gen.py` and `anim.py` also stand alone, for looking at one thing:

```sh
python3 gen.py --list              # the palette names
python3 gen.py --palette glacier   # one mark, any palette
python3 gen.py --no-dots           # the bare body, for judging silhouette
python3 anim.py --plot             # the schedule, frame by frame
python3 anim.py --frame 35         # one frame's SVG
```

## Changing things

Three config objects, and nothing else worth editing:

- **`gen.Palette`** — one row per candidate in `PALETTES`; `CHOSEN` names the one that ships. Each carries two facet
  pairs, disc and ink, given as (above-left, below-right), plus the two warm dot colours. The ten rows are the
  candidates the mark was picked from, kept so a switch is one word.
- **`gen.Geometry`** — every position and size, in a 200-unit square: the disc and its facet, the head, the handle, the
  strike marks, the dots, and the pivot.
- **`anim.Motion`** — one row per timing in `MOTIONS`, `CHOSEN` names the shipped one. Wind-up angle, and how many
  frames go to the rest, the lift, the hold, the blow, and the marks.

## Notes

Three things are worth knowing before touching this.

**The facet clip belongs outside the rotation.** `clipPathUnits` defaults to `userSpaceOnUse`, so the polygon is read in
the user space of whatever references it. Put the clip group inside the rotation and the ink's seam turns with the body,
landing 38.36° off the disc's own — which shows up as a shadow inside the mark at a different angle to the one across
the disc.

**The resting pose is the pose the blow lands in.** Any rest above the landing has to be climbed back up afterwards, and
that climb is the last thing still moving once the marks are out — so the loop reads as "marks appear, then the hammer
is flung backwards". Landing on rest leaves nothing moving after the blow but the marks themselves.

**The blow must be fast without being invisible.** Squeezed into one or two frames the eye skips it entirely and again
sees only the marks and whatever moves after them. Five frames is fast against a lift that takes sixteen; the easing is
barely more than linear for the same reason, because a square law spends most of a short blow hovering at the top and
does the whole travel in its last frame.

Two smaller ones: the strike marks bound the wind-up, not the head — at the resting pose their tips already reach about
85 of the disc's 100 — and they drift outward as they fade rather than shrinking back into the head, because shrinking
back is the pop played in reverse. The GIF uses one palette for the whole sequence and no dithering; dithering flat
colour only adds grain and costs about a fifth of the file, because LZW cannot compress noise.
