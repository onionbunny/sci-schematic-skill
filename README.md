# sci-schematic

A source-bound skill for generating and editing **scientific mechanism / relationship /
flow / data-driven schematics** with real editable sources and journal-compliant exports.

It turns scientific text, a PDF, data tables, a sketch, or an existing SVG into a figure a
reviewer cannot fault on traceability: every entity, directed relationship, value and unit
is bound to a source; activation arrows and inhibition T-bars keep their meaning and
direction; legend and data mapping stay consistent; and the editable source is a layered,
text-selectable SVG.

## Why it exists

Generic agents treat a mechanism diagram as a decorative illustration and fail in predictable
ways: invented gene names and units, inhibition drawn as activation, reversed up/downstream
order, legend colors that do not match the data, bitmap-only output with non-selectable text,
and exports that miss journal DPI / font-embedding / color-space requirements. This skill
makes those failures machine-detectable instead.

## Pipeline

```
ingest → extract (LLM scientific reading) → validate (anti-hallucination gate)
       → layout (hierarchical, ports, orthogonal routing, feedback lanes)
       → render layered editable SVG → export (multi-backend)
       → compliance preflight → result.json
```

- The spec JSON is the single source of truth; all geometry is in millimetres.
- Backend ladder: `cairosvg → rsvg-convert → inkscape → reportlab vector fallback`.
- Rasters are flattened to RGB with DPI metadata; TIFF uses LZW; PDF fonts are embedded.

## Repository layout

- `SKILL.md` — entry point and workflow (valid name/description frontmatter).
- `scripts/` — `scifig.py` CLI and the `sci_fig` package; `requirements.txt`.
- `assets/` — controlled relation/entity vocabularies, colorblind-safe palettes, presets.
- `references/` — extraction, graphics grammar, export specs, result contract, full workflow.
- `examples/` — a labeled minimal walkthrough (synthetic data, not a scientific result).

## Quickstart

```bash
python3 scripts/scifig.py ingest --input /input --work /app/work
python3 scripts/scifig.py pipeline --spec /app/work/spec.json \
  --work /app/work --output /app/output --formats svg,pdf,png,tiff
```

See `examples/walkthrough.md` for a self-contained run and `references/` for the details.

## Honesty policy

Elements not present in the source materials are never drawn. Hedged claims use dashed /
indirect relations and are listed as uncertainties; source-preserving edits keep ids and
coordinates and append change records. `result.json` reports an honest `success` /
`partial` / `failed` status and every machine check.
