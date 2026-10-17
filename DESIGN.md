---
name: GraphPilot
description: Evidence-aware code investigation in an architectural atlas.
colors:
  bg: "#f8f8f5"
  surface: "#fff"
  soft: "#f0f0ec"
  ink: "#252b49"
  muted: "#666d80"
  subtle: "#60687a"
  line: "#e1e3e7"
  line-strong: "#b8bfcd"
  accent: "#a35f45"
  success: "#4c7560"
  success-bg: "#edf4ee"
  warning: "#8a6b31"
  warning-bg: "#fbf3e2"
  error: "#a54845"
  error-bg: "#fbeeed"
  focus: "#d0b3a42e"
  on-accent: "#fff"
  dark-bg: "#181d2c"
  dark-surface: "#212739"
  dark-soft: "#2a3044"
  dark-ink: "#eeeae1"
  dark-muted: "#b1b8cb"
  dark-subtle: "#a0a9c0"
  dark-line: "#394058"
  dark-line-strong: "#626d89"
  dark-accent: "#dda58a"
  dark-success: "#b5d0ba"
  dark-success-bg: "#283c36"
  dark-warning: "#e0c28b"
  dark-warning-bg: "#3b3428"
  dark-error: "#e9aaa3"
  dark-error-bg: "#442f36"
  dark-focus: "#dda58a25"
  dark-on-accent: "#252b49"
  rail-text: "#bec5dd"
  rail-hover: "#303858"
  rail-active: "#3a4262"
  rail-muted: "#aeb6d1"
  rail-accent: "#d8a38b"
  graph-bg: "#f1f2f4"
  graph-label: "#34394a"
  graph-edge: "#abb3c4"
  graph-arrow: "#798399"
  graph-selection: "#915842"
  graph-related: "#a96850"
  node-repository: "#525d89"
  node-branch: "#8390b4"
  node-file: "#b0b7cc"
  node-function: "#c48569"
  node-class: "#7a9f8d"
  node-test-case: "#a28baa"
  node-commit: "#ad9867"
  node-issue: "#be7373"
  node-pull-request: "#7298ab"
  node-workflow-run: "#ab9c65"
typography:
  display:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "73px"
    fontWeight: 650
    lineHeight: 1.07
    letterSpacing: "-0.04em"
  headline:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "31px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  subheading:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "15px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.6
  button:
    fontFamily: '"Manrope Variable", sans-serif'
    fontSize: "12px"
    fontWeight: 650
    lineHeight: 1.6
  mono:
    fontFamily: '"IBM Plex Mono", monospace'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  small: "5px"
  control: "7px"
  notice: "8px"
  panel: "12px"
  circular: "50%"
spacing:
  compact: "7px"
  inline: "10px"
  control: "12px"
  base: "16px"
  group: "20px"
  section: "25px"
  page-inline: "42px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "11px 17px"
  button-primary-hover:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "11px 17px"
  button-secondary-hover:
    backgroundColor: "{colors.soft}"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    padding: "0"
  button-icon:
    backgroundColor: "transparent"
    rounded: "{rounded.small}"
  button-icon-hover:
    backgroundColor: "{colors.soft}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  navigation-item:
    backgroundColor: "transparent"
    textColor: "{colors.rail-text}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
    width: "100%"
  navigation-item-hover:
    backgroundColor: "{colors.rail-hover}"
    textColor: "#fff"
  navigation-item-active:
    backgroundColor: "{colors.rail-active}"
    textColor: "#fff"
  status:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.small}"
    padding: "3px 7px"
  status-ready:
    backgroundColor: "{colors.success-bg}"
    textColor: "{colors.success}"
  status-running:
    backgroundColor: "{colors.warning-bg}"
    textColor: "{colors.warning}"
  status-failed:
    backgroundColor: "{colors.error-bg}"
    textColor: "{colors.error}"
  repository-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "23px 24px 0"
  repository-card-hover:
    backgroundColor: "{colors.soft}"
  selected-summary:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  source-code:
    backgroundColor: "{colors.soft}"
    rounded: "{rounded.control}"
    padding: "14px 0"
---

# Design System: GraphPilot

## Overview

**Creative North Star: "Architectural Atlas"**

GraphPilot pairs an indigo navigation rail with warm reading planes and restrained terracotta annotations. Humanist sans-serif type keeps the workspace approachable; source excerpts, paths and branch names use a separate monospace voice. Thin rules and tonal surfaces organize a compact investigation interface.

Selection connects a graph relationship to its source evidence. Standard links, forms, tabs and tables carry the surrounding work. The name above comes from the recorded working direction; the user confirmed repository-first exploration, source evidence and a code-first build, but did not approve a visual comp or select the direction. This document records the implementation rather than asserting that approval.

**Key Characteristics:**

- Indigo wayfinding around light or dark reading surfaces.
- Terracotta selection and action feedback, with quiet typed graph colors.
- Manrope interface text and IBM Plex Mono source/data text.
- Flat workspace surfaces, thin separators and gently rounded controls.
- Inspectable selection, source locations and explicit graph coverage.

Source of truth: `app/src/tokens.css`, `app/src/styles.css`, `app/src/components/{ui,Shell,GraphCanvas}.tsx`, `app/src/main.tsx` and sampled page implementations. The frontmatter captures actual reusable values; its spacing and radius names describe repeated literals, not existing CSS custom-property names. Component primitives describe the light theme; apply the corresponding `dark-` colors through the existing semantic variables. `PRODUCT.md`, `docs/UI_DIRECTION.md` and `.impeccable/direction.md` provide context, not alternate token authority.

Review boundary: the finish reviewer scored the six listed material fixes resolved and returned **ship for that fix list**. Available visual captures cover landing desktop/mobile, graph desktop/mobile, settings dark desktop and administration desktop. This document does not certify unscreened routes or whole-app production readiness. No raster assets ship.

## Colors

Warm neutral reading surfaces sit beside an indigo rail; terracotta marks interaction, while muted data colors distinguish graph entities.

### Primary

- **Terracotta annotation** (`accent`): inline actions, focus outlines, active repository tabs and primary-button hover. Dark mode uses the lighter `dark-accent` counterpart.
- **Indigo ink** (`ink`): primary text and filled primary buttons in light mode. The rail keeps the same fixed indigo ground in both themes; dark-mode reading text uses `dark-ink`.

### Secondary

- **Typed graph colors** (`node-*`): repository/branch indigos, file lavender, function clay, class sage, test-case mauve, commit/workflow ochres, issue rose and pull-request blue. These encode entity type, not operation success or failure.
- **Selected relationship** (`graph-selection`, `graph-related`): a stronger selected-node border and its connected arrows. A selected node retains its entity-type fill.

### Neutral

- **Warm ground / reading plane / soft inset** (`bg`, `surface`, `soft`): application background, cards and forms, then source blocks and supporting areas. Their dark counterparts retain the same roles.
- **Reading hierarchy** (`ink`, `muted`, `subtle`): primary text, supporting copy and subordinate metadata.
- **Quiet rules** (`line`, `line-strong`): separators and default borders, then stronger hover borders.
- **Rail hierarchy** (`rail-text`, `rail-muted`, `rail-hover`, `rail-active`, `rail-accent`): fixed rail colors remain independent of the reading-surface theme.
- **Graph plane** (`graph-bg`, `graph-label`, `graph-edge`, `graph-arrow`): the canvas currently retains its light palette in both themes. This is an implementation exception, not a requirement for future dark-theme charts.

Success, warning and error each pair a readable foreground with a subdued background. Status text and a dot accompany the color. `on-accent` explicitly supplies foreground contrast for primary-button hover in each theme.

**The Semantic Theme Rule.** Use the existing semantic variables for ordinary surfaces and controls; preserve the paired foreground/background roles when the theme changes.

## Typography

**Display Font:** Manrope Variable, with sans-serif fallback.
**Body Font:** Manrope Variable, with sans-serif fallback.
**Label/Mono Font:** IBM Plex Mono, with monospace fallback, for source and data references.

Both families are imported locally through Fontsource packages in the application entry point. The hierarchy is an observed set of role sizes, not a mathematical scale. Heading weight is semibold, with tight tracking and balanced wrapping; compact interface copy is mostly regular or medium weight.

### Hierarchy

- **Display:** the frontmatter display role belongs to the landing hero. Its implemented responsive sizes are (58px) at widths up to (1150px), (47px) up to (850px), then (62px) in the stacked layout up to (650px).
- **Headline:** the base page heading uses `headline`; mobile page headings use (27px). Repository titles and authentication headings have local adjustments.
- **Title / Subheading:** base second- and third-level headings use `title` and `subheading`. Repeated section headings also use (17px); public section headings use (35px), then (29px) and (30px) at the two smaller breakpoints.
- **Body:** the frontmatter body role is the page default. Supporting text commonly uses (12–13px); page introductions cap their line length at (65ch), while longer context answers and timeline copy cap at (70ch).
- **Label / Button:** form labels and standard action text use the frontmatter roles. Smaller component-specific metadata is recorded only in its component snippet, not promoted into a universal text scale.
- **Mono:** code and preformatted source use `mono`; source blocks and branch/path references have local compact sizes. Graph node names use Manrope, not monospace.

**The Source Voice Rule.** Keep source excerpts and repository references in the monospace family; use Manrope for navigation, explanatory prose and graph labels.

## Layout

The desktop shell fixes a left rail at (225px) and a context bar at (65px). Reading pages have a maximum width of (1650px) and padding of (39px 42px 55px). Content uses grids, aligned rows and dividers rather than nested cards everywhere. Repository cards auto-fill columns with a minimum width of (275px) and gaps of (20px). Forms typically use gaps of (21px).

The graph workspace places a flexible canvas beside an evidence panel of (310px). The plot is (500px) tall. At widths of at least (1600px), those become (350px) and (590px), and page top padding becomes (48px). At widths up to (1150px), the rail becomes (200px), page inline padding (25px), evidence panel (270px) and graph height (450px). Up to (850px), the rail becomes (185px), graph and evidence stack, and graph height becomes (400px); settings and supporting grids also become single columns.

Up to (650px), the rail becomes an off-canvas drawer of (235px), the content loses its left offset, the context bar becomes (58px), and page padding becomes (28px 20px 38px). Repository cards become a single column. Graph search takes the full toolbar row; filter labels wrap and their selects fill the available column. The plot height becomes (390px). The selected-node summary remains before the plot and links directly to the evidence panel below it. Repository tabs and tables retain horizontal overflow where needed.

The public page has a separate maximum width of (1420px). Its desktop hero pairs text and an illustrative graph; its sections use broader spacing than the workspace. Below (650px), those sections stack with inline padding of (24px). Authentication likewise moves from a split layout to a compact brand header and form. These are surface-specific compositions, not requirements for every page.

## Elevation & Depth

Workspace cards and panels are flat at rest. Surface tone, thin borders and selection strokes provide separation. Hover changes the fill or border rather than lifting a card. The public graph preview is the deliberate exception: a diffuse shadow and a slight rotation give the illustrative fixture depth; the rotation is removed on mobile.

### Shadow Vocabulary

- **Public preview:** `box-shadow: 0 16px 45px -25px #252b4940`; restricted to the existing landing preview.
- **Field focus:** `box-shadow: 0 0 0 3px var(--focus)`; a theme-aware focus halo, separate from elevation.

**The Flat Workspace Rule.** Separate workspace content with surface tone and thin rules; preserve the public preview's isolated depth treatment without extending it to ordinary workspace cards.

## Shapes

The recurring radius set is in the frontmatter: small metadata/control corners, gently curved form controls, notices and larger panels. Repository cards, form panels, contextual guides and the graph workspace share the panel radius. Avatars, status dots and several empty-state marks are circular. The upload field has a dashed border; ordinary panels use solid borders. File nodes use a rounded rectangle, while other canvas entity types are circular. The public preview's slightly larger corner is a local exception.

## Components

### Buttons

Compact, sentence-case actions use icon/text alignment and a minimum height of (42px). Primary actions use ink on the surface foreground, switching to accent with the dedicated `on-accent` foreground on hover. Secondary actions have a surface fill and line border, with stronger borders and soft fill on hover. Text actions remove the enclosing fill and border; icon actions use a small rounded hit area with minimum dimensions of (32px). Small buttons use a minimum height of (34px). These are distinct implemented variants.

Background and foreground transitions run for (0.15s). Global keyboard focus uses an accent outline of (2px) with offset (4px). Disabled buttons use opacity (0.48) and the not-allowed cursor. There is no separate pressed transform in the source.

### Chips

Status labels use the small radius, a dot and a written state. Ready/succeeded/success map to the success pair; running/indexing/queued/syncing/pending map to the warning pair; failed/failure map to the error pair. Other states use the neutral pair. These are informational labels, not filter buttons.

### Cards / Containers

Repository cards are links with panel corners, surface fill, a line border and the frontmatter padding. Their contents align repository identity, a status, source reference, real counts and a divided branch/commit footer. Hover strengthens the border and changes the fill to soft. Keyboard focus comes from the global outline. Form panels share the surface/border/corner language with different internal padding. Quiet guides use a soft fill without a raised shadow.

### Inputs / Fields

Fields use a line border, surface fill, control corners, full width and a minimum height of (43px). Focus changes the border to accent and adds the theme-aware halo. Placeholders use subtle text; disabled inputs use soft fill and muted text. Labels sit above fields with a gap of (7px), and explanatory notes use lighter regular text. Errors appear in the shared error notice, with an alert icon, message and optional retry action. Search is a bordered icon/input wrapper whose border responds to focus within.

### Navigation

The rail combines outline SVG icons with compact Manrope labels. Links have transparent backgrounds by default, a quiet indigo hover fill and a stronger indigo active fill. Repository tabs use an accent label and underline for the active route. Administration tabs use a soft filled active state. On mobile the shell exposes open/close controls and a scrim for the navigation drawer. Appearance options are actual radio controls with a border/fill selected state and a focus-within outline.

### Graph and Source Evidence

The Cytoscape canvas uses type-specific node fills, directed arrows and ellipsized labels. Selection increases the node size and border weight, then strengthens connected arrows. The display plots at most (14) loaded nodes, or (8) when the canvas is narrower than (500px), and states how many are plotted. Every loaded node remains in the keyboard node list; typed incoming/outgoing relationship rows make direction inspectable outside the drawing.

The selected-node summary provides a direct source action. The evidence panel shows the symbol name, type/path/line reference, documentation when present, explicit actions, relationships, a numbered source block and provenance. It has a left divider beside the graph and a top divider when stacked. Source lines preserve whitespace and scroll horizontally; prose and long identifiers wrap. The landing graph is explicitly labeled as an illustrative fixture.

Motion is restricted to short control transitions, the mobile drawer and a loading spinner. Reduced-motion preferences disable CSS animation and transitions; the direct source action also switches from smooth to instant scrolling.

## Do's and Don'ts

### Do:

- **Do** reuse the semantic light/dark surface, foreground and focus pairs.
- **Do** keep repository context and a direct route to source evidence visible during investigation.
- **Do** pair graph color with entity names and relationship direction, and expose loaded nodes through the keyboard list.
- **Do** retain visible keyboard focus, labeled controls and reduced-motion behavior.
- **Do** use the same restrained border, radius and type roles when extending existing components.

### Don't:

- **Don't** replace source evidence with unlabeled illustration or implied runtime certainty.
- **Don't** use status colors as arbitrary graph-type colors; each palette carries a separate meaning.
- **Don't** add raised shadows to ordinary workspace cards or apply the landing preview's rotation to working panels.
- **Don't** promote isolated tiny metadata sizes or unused decorative selectors into a new global text role.
- **Don't** describe the working direction, critique sketch or fix-list ship verdict as an approved comp or whole-app visual certification.

## Repository context extension

Branch and snapshot selection use the existing labeled native selects, arranged
as a wrapping row below repository identity. At widths up to 600px they stack at
full width. A native details disclosure contains the existing-branch form; saved
snapshot selection removes write actions and shows a plain notice. Source and log
actions retain the same link typography, with the log download on its own row.
Log previews reuse the numbered source block and explain redaction/retention.
These extensions reuse the established tokens; no new visual direction or approval
is implied. Browser captures cover branch/snapshot context and labeled recorded
CI log evidence at desktop/mobile widths.


## Workspace evidence and owner maintenance extension

Recent questions and CI failures use the existing two-column workspace sections,
with plain linked rows, repository/branch context, timestamps and a coverage note.
They stack on mobile. Destructive owner maintenance lives in a native disclosure
at the end of Overview source context, separated by a single line and generous
space. It requires the exact repository name, explains scope and permanence, and
uses the established error foreground/background pair. Admin removal jobs have
retry controls after failure and no misleading cancel control. These are extensions
of the incumbent Operate surface, not a new approved visual direction.
