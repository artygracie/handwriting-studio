"""Handwriting engine.

Wraps the otuva/handwriting-synthesis RNN but bypasses its fixed-size `_draw`.
Instead we sample raw pen strokes once (cached per line) and lay them out
ourselves on a real paper canvas measured in millimetres, so paper size,
margins, line height, text size and stroke width are all controllable and
most of them re-render *without* re-running the neural net.

The layout pass (`layout()`) produces a single source of truth — a list of
polylines in millimetre page coordinates — which `to_svg()` turns into a
preview/download SVG. G-code export reads that SVG back in `gcode.py`.

Coordinate convention after `_process`:
  - each line is a list of polylines (pen-down segments)
  - points are (x, y) in raw model units, normalised so the line's top-left is (0, 0)
  - y increases downward (screen/SVG convention)

The millimetre page coordinates used by `layout()`/`to_svg()` keep that same
convention: origin at the top-left of the sheet, y downward.
"""

import os
import re
import sys
import threading

# --- locate and import the vendored model ------------------------------------
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(ENGINE_DIR, "vendor")

# The model's config.py uses relative paths ("model/checkpoint", "model/style"),
# so the process must run with VENDOR_DIR as the working directory.
sys.path.insert(0, VENDOR_DIR)
os.chdir(VENDOR_DIR)

from handwriting_synthesis import drawing                  # noqa: E402
from handwriting_synthesis.hand import Hand                 # noqa: E402

VALID_CHARS = set(drawing.alphabet)
NUM_STYLES = 13            # styles 0..12 ship with the model
MODEL_MAX_CHARS = 75       # hard limit per line enforced by the model

# Layout calibration constants (raw model units):
# a rendered line is ~25 units tall. Per-character width is measured per
# (style, bias) at run time — see `_raw_per_char` — instead of guessed, so
# word-wrap packs each line right up to the page width.
REF_GLYPH_UNITS = 25.0     # raw line height -> text_size_mm maps a line to this height
AVG_CHAR_RATIO = 0.30      # fallback char width (fraction of REF) if calibration fails
MAX_FILL_MM = 40.0         # ceiling on auto text size when filling the page

# Reference line for measuring per-character width (all in-alphabet, lowercase).
_CALIB_LINE = "the quick brown fox jumps over a lazy dog"

# Characters we can transliterate into the supported alphabet.
_TRANSLITERATE = {
    "‘": "'", "’": "'",            # ‘ ’ curly single quotes
    "“": '"', "”": '"',            # “ ” curly double quotes
    "–": "-", "—": "-", "‒": "-",  # – — ‒ dashes
    "…": "...",                          # … ellipsis
    " ": " ",                            # non-breaking space
    "\t": "    ",
    "&": "and",
    "/": " ",
    "*": "",
    "_": " ",
}
# Uppercase letters the model never learned -> lowercase fallback.
_CASE_FALLBACK = {"Q": "q", "X": "x", "Z": "z"}


def _fmt(v: float) -> str:
    """Trim trailing zeros so 148.0 -> '148', 215.9 -> '215.9'."""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def list_styles():
    return list(range(NUM_STYLES))


def sanitize_line(line: str):
    """Return (clean_line, dropped_chars set) for a single line."""
    out = []
    dropped = set()
    for ch in line:
        if ch in VALID_CHARS:
            out.append(ch)
            continue
        if ch in _TRANSLITERATE:
            out.append(_TRANSLITERATE[ch])
        elif ch in _CASE_FALLBACK:
            out.append(_CASE_FALLBACK[ch])
        else:
            dropped.add(ch)
    # Collapse any runs of spaces we may have introduced.
    clean = re.sub(r"[ ]{2,}", " ", "".join(out))
    return clean, dropped


def wrap_paragraph(text: str, max_chars: int):
    """Greedy word-wrap a single paragraph to <= max_chars per line."""
    max_chars = max(4, min(max_chars, MODEL_MAX_CHARS))
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], ""
    for word in words:
        # A single word longer than the limit must be hard-split.
        while len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        candidate = word if not cur else cur + " " + word
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# --- emitters: one geometry, two outputs -------------------------------------

def to_svg(geom, *, ink="#1a2b4a", stroke_width=0.7):
    """Render layout geometry to a millimetre-sized SVG string.

    Every stroke uses the same `stroke_width` (mm) and round caps/joins, so the
    line weight is uniform across the whole note — matching a single physical
    pen like the Zebra G-750 (0.7 mm)."""
    pw, ph = _fmt(geom["paper_w"]), _fmt(geom["paper_h"])
    paths = []
    for poly in geom["polylines"]:
        if not poly:
            continue
        d = []
        for j, (x, y) in enumerate(poly):
            d.append(f"{'M' if j == 0 else 'L'}{x:.2f},{y:.2f}")
        paths.append(" ".join(d))

    path_str = "".join(
        f'<path d="{d}" fill="none" stroke="{ink}" '
        f'stroke-width="{stroke_width:.2f}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>\n'
        for d in paths
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{pw}mm" height="{ph}mm" '
        f'viewBox="0 0 {pw} {ph}">\n'
        f'<rect x="0" y="0" width="{pw}" height="{ph}" fill="white"/>\n'
        f'{path_str}</svg>'
    )


class HandwritingEngine:
    def __init__(self):
        # Hand() restores the TF checkpoint; do it once and reuse.
        self.hand = Hand()
        self._lock = threading.Lock()       # TF session.run is not re-entrant
        self._cache = {}                    # (text, style, bias_q, version) -> processed line
        self._rpc = {}                      # (style, bias_q, version) -> raw units per char
        self._version = 0                   # bump to force fresh handwriting

    # -- sampling -------------------------------------------------------------
    def _process(self, offsets):
        """Convert raw RNN offsets into normalised polylines (see module docstring)."""
        coords = drawing.offsets_to_coords(offsets)
        coords = drawing.denoise(coords)
        coords[:, :2] = drawing.align(coords[:, :2])
        coords[:, 1] *= -1                       # flip so 'up' on paper is smaller y
        coords[:, :2] -= coords[:, :2].min(axis=0)  # normalise top-left to origin

        polylines, cur, prev_eos = [], [], 1.0
        for x, y, eos in coords:
            if prev_eos == 1.0:                  # pen was up -> start a new stroke
                if cur:
                    polylines.append(cur)
                cur = [(float(x), float(y))]
            else:
                cur.append((float(x), float(y)))
            prev_eos = eos
        if cur:
            polylines.append(cur)

        xs = coords[:, 0]
        ys = coords[:, 1]
        return {
            "polylines": polylines,
            "width": float(xs.max()) if len(xs) else 0.0,
            "height": float(ys.max()) if len(ys) else 0.0,
        }

    def _sample_lines(self, specs):
        """specs: list of (text, style, bias). Returns processed dict per spec,
        sampling only what isn't cached. Cache key includes self._version."""
        results = [None] * len(specs)
        todo = []                                # (index, text, style, bias)
        for i, (text, style, bias) in enumerate(specs):
            key = (text, int(style), round(float(bias), 2), self._version)
            if key in self._cache:
                results[i] = self._cache[key]
            else:
                todo.append((i, text, style, bias, key))

        if todo:
            lines = [t[1] for t in todo]
            styles = [int(t[2]) for t in todo]
            biases = [float(t[3]) for t in todo]
            with self._lock:
                strokes = self.hand._sample(lines, biases=biases, styles=styles)
            for (i, text, style, bias, key), offs in zip(todo, strokes):
                processed = self._process(offs)
                self._cache[key] = processed
                results[i] = processed
        return results

    def _raw_per_char(self, style, bias):
        """Average glyph width in raw model units for a (style, bias), measured
        from a reference line and cached. Used to word-wrap each line right up
        to the page width instead of guessing with a fixed ratio."""
        key = (int(style), round(float(bias), 2), self._version)
        if key not in self._rpc:
            proc = self._sample_lines([(_CALIB_LINE, style, bias)])[0]
            width = proc["width"]
            rpc = width / len(_CALIB_LINE) if width > 0 else AVG_CHAR_RATIO * REF_GLYPH_UNITS
            self._rpc[key] = rpc
        return self._rpc[key]

    def shuffle(self):
        """Force the next render to produce new handwriting variations."""
        self._version += 1

    # -- layout: text -> polylines in millimetre page coordinates -------------
    def layout(self, *, text, style=9, bias=0.75, text_size_mm=8.0,
               line_height=1.6, paper_w=148.0, paper_h=210.0,
               margin=18.0, fit_to_page=True):
        """Return {polylines, warnings, line_count, overflow, paper_w, paper_h,
        margin}. `polylines` is a list of strokes, each a list of (x, y) points
        in millimetres with the origin at the top-left of the sheet."""
        warnings = []
        dropped_all = set()

        text_area_w = max(10.0, paper_w - 2 * margin)
        text_area_h = max(10.0, paper_h - 2 * margin)

        # Sanitize once into "blocks": None marks a blank line (paragraph gap),
        # otherwise a cleaned hard line to be word-wrapped.
        blocks = []
        for raw in text.replace("\r\n", "\n").split("\n"):
            clean, dropped = sanitize_line(raw)
            dropped_all |= dropped
            blocks.append(None if clean.strip() == "" else clean)

        if dropped_all:
            warnings.append(
                "Unsupported characters skipped: "
                + " ".join(sorted(repr(c) for c in dropped_all))
            )

        rpc = self._raw_per_char(style, bias)        # raw units per character

        def char_mm(E):
            return max(0.4, rpc * (E / REF_GLYPH_UNITS))

        def est_max_chars(E):
            return max(4, min(MODEL_MAX_CHARS, int(text_area_w / char_mm(E))))

        # Build the layout (None | text) by wrapping each block at max_chars.
        def build_layout(max_chars):
            out = []
            for b in blocks:
                if b is None:
                    out.append(None)
                else:
                    out.extend(wrap_paragraph(b, max_chars))
            return out

        # Fill the page: pick the wrap width that lets the text be as large as
        # possible while still fitting BOTH the text-area width and height.
        # Wider wrapping -> fewer, longer lines (taller text, limited by width);
        # narrower wrapping -> more, shorter lines (limited by height). The best
        # width maximises the achievable scale. Pure string maths given a
        # per-character width `cw` (raw units), so we can scan every candidate
        # cheaply.
        def scan_fill(cw):
            best = None  # (scale, wrap_chars)
            for w in range(4, MODEL_MAX_CHARS + 1):
                rows = build_layout(w)
                line_lens = [len(ln) for ln in rows if ln]
                if not line_lens:
                    continue
                longest = max(line_lens)
                n_rows = len(rows)               # blank lines count as a row
                s_w = text_area_w / (longest * cw)
                raw_h = (n_rows - 1) * REF_GLYPH_UNITS * line_height + REF_GLYPH_UNITS
                s_h = text_area_h / raw_h
                scale = min(s_w, s_h)
                if best is None or scale > best[0]:
                    best = (scale, w)
            return best

        # Choose the text size E (mm) and the wrap width (chars/line).
        if fit_to_page:
            best = scan_fill(rpc)
            if best is None:
                E, max_chars = text_size_mm, est_max_chars(text_size_mm)
            else:
                # The generic `rpc` (a pangram average) can be 10-15% off for a
                # given hand, which makes the scan wrap too narrow and leaves the
                # right margin unused. Re-measure the per-character width from
                # THIS note's actual strokes and re-scan, so lines pack right up
                # to the margin and the text grows to its true maximum.
                probe = build_layout(best[1])
                probe_lines = [ln for ln in probe if ln is not None]
                probe_proc = (self._sample_lines([(ln, style, bias) for ln in probe_lines])
                              if probe_lines else [])
                probe_chars = sum(len(ln) for ln in probe_lines)
                if probe_chars > 0 and probe_proc:
                    cw_note = sum(p["width"] for p in probe_proc) / probe_chars
                    best = scan_fill(cw_note) or best
                E = min(MAX_FILL_MM, best[0] * REF_GLYPH_UNITS)
                max_chars = best[1]
        else:
            E = text_size_mm
            max_chars = est_max_chars(E)

        # Build + sample the final layout once, at the chosen size.
        layout = build_layout(max_chars)
        specs = [(ln, style, bias) for ln in layout if ln is not None]
        processed = self._sample_lines(specs) if specs else []
        pi = iter(processed)
        rendered = [None if ln is None else next(pi) for ln in layout]

        # Measure actual content at size E.
        s = E / REF_GLYPH_UNITS                              # mm per raw unit
        gap = E * line_height
        content_w = content_h = 0.0
        for i, line in enumerate(rendered):
            top = i * gap
            if line is None:
                content_h = max(content_h, top)
                continue
            content_w = max(content_w, line["width"] * s)
            content_h = max(content_h, top + line["height"] * s)

        # Safety clamp from measured size (never enlarges) so a wrap estimate
        # that ran a touch wide can't push ink past the margins.
        if content_w > 0 and content_h > 0:
            if fit_to_page:
                clamp = min(1.0, text_area_w / content_w, text_area_h / content_h)
            else:
                # Width-only: keep the requested size but never run off the right.
                clamp = min(1.0, text_area_w / content_w)
        else:
            clamp = 1.0

        overflow = (not fit_to_page) and (content_h * clamp > text_area_h + 0.5)
        if overflow:
            warnings.append(
                "The note is taller than the page — turn on Fill page, "
                "use a larger paper, or shorten the text."
            )

        scale = s * clamp
        polylines = []     # list of strokes, each [(x_mm, y_mm), ...]
        for i, line in enumerate(rendered):
            if line is None:
                continue
            y_origin = margin + (i * gap) * clamp
            for poly in line["polylines"]:
                if not poly:
                    continue
                pts = [(margin + x * scale, y_origin + y * scale) for (x, y) in poly]
                polylines.append(pts)

        # Ink bounding box (mm, page coords) so callers can verify the note sits
        # inside the paper / margins before plotting.
        bbox = None
        if polylines:
            all_pts = [p for poly in polylines for p in poly]
            xs = [p[0] for p in all_pts]
            ys = [p[1] for p in all_pts]
            bbox = [min(xs), min(ys), max(xs), max(ys)]

        return {
            "polylines": polylines,
            "warnings": warnings,
            "line_count": len(specs),
            "overflow": overflow,
            "paper_w": paper_w,
            "paper_h": paper_h,
            "margin": margin,
            "bbox": bbox,
        }

    # -- public render (SVG) --------------------------------------------------
    def render(self, *, text, style=9, bias=0.75, text_size_mm=8.0,
               line_height=1.6, stroke_width=0.7, ink="#1a2b4a",
               paper_w=148.0, paper_h=210.0, margin=18.0, fit_to_page=True):
        """Return a dict: {svg, warnings, line_count, overflow, paper_*, margin}."""
        geom = self.layout(
            text=text, style=style, bias=bias, text_size_mm=text_size_mm,
            line_height=line_height, paper_w=paper_w, paper_h=paper_h,
            margin=margin, fit_to_page=fit_to_page,
        )
        return {
            "svg": to_svg(geom, ink=ink, stroke_width=stroke_width),
            "warnings": geom["warnings"],
            "line_count": geom["line_count"],
            "overflow": geom["overflow"],
            "paper_w": geom["paper_w"],
            "paper_h": geom["paper_h"],
            "margin": geom["margin"],
            "bbox": geom["bbox"],
        }
