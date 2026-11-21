# Result Contract

Every case returns one `result.json` at the output root. It is an honest machine-readable
record, not a marketing summary. Paths are relative to the output directory.

## Top-level fields

| Field | Meaning |
|---|---|
| `case_id` | id from the input case |
| `status` | `success`, `partial`, or `failed` (see decision rules) |
| `schema_version` | spec/result schema version |
| `figure_id`, `figure_type` | which figure and its kind (mechanism / flow / data-driven / edit) |
| `summary` | counts and provenance coverage |
| `artifacts` | editable source, spec, exports, previews |
| `provenance` | per-element source binding |
| `legend_mapping_check` | legend/relation/data consistency |
| `uncertainties` | hedged or unresolved items |
| `change_records` | edit history (empty for a new figure) |
| `checks` | validation, layout, export backends, compliance |
| `notes`, `generated_at` | provenance statement and UTC timestamp |

## status decision rules

- `failed` — validation did not pass, or no format exported successfully.
- `partial` — validation passed and at least one format exists, but compliance failed or not
  every requested format was produced. The failing items and reasons are listed.
- `success` — validation passed, all requested formats exported, and compliance passed.

## artifacts

- `editable_source`: the SVG with `text_selectable: true`, `layered: true`, and the ordered
  layer list (`layer-compartments`, `layer-relationships`, `layer-entities`,
  `layer-legend`, `layer-annotations`).
- `spec`: the validated JSON spec.
- `exports`: non-PNG files; each entry has `format`, `path`, `backend`, `ok`, and an
  optional `error` / `dpi`.
- `previews`: PNG entries (same shape as exports).

## provenance

- `sources`: registry with id, kind, path, name.
- `elements`: one row per entity, relationship, and group, giving `element_id`, `kind`,
  `label`, `source_refs`, a resolved `sources` detail (id, path, locator), and
  `confidence`. This is the auditable link from each drawn element back to the material.

## legend_mapping_check

- `legend_item_count`, `relations_used`, `relations_in_legend`,
  `relations_missing_legend` (must be empty for a pass), and per-dataset mapping records
  (`color_by`, `palette`, `category_colors`) so a reviewer can verify that each color
  corresponds to the real category and value.

## checks

- `validation`: status plus error and warning lists.
- `layout`: the layout report including any warning codes (e.g. `edge_label_collision`).
- `export_backends`: detected backends in the environment.
- `compliance`: overall status and per-file check records (page size, embedded fonts,
  RGB/sRGB, pixel dimensions, DPI, TIFF compression, SVG selectability).

## Honesty requirements

- Never report a format as `ok` when its export failed; record the error string.
- Never claim compliance on a failing check.
- A partial result must state the exact limit; a failed result must still be written early so
  the harness can see what was attempted.
