"""Inkwell — local handwriting studio.

Serves a single-page UI and a small JSON API around the handwriting engine.
The TensorFlow model is loaded once at startup and reused for every request.
"""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import papers
from engine import HandwritingEngine, list_styles
from gcode import svg_to_gcode

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")

app = FastAPI(title="Inkwell")

# The engine loads the TF checkpoint — do it once, lazily, on first use so the
# server can boot instantly and report load progress.
_engine = None


def engine() -> HandwritingEngine:
    global _engine
    if _engine is None:
        print("Loading handwriting model (first request only)…", flush=True)
        _engine = HandwritingEngine()
        print("Model ready.", flush=True)
    return _engine


class GcodeRequest(BaseModel):
    svg: str
    feed_mm_min: int = 3000
    pen_down_s: int = 60


class RenderRequest(BaseModel):
    text: str = ""
    style: int = 9
    bias: float = 0.75            # "legibility": higher = neater
    text_size_mm: float = 8.0
    line_height: float = 1.6
    stroke_width: float = 0.7      # Zebra G-750, medium 0.7 mm — one consistent weight
    ink: str = "#1a2b4a"
    paper: str = papers.DEFAULT_PAPER
    orientation: str = "portrait"
    margin: float = 18.0
    fit_to_page: bool = True
    shuffle: bool = False         # bump variation before rendering


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/options")
def options():
    return {
        "papers": papers.paper_catalog(),
        "styles": list_styles(),
        "default_paper": papers.DEFAULT_PAPER,
    }


@app.post("/api/render")
def render(req: RenderRequest):
    eng = engine()
    if req.shuffle:
        eng.shuffle()
    w, h = papers.paper_dimensions(req.paper, req.orientation)
    try:
        result = eng.render(
            text=req.text,
            style=req.style,
            bias=req.bias,
            text_size_mm=req.text_size_mm,
            line_height=req.line_height,
            stroke_width=req.stroke_width,
            ink=req.ink,
            paper_w=w,
            paper_h=h,
            margin=req.margin,
            fit_to_page=req.fit_to_page,
        )
    except Exception as exc:  # surface model/layout errors to the UI
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return result


@app.post("/api/gcode")
def gcode(req: GcodeRequest):
    try:
        gc = svg_to_gcode(req.svg, feed_mm_min=req.feed_mm_min, pen_down_s=req.pen_down_s)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return PlainTextResponse(gc, media_type="text/plain")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    # Single worker: the TF session is shared and guarded by a lock.
    uvicorn.run(app, host="127.0.0.1", port=8000, workers=1)
