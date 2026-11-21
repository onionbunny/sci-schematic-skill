# Graphics Grammar

A controlled visual grammar so the figure reads the same way to a reviewer as the science
does. All geometry is in millimetres; the renderer converts point sizes to mm and emits
unitless SVG coordinates to avoid double-scaling.

## 1. Node shapes (by entity type)

| Shape | Entity types | Meaning |
|---|---|---|
| box (rectangle) | gene, rna, dna | nucleic acid |
| rounded rectangle | protein, enzyme, receptor, pathway_node | macromolecule |
| ellipse | ligand, process | signal / process |
| hexagon | small_molecule, metabolite | simple chemical (SBGN) |
| diamond | phenotype | outcome / endpoint |
| cut-corner rectangle | complex | molecular complex |
| container | compartment, cell, tissue | background grouping only |

Containers are drawn behind everything and never receive an edge endpoint.

## 2. Edge glyphs (by relation)

| Glyph | Line | Relations |
|---|---|---|
| filled arrow | solid | activation, cleavage |
| filled arrow | dashed | degradation, indirect_effect |
| T-bar | solid | inhibition |
| open arrow | dashed | transcription, translation, translocation, modulation |
| open arrow | solid | secretion |
| circle + arrow | solid | phosphorylation, dephosphorylation, ubiquitination, methylation, acetylation |
| hollow circle | solid | catalysis |
| plain line (no head) | solid / dashed | binding / dissociation |

The T-bar is shortened by a small clearance so it stops just outside the target node
instead of being hidden under it. Modification markers carry a short text (e.g. "P", "Ub")
inside a filled circle.

## 3. Layers (rendered back to front)

1. background and containers
2. edges and their markers
3. nodes (fill then stroke)
4. node labels
5. edge labels
6. legend
7. annotations (title, panel letter, notes)

Keeping these as separate SVG groups means a reviewer can toggle or edit any layer in
Illustrator/Inkscape. Text remains real `<text>`, never outlines, so it is selectable and
searchable.

## 4. Automatic layout rules

- **Hierarchical ranks**: upstream entities sit on the left, outcomes on the right; nodes
  sharing a rank are aligned.
- **Ports**: edges attach to dedicated ports distributed around a node, so multiple edges
  do not overlap at one point.
- **Orthogonal routing**: edges run on horizontal/vertical segments with right-angle turns.
- **Feedback edges**: a polarity-aware cycle search (positive edges first, negative edges
  last) identifies the negative feedback return, which is routed in a dedicated lane below
  the graph with feedback ports placed outside the node columns so it does not cross nodes.
- **Manual engine**: for source-preserving edits, explicit coordinates are used unchanged.

## 5. Layout warnings (machine-checked)

The engine reports, rather than silently tolerates:

- `node_overlap` — two node rectangles intersect.
- `canvas_overflow` — an element falls outside the page.
- `container_overflow` — a member lies outside its group.
- `edge_label_collision` — an edge label rectangle intersects any node, including its own
  endpoints. Long labels must be shortened, repositioned, or the node spacing increased.

Warnings do not block export but should be resolved or explained.

## 6. Color discipline

- Categorical color uses the palette declared in the spec; the number of classes must equal
  the number of legend items. Prefer `okabe_ito` (colorblind-safe, distinguishable in
  grayscale). Reusing a near-identical color for extra classes is forbidden.
- Continuous numeric values use the single-hue sequential scale, never a categorical palette.
- Semantic edge colors: positive `#0072B2`, negative `#D55E00`, neutral `#333333`.
- Node fills are white with dark strokes so labels stay legible in print.

## 7. Legend and annotations

- Every category, glyph, and symbol used in the figure appears in the legend, and every
  legend entry is actually used. A pure entity/category legend does not need relation
  entries, but a legend that lists any relation must cover every relation type present.
- The panel letter (e.g. "A"), title, and notes are annotation objects with their own
  positions and font sizes, not part of the data.
- Keep the minimum font size of the preset (5 pt for Nature/Science/Cell, 6 pt for PLOS).
