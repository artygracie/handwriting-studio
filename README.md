# Inkwell — local handwriting studio

A calligrapher.ai-style tool that runs **entirely on your machine**. Type a note
on the left, see real handwriting render on a true-to-size sheet of paper on the
right, then export **plotter-ready G-code** (or SVG) for the Bachin T-A4.

Built on the [otuva/handwriting-synthesis](https://github.com/otuva/handwriting-synthesis)
RNN (Alex Graves' handwriting model, TensorFlow 2), vendored under `vendor/`.

![layout: composer on the left, paper preview on the right]

## Features

- **Live preview** on real paper sizes — A4, A5, A6/A7, US Letter, Half-Letter,
  plus 5×7 / 4×6 / A2 note cards and tented place cards. Portrait or landscape.
- **Multi-paragraph notes** — automatic word-wrap to the page width, blank lines
  become paragraph gaps.
- **Fill page** — the note auto-sizes and word-wraps to pack the whole text
  area (it grows *and* shrinks to fit), so the sheet never comes out half-empty.
  Per-character width is measured from the model so lines fill the width
  properly. Turn it off to set an exact text size.
- **Controls:** handwriting style (13 hands), legibility, text size, line height,
  ink colour, margins, and the **pen** (defaults to the loaded **Zebra G-750**,
  0.7 mm — one consistent weight across the whole note).
- **Shuffle** for a fresh variation of the same text.
- **Fast tweaks** — changing stroke width, colour, line height, etc. re-renders
  instantly; only changing the text, style, size or legibility re-runs the model
  (strokes are cached per line).
- **Download SVG** — physically sized in millimetres.
- **Download G-code** — GRBL G-code for the Bachin T-A4 (servo pen-lift),
  ready to stream straight to the plotter. No vpype step required.

## Setup (one time)

Uses a plain virtualenv off a **native arm64 Python** (the system
`/usr/bin/python3` is perfect). It deliberately avoids the system x86_64 conda:
Intel TensorFlow needs AVX, which Rosetta can't emulate, so we use Apple's
`tensorflow-macos` build instead.

```bash
cd inkwell
./setup.sh          # creates ./venv and installs deps (~1 GB download)
```

## Run

```bash
./run.sh            # serves http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>. The handwriting model loads on the **first render**
(~10–20 s the first time), then stays warm.

## From note to plotted paper

1. Compose and style your note, then **Download G-code**.
2. Copy `inkwell-note.gcode` to the machine wired to the T-A4 and stream it with
   Universal G-code Sender. It homes at top-left and writes at the previewed
   millimetre size.

The G-code uses GRBL servo pen-lift — `M3 S<down>` to lower the pen, `M5` to
lift, with a short dwell so the servo settles (see `gcode.py` to tune the
servo values, feed rate, or dwell). Prefer the old SVG → vpype route? **Download
SVG** still works:

```bash
vpype read inkwell-note.svg gwrite --profile gcode note.gcode
```

## Notes & limits

- The model's alphabet is limited. Inkwell transliterates common characters
  (curly quotes → straight, em-dash → hyphen, `&` → "and") and **lowercases
  Q/X/Z** (the model never learned those capitals). Anything it can't represent
  is dropped and reported in a warning.
- Max 75 characters per *rendered* line (a model constraint); wrapping handles
  this automatically.
- Single page per note. For very long notes, lower the text size or split across
  several notes.

## Project layout

```
inkwell/
  server.py          FastAPI app (serves UI + /api/render + /api/gcode)
  engine.py          sampling + caching + paper-aware fill layout → SVG
  gcode.py           SVG → GRBL G-code for the Bachin T-A4 (servo pen-lift)
  papers.py          paper-size presets (mm)
  static/            index.html · style.css · app.js
  vendor/            otuva/handwriting-synthesis (model + 43 MB checkpoint)
  requirements.txt · setup.sh · run.sh
```

## Tuning

If text consistently renders a little large/small, adjust `REF_GLYPH_UNITS` in
`engine.py` (lower = bigger text); `MAX_FILL_MM` caps how large Fill page will
grow short notes. Wrap width is driven by a per-style width measured from the
model (`_raw_per_char`), so lines fill the page width without a hand-tuned ratio.
For the plotter, tune servo values / feed / dwell in `gcode.py`.
