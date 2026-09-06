---
name: Mandate Supervisor
description: A bank regulator's live supervision console for AI payment agents — institutional navy, verification teal, drafting-table precision.
colors:
  primary: "oklch(0.5 0.175 257)"
  primary-foreground: "oklch(0.99 0.005 250)"
  ink: "oklch(0.22 0.052 258)"
  canvas: "oklch(0.984 0.005 250)"
  card: "oklch(1 0 0)"
  muted: "oklch(0.955 0.009 250)"
  muted-foreground: "oklch(0.505 0.035 255)"
  border: "oklch(0.905 0.014 250)"
  rail: "oklch(0.225 0.068 258)"
  rail-foreground: "oklch(0.9 0.016 250)"
  brand-navy: "oklch(0.27 0.096 257)"
  brand-teal: "oklch(0.625 0.115 181)"
  status-working: "#f59e0b"
  status-done: "oklch(0.66 0.118 181)"
  status-flag: "#dc2626"
  agent-mandate: "#3b82f6"
  agent-kya: "#8b5cf6"
  agent-log: "#14b8a6"
  agent-drift: "#f97316"
  agent-drafting: "#6366f1"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "3rem"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-0.025em"
  heading:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "-0.015em"
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  data:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  section: "40px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  badge-status:
    rounded: "{rounded.md}"
    padding: "2px 10px"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.lg}"
---

## Overview

An **Operate-mode** product: a case officer completes supervisory reviews here. Scanability, consistency, and earned familiarity outrank expression; the brand lives in precise details, not decoration. The visual world derives from the logo — the institutional navy of the mandate document and payment card (`#002454` → `#003c78`), the blue the card lifts to, and the teal of the verification check (`#0e9d8b`) — on cool near-white paper, with a fine blueprint-grid motif standing for the drafting table a regulator works at. The mark is that card with the agent's face on it — the thing being supervised — and it appears as vector, never bitmap: `dashboard/public/mark.svg` (favicon and app icon) and the matching `<BrandMark>` component. Its tile is a full-bleed rounded square, never a disc — the glyph is wider than it is tall, so a circle spends the canvas on empty corners and leaves the drawing unreadable in a browser tab. The glyph runs nearly edge to edge and its strokes are set far heavier than the logo's, because a hairline vanishes at 32px; it is drawn to read down to 16px. `favicon.ico` carries five natively-rendered frames (16/24/32/48/64) rather than one raster downscaled, and the 16 and 24 frames drop the card's chip and thicken the strokes further — at that size the chip is four sub-pixel blobs that only muddy the glyph. Its tile takes `{colors.rail}`, so on the sidebar it dissolves into the rail and the mark reads as the white glyph alone. Note that `SidebarMenuButton` clamps any direct `<svg>` child to `size-4`, so the rail mark is wrapped in a sized `<span>` — dropping it in bare silently renders it at 16px. The one deliberately expressive element is the dark navy sidebar rail; everything to its right stays calm.

## Colors

Every gray leans navy — nothing warm anywhere. `{colors.primary}` is reserved for primary actions, active/selected states, focus, and the human-gate "awaiting" state; never decoration. Status hues are signal and keep their conventional meanings: amber = machine working, green = complete/clean, red = flagged/blocked — but "complete/clean" is the logo's own check-mark teal, not a generic emerald. That is enforced centrally: `index.css` redefines the whole `emerald-*` ramp in `@theme`, so every `emerald-` class in the app resolves to the brand teal and the success hue cannot drift. Each specialist agent owns one identity hue (see `dashboard/src/lib/node-meta.tsx`) used at low opacity for icon chips and badges — full saturation only on live pipeline states.

## Typography

Archivo (600–800) for headings and display only; system sans for all body, labels, and controls (Operate surfaces don't need a display/body pairing below the heading level). IBM Plex Mono strictly for **data**: case ids, rule ids, amounts, timestamps, config versions — never as a "technical" costume on prose. All tables and mono runs set `font-variant-numeric: tabular-nums`. Fixed rem scale, ~1.2 ratio between steps; no fluid clamp type.

## Layout

Sidebar rail (dark) + content area (paper). Content pages center at `max-w-5xl`/`max-w-6xl` with 32px gutters. Cards use hairline 1px borders; card grids only for genuinely parallel peers (the case queue) — rosters and previews are single bordered lists with hairline row dividers. Data density is welcome; whitespace separates groups, never decorates.

## Elevation & Depth

Shadows are tinted from the navy ink, never gray-black (a Stripe-derived move — gray shadows on a tinted palette read dirty):

| Level | Treatment | Use |
|---|---|---|
| 0 | 1px `{colors.border}` border, no shadow | Inline panels, list containers |
| 1 | border + `0 1px 3px oklch(0.25 0.06 265 / 0.08)` | Cards at rest |
| 2 | `0 8px 24px oklch(0.25 0.06 265 / 0.10), 0 2px 6px oklch(0.25 0.06 265 / 0.05)` | Dialogs, popovers, the review gate |

On the dark rail, depth is a surface ladder (rail → rail-accent), never drop shadows. The blueprint grid (28px, primary at 6% alpha, masked to fade) is the only sanctioned background texture, and only on the Overview hero.

## Shapes

Radius scale tops out at 16px (`rounded-2xl` on the hero card); interactive controls sit at 8px, cards at 12px. No pills except badges. No zero-radius brutalism.

## Components

- **Buttons**: shadcn variants; primary = `{colors.primary}`. Press feedback is a 1px translate, not a scale bounce.
- **Badges** carry all severity/status signaling (never colored side-borders). Scenario badges: emerald family for clean, amber for flagged, muted for unreviewed.
- **Supervision map** (React Flow): a 4-column bench of 122px specialist chips between a centred spine. The bench's fan-in join (`specialists_done`) is **drawn, not folded away** — hiding it made the projection claim each specialist reports onward by itself. Chips take agent-hue icon roundel at rest, blue ring while working, teal when clean, red when it returned findings, primary-blue while the human gate holds. Node sizes are **declared, not measured** — React Flow measures 0×0 inside a hidden dialog and renders the boxes invisible.
- **Map edges**: two trunks flank the bench and nothing crosses it — work goes **out** down the left trunk, results come **back** up the right. Each row gap carries two rails 16px apart: the row below being dispatched to, and the row above handing its results out. So every specialist has exactly one line in at its top and one out at its bottom, and the dispatch rails never reach the collect trunk (101px clear) while the collect rails never reach the dispatch trunk (97px clear). The remaining lanes — the join's short-circuit, the synthesizer's return, the draft route, the grounding loop — each get their own channel outside the grid. An edge lights only when the run **actually walked it** — the step sequence proves the target started after the source, with the synthetic supervisor holding seq 0 as the run's origin. Lighting every edge that merely *enters* an active node was wrong: it lit the join's short-circuit and the synthesizer's return the moment the orchestrator picked up a question, wrapping three arms round an idle bench. The one exception is the human gate, which holds without emitting a step. A lit edge takes the colour of the box it enters, from `--map-*` tokens carrying the same hues as that box's ring — so a line can never disagree with the node it points at, and a path not taken never glows. Conditional edges the run skipped stay at the border colour, and the join's conditional escape — real, but never taken on a pass that dispatched any specialist — recedes to a 1px hairline at 22% with a small arrowhead: present on the map, but plainly a road not travelled. Direction is carried by an arrowhead at the target plus a chevron on the edge's longest straight run, because one head at the far end of a map-wide trunk does not tell you which way work is flowing.
- **Panel headers**: icon + title left, live-dot/meta right, hairline bottom border.
- **Empty states** name the action that fills them.
- **Focus**: 3px ring at `{colors.primary}`/50 via shadcn's ring token. Selection, caret, scrollbars, and accent-color are all themed from primary — browser surfaces carry the design too.

## Do's and Don'ts

- **Never** an eyebrow/kicker above a heading — headings carry their own weight.
- **Never** colored `border-left` bars above 1px on cards, rows, or callouts.
- **Never** bounce/elastic easing; transitions run 150–250ms, motion conveys state only, no page-load choreography.
- **Never** blur/glass or gradient blobs as decoration; the blueprint grid is the only texture.
- **Never** same-size icon+heading+text card grids as page structure; use dense bordered lists.
- **Never** mono for prose, display faces in controls, or full-saturation accents on inactive states.
- **Do** keep the four agent hues consistent everywhere an agent is named.
- **Do** state numbers from the deterministic layer verbatim (risk score, tiers) — the UI never invents severity language.
