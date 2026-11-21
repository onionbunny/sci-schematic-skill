# Extraction & Provenance Guide

This is the scientific-reading stage. The deterministic tooling cannot decide what a paper
means; you do. The output is a figure spec whose every element is defensible against the
mounted materials.

## 1. Source registry first

After `ingest`, read `ingest_bundle.json` and `reading/`. Each source has a stable id
(`S1`, `S2`, …). Use exactly these ids in `source_refs`. A source entry may carry a
`locator` (page, section, table row, figure panel) and a short `quote`; prefer the most
specific locator you can.

## 2. Provenance rules (anti-hallucination)

1. Every entity and every relationship MUST have at least one `source_ref`. Provenance
   coverage below 1.0 fails validation.
2. Copy labels, names, numbers, and units verbatim. Do not normalize "p53" to "TP53",
   expand abbreviations, or translate units unless the source itself does so.
3. Never add a node or edge because it is "well known". If it is not in the materials,
   it is not in the figure.
4. One source may support many elements; one element may cite many sources. When sources
   disagree, keep both references and record the conflict (see §6).
5. Data-driven figures: every plotted value traces to a real cell/row. Do not interpolate,
   smooth, or invent a data point. Declare the mapping in `datasets`.

## 3. Entity extraction

- Assign the controlled `type` from `assets/entity_vocab.json` using the trigger words and
  the node's biological role. A kinase is an `enzyme`; a gene is a `gene`; a drug is a
  `small_molecule`.
- Distinguish the thing from its location. "nuclear p53" is still a protein; the nucleus is
  the compartment.
- Merge synonyms only when the text clearly equates them; otherwise keep separate nodes and
  note the possible identity in `uncertainties`.
- Set `confidence`: `high` (explicit, unambiguous), `medium` (inferred from context),
  `low` (weak/indirect). Low-confidence elements still need a source and an uncertainty.

## 4. Relationship extraction — direction and meaning

Direction is always **source → target**. Read the sentence's causal grammar, not word order.

- "A phosphorylates B" → source A, target B, relation `phosphorylation`.
- "B is inhibited by A" → source A, target B, relation `inhibition` (the passive does not
  reverse the causal direction).
- Match the relation to the exact meaning using the trigger lists in
  `assets/relation_vocab.json`. This choice drives the glyph:
  - positive causation → `activation` (filled arrow)
  - suppression/blocking → `inhibition` (T-bar)
  - reversible assembly → `binding` (no arrowhead); separation → `dissociation`
  - information flow (transcription/translation/translocation) → `open_arrow` relations
  - modification reactions (phosphorylation, ubiquitination, methylation, acetylation) →
    `arrow_circle` relations
- Do not collapse distinct verbs. "binds" is not "activates"; "degrades" is not
  "inhibits". If one sentence states both, model two edges.
- When the text gives a chain with intermediates ("A, via B, activates C"), include B as a
  node if the source identifies it; otherwise use `indirect_effect` directly A→C.

## 5. Hedging and uncertainty

Hedged language changes the relation and confidence, not just the label.

- "may regulate", "is associated with", "indirectly" → `indirect_effect` or `modulation`,
  dashed line, and an `uncertainties` entry.
- Direction genuinely unknown → `modulation` (open arrow, dashed), never a guessed arrow.
- Record each uncertainty as an object: element id, what is uncertain, the evidence, and
  what would resolve it. Reviewers can then see the boundary of the claims.

## 6. Contradictions and missing information

- Conflicting sources: do not pick one silently. Keep the element, cite both, set
  confidence to `low`, and add an uncertainty describing the conflict.
- Legend vs data mismatch, or a referenced source that is absent: the validator emits a
  code; either correct the spec or surface the gap. Never paper over it.
- If a required element cannot be grounded, prefer a `partial` result that states what is
  missing over a `success` that fabricates it.

## 7. Compartments and groups

- Create a group only when the source states a boundary (nucleus, cytosol, membrane,
  organelle). Assign members explicitly; an entity belongs to at most one group.
- Edges may cross group boundaries; the renderer draws groups behind nodes and never treats
  a container as an endpoint.

## 8. Minimal spec skeleton

Use `scifig.py new` to emit a skeleton, then fill it. The required top-level keys are
`case_id`, `figure`, `sources`, `entities`, `relationships`, `groups`, `datasets`,
`legend`, `annotations`, `uncertainties`, `change_records`, and `layout`.
