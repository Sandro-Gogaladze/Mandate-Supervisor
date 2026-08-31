---
name: Mandate Supervisor
description: A bank regulator's live supervision console for AI payment agents — navy ink, electric blue, drafting-table precision.
colors:
  primary: "oklch(0.55 0.21 262)"
  primary-foreground: "oklch(0.99 0.005 255)"
  ink: "oklch(0.21 0.045 265)"
  canvas: "oklch(0.985 0.003 255)"
  card: "oklch(1 0 0)"
  muted: "oklch(0.955 0.008 255)"
  muted-foreground: "oklch(0.5 0.03 262)"
  border: "oklch(0.905 0.012 255)"
  rail: "oklch(0.235 0.07 266)"
  rail-foreground: "oklch(0.9 0.015 255)"
  status-working: "#f59e0b"
  status-done: "#10b981"
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

An **Operate-mode** product: a case officer completes supervisory reviews here. Scanability, consistency, and earned familiarity outrank expression; the brand lives in precise details, not decoration. The visual world derives from the logo's two colors — deep navy (the human figure) and electric blue (the robot) — on cool near-white paper, with a fine blueprint-grid motif standing for the drafting table a regulator works at. The one deliberately expressive element is the dark navy sidebar rail; everything to its right stays calm.

## Colors

Every gray leans navy — nothing warm anywhere. `{colors.primary}` is reserved for primary actions, active/selected states, focus, and the human-gate "awaiting" state; never decoration. Status hues are signal, not brand, and keep their conventional meanings: amber = machine working, emerald = complete/clean, red = flagged/blocked. Each specialist agent owns one identity hue (see `dashboard/src/lib/node-meta.tsx`) used at low opacity for icon chips and badges — full saturation only on live pipeline states.

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
- **Pipeline nodes** (React Flow): 236px cards, agent-hue icon roundel at rest, amber ring while working, emerald when complete, primary-blue "Awaiting reviewer" while the human gate holds. Edges light only along actually-traversed paths.
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
