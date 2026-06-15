"""Paper-size presets, in millimetres.

Every size is stored portrait (width <= height). Orientation is applied at
render time, so a single definition covers both portrait and landscape.
"""

# name -> (width_mm, height_mm)
PAPERS = {
    # ISO A series
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "A7": (74.0, 105.0),
    # US / imperial
    "US Letter": (215.9, 279.4),       # 8.5 x 11 in
    "Half Letter": (139.7, 215.9),     # 5.5 x 8.5 in
    # Common card / stationery sizes
    "5x7 Card": (127.0, 177.8),        # 5 x 7 in
    "4x6 Card": (101.6, 152.4),        # 4 x 6 in
    "A2 Card": (108.0, 139.7),         # 4.25 x 5.5 in (folded A2 note card)
    "Place Card": (88.9, 50.8),        # 3.5 x 2 in (tented place card, flat)
}

DEFAULT_PAPER = "A5"

# Sensible default margin per paper, mm. Falls back to GENERIC_MARGIN.
GENERIC_MARGIN = 18.0
PAPER_MARGINS = {
    "A7": 8.0,
    "Place Card": 6.0,
    "A2 Card": 10.0,
    "4x6 Card": 10.0,
    "5x7 Card": 12.0,
}


def paper_dimensions(name: str, orientation: str = "portrait"):
    """Return (width_mm, height_mm) for a preset, applying orientation."""
    w, h = PAPERS.get(name, PAPERS[DEFAULT_PAPER])
    if orientation == "landscape":
        return h, w
    return w, h


def default_margin(name: str) -> float:
    return PAPER_MARGINS.get(name, GENERIC_MARGIN)


def paper_catalog():
    """Serializable list for the UI."""
    out = []
    for name, (w, h) in PAPERS.items():
        out.append({
            "name": name,
            "width_mm": w,
            "height_mm": h,
            "default_margin": default_margin(name),
        })
    return out
