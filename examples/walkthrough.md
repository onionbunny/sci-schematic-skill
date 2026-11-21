# Minimal Walkthrough

This is a labeled, self-contained example. It is synthetic data used only to demonstrate the
pipeline; it is not a scientific result.

`example_spec.json` describes a three-node pathway grounded in one text source:

> "Kinase A activates protein B, and protein B inhibits the output gene C."

- Entities: `Kinase A` (enzyme, rounded), `Protein B` (protein, rounded), `Gene C`
  (gene, box). Each carries `source_refs: ["S1"]`.
- Relationships: `activation` (filled arrow, blue) A→B and `inhibition` (T-bar, orange)
  B→C. Direction is source → target.
- Legend lists both relations; the panel letter is "A".
- No positions are authored: the hierarchical engine computes them, so this is a clean
  pre-layout spec.

## Run it

Let `$SKILL` be the skill root.

```bash
python3 $SKILL/scripts/scifig.py validate \
  --spec $SKILL/examples/example_spec.json
python3 $SKILL/scripts/scifig.py pipeline \
  --spec $SKILL/examples/example_spec.json \
  --work /tmp/example_work --output /tmp/example_output \
  --formats svg,pdf,png,tiff
```

Expected: validation passes with 0 errors, layout reports 0 warnings, all four formats
export, compliance passes, and `result.json` reports `status: success`.

## What to inspect in the output

- `figure_min.svg` — open in a text editor or Illustrator/Inkscape: separate layers and
  selectable text labels.
- `figure_min.pdf` — vector page; `pdffonts` shows embedded fonts.
- `figure_min.png` / `figure_min.tiff` — RGB, 300 dpi; the T-bar stops just outside Gene C.
- `result.json` — provenance coverage 1.0, no missing legend relations, and the backend
  used for each format.

## Turning it into an edit exercise

Copy the spec, set `layout.engine` to `manual`, add explicit `position`/`size` to each
node (as produced by a layout run), change R2 from `inhibition` to `activation`, and append
a `change_records` entry. Re-running keeps every node in place while only the edge glyph
changes.
