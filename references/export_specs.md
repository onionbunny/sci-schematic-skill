# Export & Compliance Specs

## 1. Journal presets

The preset is selected in `figure.preset`. Values are a general baseline; always defer to the
journal's current author guide at submission.

| Preset | Single col | Double col | Max depth | Raster DPI | Min font | Min stroke |
|---|---|---|---|---|---|---|
| nature | 89 mm | 183 mm | 247 mm | 300 (line 600) | 5 pt | 0.25 pt |
| science | 55 mm | 120 mm | 235 mm | 300 (line 600) | 5 pt | 0.25 pt |
| cell | 90 mm | 180 mm | 240 mm | 300 (line 600) | 5 pt | 0.25 pt |
| plos | 89 mm | 183 mm | 240 mm | 300 | 6 pt | 0.3 pt |
| default_print | 120 mm | 180 mm | 250 mm | 300 | 6 pt | 0.3 pt |
| screen | 160 mm | 240 mm | 180 mm | 150 | 8 pt | 0.4 pt |

All presets use sRGB. Vector outputs (PDF/EPS/SVG) are resolution-independent, but any
embedded raster inside them must still meet the DPI floor.

## 2. Units and conversion

- Geometry is authored in millimetres.
- `mm_per_pt = 0.3527778`, `pt_per_mm = 2.8346457`; the 96-dpi reference is used only for
  pixel conversion.
- The renderer converts point font/stroke sizes to mm and writes unitless SVG numbers.
  Feeding absolute `pt` units into a mm-based viewBox causes a second scaling pass and
  grossly oversized text — do not do this.

## 3. Output formats

- **SVG** — the editable source: layered groups, real selectable text, markers in `<defs>`.
- **PDF** — vector, fonts embedded, page size matching the canvas mm.
- **PNG** — flattened RGB (no alpha), sRGB, DPI metadata written.
- **TIFF** — RGB, LZW compression, DPI metadata.
- **EPS** — where the backend supports it; otherwise the reportlab/vector path is used.

Raster exports are normalized: cairosvg's RGBA output is composited onto a white background
and converted to RGB so journals never receive an alpha, indexed, or CMYK file.

## 4. Backend ladder (auto-detected)

Run `scifig.py backends` to list what is available. Each export tries, in order:

1. **cairosvg** (Python; SVG→PDF/PNG)
2. **rsvg-convert** (system binary)
3. **inkscape** (system binary)
4. **reportlab fallback** — a built-in vector redraw for PDF when no SVG rasterizer exists

The backend that produced each file is recorded in the export report and `result.json`. If
the fallback is used, state it explicitly. Avoid ImageMagick `convert` for SVG: its SVG
delegate depends on an rsvg renderer that may be absent and can fail silently.

## 5. Compliance gate

`check` inspects each artifact and records pass/fail with details.

- **SVG**: text elements are present and selectable (not outlined); structure is well-formed.
- **PDF** (`pdfinfo` / `pdffonts`): page size matches the target mm; every font is
  embedded; a font list with embedding flags is returned.
- **PNG/TIFF** (Pillow): mode is exactly `RGB`; pixel dimensions equal
  `mm / 25.4 × dpi`; DPI metadata is present and at least the target; TIFF compression is
  reported (LZW). CMYK, palette ("P"), grayscale-alpha ("LA"), and RGBA are rejected.

A failed check is a real signal: correct the export or record the limitation; never relabel
a failing artifact as compliant.

## 6. Choosing formats for a case

- Mechanism/relationship figures for journals: editable SVG + vector PDF + 300-dpi PNG/TIFF.
- Editable requirement always pairs the source SVG with a rendered PDF/PNG preview.
- Screen-only or quick review: the `screen` preset at 150 dpi is sufficient and smaller.
