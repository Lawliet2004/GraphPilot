# Ordinary-extension documenter check — GraphPilot Operate UI

**Verdict:** additions conform to the recorded system. **No enduring
documentation correction required**; one minor prose-log gap noted below.

## Files checked (byte-compared to `/tmp/graphpilot-implementation/baseline-20261018T091420Z/source`)

- `app/src/pages/Repository.tsx` — +Symbols/Content mode select, Match case
  checkbox, bounded match list (limit=25), scan-coverage footnote, exact
  around/column/end_column evidence params, shared `evidencePanel`, impact
  `has_more` notice.
- `app/src/pages/context.tsx` — URL-driven source pin (`pin/line/start/end/
  column/end_column`), pinned notice with Remove, citation ranges
  (`start–end…`, `line:column`, `· pinned`, `· partial line`, `· excerpt`).
- `app/src/styles.css` — only new rules: `.code-line.match-line`,
  `.match-list`/`.match-row`/`.match-location`, `.checkbox-label`,
  `.pinned-source`. `tokens.css` unchanged; `diff -rq` confirms these four are
  the only app/src changes.
- `app/src/lib/api.ts` — additive optional fields/types only (`Node.match`,
  `LineExcerpt`, `ContentHit`, `ContentSearch`, `ImpactResult`, evidence
  `end_line_partial`/`line_excerpt`/`content_hash`/`pinned`).

## Conformance evidence

- **Colors:** every new declaration uses existing vars — `var(--accent)`,
  `var(--soft)`, `var(--surface)`, `var(--line)`, `var(--muted)`. Zero new hex
  or rgb() literals in any diff. `.match-line` is a 12% accent `color-mix`
  background wash: accent marks selection per the recorded rule, and a
  background tint is not the floor-banned colored border or hard shadow.
- **Controls:** mode switch is a native `select` inside incumbent
  `.inline-label` (same as Node type/Relationship); the case control is a real
  checkbox with `accent-color: var(--accent)` — identical to existing
  `.tool-check input` (styles.css:3788). Buttons reuse `button secondary
  small-button`, `text-link`, `text-button`, `icon-button panel-close`.
- **Containers/type:** `.notice`, `.notice.subtle`, `.selected-summary`,
  `.graph-workspace`, `.graph-main`, `.evidence-panel`, `.canvas-footnote`,
  `small muted`, `Empty`/`Loading`/`ErrorNotice` — all pre-existing. Mono 10px
  on match rows copies the adjacent `.code-line code` precedent; no new text
  role promoted. Lucide SVG icons only; no kickers, shadows, modals, gradient
  text or glyph stand-ins.
- **Accessibility/states:** per-mode `aria-label`s, `aria-label="Content
  matches"`, real focus on the panel, `prefers-reduced-motion` respected for
  the scroll-to-source action; loading/error/empty/truncated states all use
  incumbent components with honest coverage copy (files scanned, skipped,
  completion reason) — consistent with "make evidence and uncertainty
  inspectable."

## Documentation drift

DESIGN.md's recorded system (frontmatter tokens, component primitives, named
rules) still matches the shipped build exactly; nothing added requires a
token, component or prohibition change, and nothing canonizes a craft-floor
refusal. The prose "Repository context extension" section trails the build by
one feature increment — it does not yet mention Content-mode literal search,
the match list/scan coverage, exact match ranges or pinned Ask citations.
That is a feature-log gap, not system drift: an ordinary extension preserves
the incumbent system, so this is reported rather than repaired. A future pass
could append 1–2 sentences to that section.

## System summary (unchanged)

- Palette: warm neutral surfaces + indigo rail, terracotta accent for
  selection/focus/action, typed `node-*` graph colors, paired status colors.
- Type: Manrope Variable (display→button roles), IBM Plex Mono for
  source/data; local 10px compact sizes inside code/match rows.
- Named rules: Semantic Theme, Source Voice, Flat Workspace; thin `line`
  rules, soft hover fills, panel/control radii.
- No defects canonized; no drift repaired unasked.
