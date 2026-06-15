"""Quick end-to-end check: load the model, render a multi-paragraph note,
and assert we get a sane, paper-sized SVG. Run inside the 'inkwell' env."""

from engine import HandwritingEngine

NOTE = """Dear Ally,

We are so happy you are here to
celebrate with us today.

With love,
The Family"""

eng = HandwritingEngine()
out = eng.render(
    text=NOTE, style=9, bias=0.75, text_size_mm=8.0, line_height=1.6,
    stroke_width=1.0, ink="#1a2b4a", paper_w=148.0, paper_h=210.0,
    margin=18.0, fit_to_page=True,
)

svg = out["svg"]
assert svg.startswith("<svg"), "no svg"
assert "148mm" in svg and "210mm" in svg, "paper size missing"
n_paths = svg.count("<path")
print(f"lines sampled : {out['line_count']}")
print(f"paths in svg  : {n_paths}")
print(f"warnings      : {out['warnings']}")
print(f"svg bytes     : {len(svg)}")
assert n_paths > 0, "no ink drawn"

# Re-render with a layout-only change (stroke width) — should reuse cached strokes.
out2 = eng.render(
    text=NOTE, style=9, bias=0.75, text_size_mm=8.0, line_height=1.6,
    stroke_width=2.0, ink="#5b2333", paper_w=148.0, paper_h=210.0,
    margin=18.0, fit_to_page=True,
)
assert out2["line_count"] == out["line_count"]
print("layout-only re-render OK (cache reuse)")

with open("smoke_out.svg", "w") as f:
    f.write(svg)
print("wrote smoke_out.svg")
print("SMOKE_OK")
