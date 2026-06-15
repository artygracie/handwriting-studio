const $ = (id) => document.getElementById(id);

const state = {
  text: "",
  style: 9, bias: 0.75, text_size_mm: 8, line_height: 1.6,
  stroke_width: 0.7, ink: "#1a2b4a",
  paper: "A5", orientation: "portrait", margin: 18, fit_to_page: true,
};

// G-code conventions emitted by gcode.py — kept here for the handoff panel.
const GCODE = {
  units: "mm (G21), absolute (G90)",
  origin: "paper top-left, +X right, +Y down (NO flip applied — verify on machine)",
  scale: "1 G-code unit = 1 mm (machine must be calibrated: $100/$101 steps/mm)",
  penDown: "M3 S60", penUp: "M5", dwell: "0.15 s", feed: 3000,
};

let papersById = {};

// ---- boot: load options ----
async function boot() {
  const opt = await fetch("/api/options").then(r => r.json());
  const sel = $("paper");
  opt.papers.forEach(p => {
    papersById[p.name] = p;
    const o = document.createElement("option");
    o.value = p.name;
    o.textContent = `${p.name} · ${p.width_mm}×${p.height_mm} mm`;
    sel.appendChild(o);
  });
  state.paper = opt.default_paper;
  sel.value = state.paper;
  applyPaperMargin();
  render(true);
}

function applyPaperMargin() {
  const p = papersById[state.paper];
  if (p) {
    state.margin = p.default_margin;
    $("margin").value = p.default_margin;
    $("marginVal").textContent = `${p.default_margin} mm`;
  }
}

// ---- debounced render ----
let timer = null, inFlight = false, queued = false;
function schedule(immediate = false) {
  clearTimeout(timer);
  timer = setTimeout(() => render(), immediate ? 0 : 280);
}

async function render(force = false) {
  if (inFlight) { queued = true; return; }
  inFlight = true;
  setStatus("Writing…", true);
  const body = { ...state, shuffle: force && shuffleNext };
  shuffleNext = false;
  try {
    const res = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) { setStatus("Error: " + data.error, false, true); return; }
    paint(data);
    setStatus("Ready");
  } catch (e) {
    setStatus("Error: " + e.message, false, true);
  } finally {
    inFlight = false;
    if (queued) { queued = false; render(); }
  }
}

function paint(data) {
  $("preview").innerHTML = data.svg;
  // size the paper element to the real aspect ratio
  const wrap = $("paperWrap");
  const ratio = data.paper_w / data.paper_h;
  const maxH = Math.min(window.innerHeight * 0.78, 900);
  wrap.style.height = maxH + "px";
  wrap.style.width = maxH * ratio + "px";
  // margin guide (as a fraction of displayed size)
  const mgFrac = data.margin / data.paper_w;
  $("guide").style.margin = (mgFrac * maxH * ratio) + "px";
  $("meta").textContent =
    `${data.paper_w}×${data.paper_h} mm · ${data.line_count} line${data.line_count === 1 ? "" : "s"}`;
  const w = $("warnings");
  w.innerHTML = "";
  (data.warnings || []).forEach(msg => {
    const d = document.createElement("div");
    d.textContent = msg;
    w.appendChild(d);
  });
  updateHandoff(data);
  lastData = data;
  lastSVG = data.svg;
}

// ---- plotter handoff panel ----
const r1 = (n) => Math.round(n * 10) / 10;

// Returns { label, cls } describing how the ink sits within the sheet.
function fitVerdict(data) {
  const b = data.bbox;
  if (!b) return { label: "no ink yet", cls: "" };
  const [minx, miny, maxx, maxy] = b;
  const W = data.paper_w, H = data.paper_h, m = data.margin, t = 0.5;
  if (minx < -t || miny < -t || maxx > W + t || maxy > H + t)
    return { label: "NO — runs off the paper", cls: "bad" };
  const insideMargins =
    minx >= m - t && miny >= m - t && maxx <= W - m + t && maxy <= H - m + t;
  if (insideMargins) return { label: "yes — inside margins", cls: "good" };
  return { label: "on paper, but past a margin", cls: "" };
}

function canvasFacts(data) {
  const orient = state.orientation === "landscape" ? "landscape" : "portrait";
  const W = data.paper_w, H = data.paper_h, m = data.margin;
  const b = data.bbox;
  return {
    paper: state.paper,
    size: `${W} × ${H} mm`,
    orient,
    margin: `${m} mm`,
    area: `${r1(W - 2 * m)} × ${r1(H - 2 * m)} mm`,
    bounds: b
      ? `X ${r1(b[0])}–${r1(b[2])} · Y ${r1(b[1])}–${r1(b[3])} mm`
      : "—",
    fit: fitVerdict(data),
    lines: data.line_count,
  };
}

function updateHandoff(data) {
  const f = canvasFacts(data);
  $("hoPaper").textContent = f.paper;
  $("hoSize").textContent = f.size;
  $("hoOrient").textContent = f.orient;
  $("hoMargin").textContent = f.margin;
  $("hoArea").textContent = f.area;
  $("hoBounds").textContent = f.bounds;
  const fits = $("hoFits");
  fits.textContent = f.fit.label;
  fits.className = f.fit.cls;
}

function buildHandoffText(data) {
  const f = canvasFacts(data);
  return `INKWELL → BACHIN T-A4 PLOTTING HANDOFF
=========================================

MACHINE (static)
- Machine:   Bachin Draw T-A4 · GRBL board · servo pen-lift
- Units:     ${GCODE.units}
- Origin:    ${GCODE.origin}
- Scale:     ${GCODE.scale}
- Pen:       Zebra G-750, 0.7 mm medium (single consistent line weight)
- Pen down:  ${GCODE.penDown}   Pen up: ${GCODE.penUp}   Servo dwell: ${GCODE.dwell}
- Feed:      ${GCODE.feed} mm/min in the file — START at 1000–1500 for crisp text
- Files:     *.svg = visual master (size in mm in the header); *.gcode = stream this

THIS CANVAS (live)
- Paper:        ${f.paper} (${f.orient})
- Sheet size:   ${f.size}
- Margin:       ${f.margin}
- Text area:    ${f.area}
- Ink bounds:   ${f.bounds}
- Strokes/lines:${" "}${f.lines}
- Fits page:    ${f.fit.label}

PRE-FLIGHT (do in order)
1. ORIENTATION TEST — plot the word "top" (or an L) on scrap. If it prints
   upside-down / bottom-to-top, the machine is bottom-left origin: apply
   Y_machine = ${f.size.split(" × ")[1].replace(" mm", "")} - Y_file to every Y. The file assumes top-left, no flip.
2. CALIBRATE — confirm commanded 100 mm measures 100 mm ($100/$101 steps/mm).
3. SERVO — confirm ${GCODE.penDown} actually presses the pen and ${GCODE.penUp} lifts it cleanly
   (tune the S value if not; ensure $32 laser-mode = 0).
4. ORIGIN — jog the pen to the paper's origin corner and zero there. Paper square to axes.
5. BOUNDS — refuse to run if any coordinate is < 0 or exceeds the sheet size
   (${f.size}). Ink should sit within the text area above.
6. FEED — start slow, raise only if lines stay sharp. Dry-run with pen up first.`;
}

let lastData = null;

let lastSVG = "";
function setStatus(msg, busy = false, error = false) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status" + (busy ? " busy" : "");
  if (error) s.style.color = "#a23";
  else s.style.color = "";
}

// ---- wire controls ----
function bindRange(id, key, fmt, immediate = false) {
  const el = $(id);
  el.addEventListener("input", () => {
    state[key] = parseFloat(el.value);
    const lbl = $(fmt.valId);
    if (lbl) lbl.textContent = fmt.fn(el.value);
    schedule(immediate);
  });
}

let shuffleNext = false;

function init() {
  $("text").addEventListener("input", e => { state.text = e.target.value; schedule(); });

  bindRange("style", "style", { valId: "styleVal", fn: v => v });
  bindRange("bias", "bias", { valId: "biasVal", fn: v => parseFloat(v).toFixed(2) });
  bindRange("size", "text_size_mm", { valId: "sizeVal", fn: v => `${parseFloat(v).toFixed(1)} mm` });
  bindRange("lineHeight", "line_height", { valId: "lhVal", fn: v => `${parseFloat(v).toFixed(1)}×` });
  bindRange("stroke", "stroke_width", { valId: "strokeVal", fn: v => `${parseFloat(v).toFixed(2)} mm` });
  bindRange("margin", "margin", { valId: "marginVal", fn: v => `${v} mm` });

  // Pen-tip presets set a real ballpoint-style stroke width (mm).
  $("pens").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    [...e.currentTarget.children].forEach(c => c.classList.remove("active"));
    b.classList.add("active");
    state.stroke_width = parseFloat(b.dataset.w);
    $("stroke").value = b.dataset.w;
    $("strokeVal").textContent = `${parseFloat(b.dataset.w).toFixed(2)} mm`;
    schedule(true);  // stroke is layout-only → instant
  });
  // Dragging the slider de-selects the preset chips.
  $("stroke").addEventListener("input", () =>
    document.querySelectorAll("#pens button").forEach(c => c.classList.remove("active")));

  $("fit").addEventListener("change", e => { state.fit_to_page = e.target.checked; schedule(true); });

  $("paper").addEventListener("change", e => {
    state.paper = e.target.value;
    applyPaperMargin();
    schedule(true);
  });

  $("orient").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    [...e.currentTarget.children].forEach(c => c.classList.remove("active"));
    b.classList.add("active");
    state.orientation = b.dataset.o;
    schedule(true);
  });

  $("swatches").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    document.querySelectorAll("#swatches button").forEach(c => c.classList.remove("active"));
    b.classList.add("active");
    state.ink = b.dataset.ink;
    $("inkCustom").value = b.dataset.ink;
    schedule(true);
  });
  $("inkCustom").addEventListener("input", e => {
    state.ink = e.target.value;
    document.querySelectorAll("#swatches button").forEach(c => c.classList.remove("active"));
    schedule(true);
  });

  $("shuffle").addEventListener("click", () => { shuffleNext = true; render(true); });

  $("copyHandoff").addEventListener("click", async () => {
    if (!lastData) return;
    const btn = $("copyHandoff");
    const text = buildHandoffText(lastData);
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied ✓";
    } catch {
      // Clipboard API needs a secure context; fall back to a manual selection.
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); btn.textContent = "Copied ✓"; }
      catch { btn.textContent = "Copy failed — select & ⌘C"; }
      document.body.removeChild(ta);
    }
    setTimeout(() => { btn.textContent = "Copy full handoff for robot agent"; }, 1800);
  });

  $("download").addEventListener("click", () => {
    if (!lastSVG) return;
    const blob = new Blob([lastSVG], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "inkwell-note.svg";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  $("downloadGcode").addEventListener("click", async () => {
    if (!lastSVG) return;
    const btn = $("downloadGcode");
    btn.textContent = "Generating…";
    btn.disabled = true;
    try {
      const res = await fetch("/api/gcode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ svg: lastSVG }),
      });
      if (!res.ok) throw new Error(await res.text());
      const gc = await res.text();
      const blob = new Blob([gc], { type: "text/plain" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "inkwell-note.gcode";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("G-code error: " + e.message);
    } finally {
      btn.textContent = "Download G-code";
      btn.disabled = false;
    }
  });
}

init();
boot();
