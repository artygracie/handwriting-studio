# Inkwell — local handwriting studio

A calligrapher.ai-style tool that runs **entirely on your machine**. Type a note
on the left, watch real handwriting render on a true-to-size sheet of paper on
the right, then export **plotter-ready G-code** (or SVG) for a pen plotter such
as the Bachin Draw T-A4.

Built on the [otuva/handwriting-synthesis](https://github.com/otuva/handwriting-synthesis)
RNN (Alex Graves' handwriting model, TensorFlow 2), **bundled** under `vendor/`
— there's no extra model download.

## Features

- **Live preview** on real paper sizes — A4, A5, A6/A7, US Letter, Half-Letter,
  plus 5×7 / 4×6 / A2 note cards and tented place cards. Portrait or landscape.
- **Multi-paragraph notes** — word-wraps to the page width (never breaks a word),
  blank lines become paragraph gaps.
- **Fill page** — auto-sizes the text and packs it edge-to-edge so the sheet
  never comes out half-empty. The per-character width is measured from your
  chosen hand, so lines fill right up to the margin and the text grows to its
  true maximum. Turn it off to set an exact text size.
- **Controls:** handwriting style (13 hands), legibility, text size, line height,
  ink colour, margins, and the **pen** (defaults to a **Zebra G-750**, 0.7 mm —
  one consistent line weight across the whole note).
- **Shuffle** for a fresh variation of the same text.
- **Fast tweaks** — changing stroke width, colour, line height, etc. re-renders
  instantly; only changing the text, style, size or legibility re-runs the model
  (strokes are cached per line).
- **Download SVG** — physically sized in millimetres.
- **Download G-code** — GRBL G-code (servo pen-lift), ready to stream to the
  plotter. No vpype step required.
- **Plotter handoff panel** — an in-app, copy-able spec sheet (units, origin,
  pen commands, the current canvas's size / margins / ink bounds) to hand to
  whoever runs the machine.

## Requirements

- **Python 3.8–3.11.** TensorFlow 2.12 does **not** support 3.12+.
- **macOS (Apple Silicon or Intel) or Linux.** On Apple Silicon you need a
  *native arm64* Python — the system `/usr/bin/python3` is perfect (see
  Troubleshooting for why).
- **~1.5 GB free disk** for the virtualenv (TensorFlow is a large install).
- `git`, to clone. The 42 MB model checkpoint ships in the repo.
- A pen plotter is **optional** — you can use Inkwell purely to generate
  handwriting SVGs.

## Setup (one time)

```bash
git clone https://github.com/artygracie/handwriting-studio.git
cd handwriting-studio
./setup.sh          # creates ./venv and installs deps (~1 GB download)
```

`setup.sh` finds a suitable Python, creates `./venv`, and installs
`requirements.txt`. If it can't find a usable interpreter, create the env
yourself:

```bash
python3.11 -m venv venv          # any Python 3.8–3.11
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

## Run

```bash
./run.sh            # serves http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>. The handwriting model loads on the **first render**
(~10–20 s the first time), then stays warm. (`run.sh` runs
`venv/bin/python server.py` — there's no auto-reload, so restart it after
editing `engine.py`/`server.py`.)

Smoke-test the engine without the UI:

```bash
./venv/bin/python smoke_test.py
```

## From note to plotted paper

1. Compose and style your note, then **Download G-code**.
2. Copy `inkwell-note.gcode` to the computer wired to your plotter and stream it
   (e.g. with [Universal G-code Sender](https://winder.github.io/ugs_website/)).
   It writes at the previewed millimetre size.

The G-code is millimetres (`G21`), absolute (`G90`), with GRBL servo pen-lift —
`M3 S<down>` to lower the pen, `M5` to lift, plus a short dwell so the servo
settles. It assumes the machine's origin is the **top-left** of the sheet with
+Y running *down* the page, and applies **no Y-flip**. ⚠️ **Verify this on your
machine first** — plot the word `top` on scrap. If it comes out upside-down,
your machine is bottom-left origin; flip Y in `gcode.py`. Use the in-app
**Plotter handoff** panel for the exact per-canvas specs and a pre-flight
checklist.

Prefer the SVG → vpype route instead? **Download SVG** still works:

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
server.py          FastAPI app (serves UI + /api/render + /api/gcode)
engine.py          sampling + caching + paper-aware fill layout → SVG
gcode.py           SVG → GRBL G-code (servo pen-lift)
papers.py          paper-size presets (mm)
static/            index.html · style.css · app.js
vendor/            otuva/handwriting-synthesis (model + 42 MB checkpoint, bundled)
requirements.txt · setup.sh · run.sh · smoke_test.py
```

## Tuning

- Text consistently a little large/small? Adjust `REF_GLYPH_UNITS` in
  `engine.py` (lower = bigger text). `MAX_FILL_MM` caps how large Fill page
  grows short notes.
- Plotter: tune the servo values, feed rate, and dwell in `gcode.py`.

## Troubleshooting

- **`Abort trap: 6` / the process is killed on launch (Apple Silicon).** You're
  using an x86_64 / Rosetta or conda Python. Intel TensorFlow needs AVX, which
  Rosetta can't emulate. Use a native arm64 Python (`/usr/bin/python3`);
  `setup.sh` tries to enforce this.
- **`pip` can't find TensorFlow / install fails.** You're likely on Python
  3.12+. Use 3.8–3.11.
- **First render is slow.** Normal — the model loads once, then stays warm.

## Credits

Handwriting synthesis model: [otuva/handwriting-synthesis](https://github.com/otuva/handwriting-synthesis),
a TensorFlow 2 port of Alex Graves,
[*Generating Sequences With Recurrent Neural Networks*](https://arxiv.org/abs/1308.0850).
The vendored model under `vendor/` retains its upstream license.
