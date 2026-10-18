disposition: ship

Scope: finish review of the Code Symbols/Content extension only (literal case-aware
search, path:line:column hits, partial-scan disclosure, source-pinned Ask
citations). Inspection was visual: all six required captures plus both baselines
were opened and viewed — source-content-desktop/mobile, source-ask-desktop/mobile,
source-empty-desktop, source-partial-desktop, baseline-source-desktop/mobile.
Keyboard focus rings and the transient "Skip to content" control in captures are
intentional per the brief and were not counted as defects. Detector JSON is empty;
no comp exists (code-led extension of established Operate UI). CUA/manual browser
not available and not claimed; parent Playwright probe results accepted as scoped
checks only. Code sampled for file/line anchors: Repository.tsx:770-1050,
context.tsx:125-299, styles.css:1236-1295, api.ts:140-181. Unread: remainder of
Repository.tsx and styles.css outside the new selectors; no functional test re-run.

## persistence
pass — PRODUCT.md and DESIGN.md exist; DESIGN.md's "Repository context extension"
records Ask/Code/Activity. This slice extends Code in place; documenting the
Content mode is the documenter's post-review step, not a build defect. Existing
dirty work preserved per brief; no repository files touched by this review.

## fidelity
Against DESIGN.md conventions (no approved comp binds):

- Three tabs (Ask/Code/Activity), rail, theme, snapshot notice, selects — match
  baseline; retained across all captures.
- Toolbar: "Search [Symbols|Content]" inline-label + "Match case" checkbox reuse
  the baseline Node type/Relationship label-select pattern — match.
- Match rows: real buttons, accent mono `path:line:column`, ellipsized snippet,
  sibling `Ask →` text-link; soft hover/active fill; terracotta focus outline —
  match (Repository.tsx:925-968, styles.css:1236-1292).
- Scan disclosure notice + footnote (`N of M indexed files scanned · KB · commit
  · saved snapshot · total`) — honest provenance, match (Repository.tsx:907-980).
- Empty state "No matches — No indexed file in this snapshot contains that
  text." — scoped, honest copy — match.
- Ask citations `[E1] deep.py:229-235 · pinned →`, `· excerpt`, `· partial line`
  link back into Code with node/line/column params — match (context.tsx:250-291).
- Evidence panel, selected-summary "View source", keyboard list, Trace
  dependencies — unchanged from baseline.
- Mobile: toolbar wraps, results and panel stack, chips wrap; no horizontal page
  overflow visible (probe-verified). Long source lines scroll inside rows/panel.
- No craft-floor refusals introduced (no kickers, gradient text, hard shadows,
  glyph icons; mono used only for code/data).

## ceiling
reached within extension scope — new UI commits to the existing restrained
vocabulary (native selects, disclosures, flat panels, accent focus); nothing
borrowed from outside the world, no unused native devices demanded by a slice
this size.

## material_fixes
none — no material regressions found in hierarchy, legibility, copy honesty,
implied interactions, or mobile composition within extension scope.

## residual (narrow, non-blocking)
1. Pluralization: "1 matches · 5 files" and "1 total matches" render with a
   singular count — Repository.tsx:862, :978 (visible in source-content-desktop).
2. Raw reason enum in notice: "Scan incomplete — matches cap" reads mechanical —
   Repository.tsx:914 (`completion_reason.replaceAll("_"," ")`).
3. Match-row type runs at 10px (location, snippet, Ask link) — legible but at
   the floor — styles.css:1271, :1277, :1285.
4. Observation, not a UI defect: `.env` appears in Ask "Source files & matches"
   and citation chips; presumably part of the approved fixture manifest, but
   worth one sanity check that secret-named files are intended members.
5. Preexisting, out of scope: Ask history shows repeated identical
   "Find 'parent-count-unmatched'" entries — fixture/history behavior, not from
   this slice.

## keep
Honest scope language — "No indexed file in this snapshot…", partial-scan
disclosure, commit/snapshot footnote, "Static resolution does not prove runtime
behavior" — and the source-pinned citation chain into Code must not be diluted.
