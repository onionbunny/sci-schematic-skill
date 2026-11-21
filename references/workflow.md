# End-to-End Workflow

A complete playbook with decision points. Read the other references when a stage points to
them; do not preload everything.

## Stage 0 — Understand the task

Read `/input/case.json` and `/input/task.md`. Note the work order (new figure vs edit),
the figure type, target journal/preset if named, and the requested formats. List the mounted
materials; never assume a file's content from its name.

## Stage 1 — Ingest

```bash
python3 $SKILL/scripts/scifig.py ingest --input /input --work /app/work
```

Outputs: `ingest_bundle.json` and `reading/`. PDF text is extracted, tables are normalized
to JSON, and an existing SVG is parsed into a seed with mm geometry. Read the bundle and the
reading files to learn the source ids and the actual claims.

Decision point: if a material cannot be parsed, record it; do not proceed as if it were
empty. Check whether the case is an edit (an SVG seed exists).

## Stage 2 — Extract (native reasoning)

Create a skeleton and fill it:

```bash
python3 $SKILL/scripts/scifig.py new --spec /app/work/spec.json --case-id <id>
```

Build entities, relationships, groups, datasets, legend, and annotations following
`extraction_guide.md`. Cite source ids on every element; preserve names and units; choose
relations by exact verb meaning; route hedged claims to dashed/indirect relations with
uncertainties. For data-driven figures, copy real values and declare the color mapping.

Decision points:
- Passive voice — keep causal direction (source = the actor).
- One sentence, two verbs — model two edges.
- Unknown direction — `modulation`, never a guess.
- Contradiction — cite both, lower confidence, add an uncertainty.

## Stage 3 — Validate

```bash
python3 $SKILL/scripts/scifig.py validate --spec /app/work/spec.json \
  --report /app/work/validation_report.json
```

Fix every error before continuing. Batch all corrections into one spec edit. Confirm
provenance coverage is 1.0 and the legend/relation/data checks are consistent.

## Stage 4 — Layout

```bash
python3 $SKILL/scripts/scifig.py layout --spec /app/work/spec.json
```

New figure: the hierarchical engine assigns ranks, ports, routes, and feedback lanes.
Edit: set `layout.engine = "manual"` and keep explicit coordinates. Review any layout
warnings (`node_overlap`, `canvas_overflow`, `container_overflow`,
`edge_label_collision`) and resolve or explain them.

## Stage 5 — Render, export, preflight (one command)

```bash
python3 $SKILL/scripts/scifig.py pipeline --spec /app/work/spec.json \
  --work /app/work --output /app/output --formats svg,pdf,png,tiff
```

The pipeline renders the layered editable SVG, runs the backend ladder for each format,
normalizes rasters to RGB with DPI, executes the compliance gate, and writes `result.json`.

Decision point: inspect the compliance report. A failed font-embedding or color-mode check
must be fixed and the pipeline re-run; a missing backend that triggers the reportlab
fallback is acceptable but must be visible in the report.

## Stage 6 — Edit tasks

Reuse the SVG seed, preserve ids and coordinates, apply only the requested change, and
append a `change_records` entry (element, reason, what was preserved). Do not restyle or
move unrelated elements.

## Stage 7 — Final verification

Before finishing, confirm:
1. `result.json` status matches reality and all artifact paths exist.
2. The editable SVG opens with selectable text and distinct layers.
3. PDF fonts are embedded; PNG/TIFF are RGB at the target DPI; TIFF is LZW.
4. Every element traces to a source; legend and data mapping have no missing entries.
5. Uncertainties and change records honestly reflect hedging and edits.

## Budget discipline

Run ingest once; spend model turns on scientific extraction and judgment; batch validation
fixes; let the deterministic pipeline handle geometry, export, and preflight so the limited
request and wall-clock budget is not consumed by redrawing.
