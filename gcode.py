"""Convert an Inkwell SVG to G-code for the Bachin Draw T-A4 (GRBL, servo pen-lift).

Coordinate mapping
------------------
SVG origin is top-left, Y increasing downward.
The Bachin T-A4 homes at top-left; X increases right, Y increases away from the
operator (down the page), so no axis flip is needed — SVG X/Y maps directly to
machine X/Y.

Pen-lift mechanism
------------------
The T-A4 uses a servo on the Z-axis output.
  M3 S{down_s}  — servo on, pen touches paper
  M5            — servo off, pen lifts

Tune `pen_down_s`, `pen_up_s` (spindle-speed values 0-1000) and `feed_mm_min`
to match your servo and preferred writing speed.
"""

import re

# G-code preamble / postamble templates
_PREAMBLE = """\
; Inkwell G-code — Bachin Draw T-A4
; Feed: {feed} mm/min  Pen-down S: {pen_down_s}
G21          ; millimetres
G90          ; absolute positioning
G0 X0 Y0    ; go home
"""

_POSTAMBLE = """\
M5           ; pen up
G0 X0 Y0    ; return home
M2           ; end program
"""

# Split an SVG path data string into (command, x, y) tuples.
# Our paths only contain M and L; nothing else is emitted by engine.py.
_CMD_RE = re.compile(r"([ML])([\d.]+),([\d.]+)")


def svg_to_gcode(
    svg: str,
    feed_mm_min: int = 3000,
    pen_down_s: int = 60,
    pen_up_delay_ms: int = 150,
    pen_down_delay_ms: int = 150,
) -> str:
    """Return a G-code string for the given SVG text."""
    # Collect all path d="..." strings.
    paths = re.findall(r'd="([^"]+)"', svg)

    lines = [_PREAMBLE.format(feed=feed_mm_min, pen_down_s=pen_down_s)]
    pen_is_down = False

    def lift():
        nonlocal pen_is_down
        if pen_is_down:
            lines.append("M5")
            if pen_up_delay_ms:
                lines.append(f"G4 P{pen_up_delay_ms / 1000:.3f}   ; wait for servo")
            pen_is_down = False

    def lower():
        nonlocal pen_is_down
        if not pen_is_down:
            lines.append(f"M3 S{pen_down_s}")
            if pen_down_delay_ms:
                lines.append(f"G4 P{pen_down_delay_ms / 1000:.3f}   ; wait for servo")
            pen_is_down = True

    for path_d in paths:
        cmds = _CMD_RE.findall(path_d)
        if not cmds:
            continue
        for cmd, xs, ys in cmds:
            x, y = float(xs), float(ys)
            if cmd == "M":
                lift()
                lines.append(f"G0 X{x:.3f} Y{y:.3f}")
                lower()
            else:  # L
                lines.append(f"G1 F{feed_mm_min} X{x:.3f} Y{y:.3f}")

    lift()
    lines.append(_POSTAMBLE)
    return "\n".join(lines)
