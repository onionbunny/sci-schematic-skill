---
name: sci-schematic
description: >-
  Source-bound scientific schematic / mechanism / flow / relationship figure generation and
  editing with editable source files and journal-compliant exports. Use whenever the task asks
  to turn scientific text, a PDF, data tables, a sketch or an existing SVG into a publication
  figure (mechanism diagram, pathway/relationship schematic, process flow, or data-driven
  schematic), to edit an existing figure while preserving its source, or to export and
  preflight figures for journals (SVG/PDF/PNG/TIFF). It extracts entities and directed
  relationships, enforces provenance and legend/data consistency, and delivers layered,
  text-selectable editable sources plus rendered previews and an honest result.json.
---

# Scientific Schematic Generation & Editing

## What this skill guarantees

Every scientific element is **traceable to a source**; relationships keep their direction and
glyph (activation arrow vs inhibition T-bar); legend and data mapping stay consistent; the
editable source is a layered, text-selectable SVG; and exports are preflighted against the
target preset. Never invent a gene, concentration, time point, unit, or relationship that is
not in the materials. When the source is silent or ambiguous, record an uncertainty instead.

## Layout of this skill

- `scripts/scifig.py` — single CLI entry (the `sci_fig` package sits beside it).
- `assets/` — controlled vocabularies, colorblind-safe palettes, journal presets.
- `references/` — detailed guides; read the file matching the current stage, not all at once.
- `examples/` — one labeled minimal walkthrough.

## Core pipeline (follow in order)

Let `$SKILL` be this folder. Prefix every command with `python3 $SKILL/scripts/scifig.py`.

### 1. Ingest the real inputs

Runtime inputs are `case.json` and `task.md` plus mounted materials. Read the actual files;
do not assume content from filenames.

```bash
python3 $SKILL/scripts/scifig.py ingest --input /input --work /app/work
```

This writes `/app/work/ingest_bundle.json` and human-readable files under
`/app/work/reading/` (extracted text, normalized tables, SVG seed). Read `task.md` and the
bundle to learn the source ids (`S1`, `S2`, …) that all `source_refs` must point to.

### 2. Extract the entity-relationship manifest (the scientific step)

This is native reasoning, not a script. Build a figure spec by filling a JSON skeleton
(`scifig.py new --spec /app/work/spec.json`). For every element, cite sources.

- **entities**: `id`, `label`, controlled `type` (see `assets/entity_vocab.json`),
  `source_refs`, and `confidence`.
- **relationships**: `source`, `target`, controlled `relation`
  (`assets/relation_vocab.json`), `source_refs`. Direction is always source → target.
- **groups**: compartments and their members; an entity belongs to at most one group.
- **datasets / legend**: when data drives colors, copy the real columns/rows and declare
  the mapping (see `references/extraction_guide.md`).

Apply the anti-hallucination rules in `references/extraction_guide.md`. Match the
relation to the exact verb meaning (inhibits → T-bar, not arrow). Keep names and units
verbatim. If a claim is hedged ("may regulate"), use the dashed/indirect relation, lower
confidence, and add an `uncertainties` entry.

### 3. Validate — fix every error before continuing

```bash
python3 $SKILL/scripts/scifig.py validate --spec /app/work/spec.json \
  --report /app/work/validation_report.json
```

Exit code 0 = pass. On errors, edit the spec and re-run; batch all fixes into one edit to
save requests. Warnings are allowed but each should be explained in `uncertainties`.
Provenance coverage must be 1.0.

### 4. Layout, then render the editable SVG

```bash
python3 $SKILL/scripts/scifig.py layout --spec /app/work/spec.json
```

The hierarchical engine assigns ranks, distributes ports, routes orthogonal edges, places
the legend and annotations, and writes coordinates back. For an **edit** task that must
keep coordinates, set `layout.engine = "manual"` (see below).

### 5. Export and preflight

```bash
python3 $SKILL/scripts/scifig.py pipeline --spec /app/work/spec.json \
  --work /app/work --output /app/output --formats svg,pdf,png,tiff
```

`pipeline` runs validate → layout → render → export → compliance → `result.json`. Backends
are auto-detected and degrade honestly (cairosvg → rsvg/inkscape → reportlab fallback);
the raster is flattened to RGB with DPI metadata. The compliance gate checks page size,
embedded fonts, RGB/sRGB, pixel dimensions, DPI, and that SVG text is still selectable.

If the harness only needs a subset, call `render`, `export`, or `check` individually.

## Editing an existing figure (source-preserving)

1. `ingest` parses the supplied SVG into a seed (labels, nodes, edges, mm geometry).
2. Recreate the spec keeping the **same ids, labels, and explicit positions/sizes**; set
   `layout.engine = "manual"` so coordinates are preserved.
3. Apply only the requested change (e.g. switch a relation from `activation` to
   `inhibition`; the renderer swaps the marker automatically).
4. Append a `change_records` entry stating element, reason, and what was preserved.
Do not restyle or move unrelated elements.

## Output contract

Each case returns `result.json` with `case_id`, honest `status` (`success` / `partial` /
`failed`), counts, artifact paths (editable SVG source, spec, exports, PNG previews),
per-element provenance, legend/data mapping check, uncertainties, change records, and all
machine checks. Field details: `references/result_contract.md`. Editable diagrams always
ship with a rendered PDF/PNG preview. A partial result must identify its limits.

## Exception handling

- Missing/contradictory material, or legend vs data mismatch: the validator reports a
  code; fix the spec or record the conflict. Never silently guess.
- Missing font: keep the preset family (Liberation Sans is metric-compatible with Arial);
  do not substitute an exotic font. Record any substitution.
- Export backend missing: the CLI falls down the backend ladder and records which backend
  produced each file; if only the reportlab fallback works, say so explicitly.
- Runtime failure: save an honest partial result early; mark failed formats and the reason.

## Budget discipline

The execution budget is limited (model requests and wall-clock). Run `ingest` once, batch
validation fixes into as few edits as possible, and prefer `pipeline` for the deterministic
stages so model turns are spent on scientific extraction and judgment, not on redrawing.

## When to read references

- `references/extraction_guide.md` — provenance rules, relation direction, trigger words,
  contradiction handling (read during step 2).
- `references/graphics_grammar.md` — glyph catalog, layers, layout and legend rules.
- `references/export_specs.md` — journal presets, DPI/color/font rules, backend ladder.
- `references/result_contract.md` — exact `result.json` fields.
- `references/workflow.md` — full stage playbook and worked decision points.
