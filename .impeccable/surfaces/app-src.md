---
version: 1
slug: "app-src"
primary_target: "app/src"
related_targets: ["app/src/pages/Repository.tsx","app/src/components/GraphCanvas.tsx"]
---

# GraphPilot repository investigation

Scope: repository-first workspace; Operate mode. Developers choose a repository,
find symbols, follow typed connections and inspect source evidence. The user
confirmed that workflow and a code-first build. The visual direction below is a
retrospective working assumption, not a user-selected direction or approved comp.

## Direction contract

THESIS: Make a code relationship an inspectable path back to its source, with the
repository workspace leading rather than generic metric cards.

OWN-WORLD: Indigo navigation, warm white reading planes, terracotta selections,
quiet typed graph colors, Manrope UI and source/data mono. Standard web controls.
The extracted, implemented system now lives in DESIGN.md.

STORY: Choose a repository, find a symbol, trace a typed connection, inspect its
source and distinguish observed evidence from unknown runtime behavior.

FIRST VIEWPORT: At desktop, a left rail and context bar frame the repository
heading, branch/commit, tabs and search/filters. A bounded graph sits beside an
evidence panel. Selection adds a direct source action; mobile stacks graph and
panel with a reachable selected-node summary. Exact responsive dimensions belong
in DESIGN.md, not in this surface's strategy.

FORM: Architectural Atlas, candidate 6 in the ordered grounded list.
seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Evidence and status

Direction provenance: docs/UI_DIRECTION.md (retrospective contract) and
.impeccable/direction.md (original candidates). The decision HTML sketch is a
critique reference only. No raster assets ship.

Available review captures cover landing desktop/mobile, graph desktop/mobile,
settings dark desktop and administration desktop. The finish reviewer scored all
six material fixes resolved and returned ship for that fix list. This does not
certify unscreened routes or whole-app production readiness. DESIGN.md and
.impeccable/design.json record the actual code after those corrections.

Unresolved: user selection of the visual direction was never received. Preserve
that provenance; do not reinterpret documentation as visual approval.
