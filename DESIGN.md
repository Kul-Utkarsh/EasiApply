# Design — Kinetic Neo-Tech Cockpit (Unified Authority)

> Single source of truth for the EasiApply interface across **Light and Dark** modes.
> Token implementation: `frontend/static/theme.css` (CSS variables, `[data-theme]`).
> Tailwind bridge: `frontend/static/theme-config.js`. Font files: `frontend/static/fonts/`.
> This document absorbs and supersedes `frontend/kinetic_neo_tech/DESIGN.md` (deleted).

<!-- impeccable:design-schema 2 -->

## Name
Kinetic Neo-Tech Cockpit

## Thesis
A high-velocity, industrial-grade operational interface for autonomous job searching. It rejects the soft, airy, ultra-padded look of conventional SaaS ATS tools in favor of a dense, aerospace-instrumentation aesthetic. The user is a pilot running a complex machine — in a luminous day hangar (Light) or a midnight cockpit (Dark).

## Modes & Token Architecture
All color/spacing decisions flow through CSS variables. Themes toggle via
`data-theme="light" | "dark"` on `<html>` (see `darkmode.js`); legacy `.dark`
class selectors were migrated and must not be reintroduced.

| Role | Light | Dark |
|---|---|---|
| Canvas base | `#ebecef` (`--canvas-base`) | `#121416` |
| Canvas cards | `#f8f9fa` / `#ffffff` (`--canvas-card`, `--surface-container-lowest`) | `#1e2022` / `#1a1d20` |
| Primary text | `#191c1e` (`--on-surface`) | `#e2e2e5` |
| Secondary text | `#5d5e61` | `#b6bcc4` |
| Borders | `#c3caaf` / `#737a63` | `#434935` / `#3a4048` |
| Terminal module | `#111315` (both modes — always dark) | `#111315` |
| Accent (electric lime) | `#b6f438` (`--primary-container`) | `#b6f438` |
| Text on accent | `#131f00` (never white) | `#131f00` |

### Dark Mode Variables (mapping)
Light canvas `#ebecef` → dark `#121416`; light card `#f8f9fa`/`#ffffff` →
`#1e2022`/`#1a1d20`; light text `#191c1e` → dark `#e2e2e5`; muted `#5d5e61` →
`#b6bcc4`; error `#ffdad6`→`#3a1d20`, error text `#93000a`→`#f2b8c6`.
Hardcoded light palettes (`slate-*`, `zinc-*`, `lime-*`, `red-*` in mocks) are
remapped under `[data-theme="dark"]` in `theme.css` — new code must use tokens.

### WCAG Contrast Compliance (required)
- `#b6f438` on `#131f00` ≈ **15:1 (AAA)** — the ONLY approved text-on-lime pairing.
- `#b6f438` on white ≈ **1.4:1 (FAIL)** — never white text on lime; never lime body text on light surfaces.
- Body pairs (`#191c1e`/`#f8f9fc`, `#e2e2e5`/`#121416`) ≈ 14–15:1 (AAA).
- Muted pairs (`#5d5e61`/`#f8f9fc` ≈ 5.9:1 AA; dark `#b6bcc4`/`#101214` ≈ 9:1 AA) approved for secondary text ≥12px; below AA-large thresholds use them for large/bold text only.

## Typography (tri-font stack, self-hosted)
Vendored `woff2` in `frontend/static/fonts/` (no CDN dependency).
Fallbacks cover non-Latin scripts via system + Noto stacks.

- **Display & Headings — Space Grotesk** (400–700). Angular technical geometry for section titles, module headers, hero numerals. `font-family: "Space Grotesk", system-ui, "Noto Sans", sans-serif`. Tight tracking (`-0.02em` to `-0.03em`), weight 600–700.
- **Body & Prose — Geist** (400–700). Hyper-legible for dense data fields, forms, feeds. `font-family: "Geist", system-ui, "Noto Sans", sans-serif`. Relaxed leading (22–24px at 14–16px).
- **Micro-copy & Code — JetBrains Mono** (500/700). Telemetry, logs, machine states, terminal widgets. Uppercase or key-value rhythm (`SYS_INIT:`, `AUTH:`). `font-family: "JetBrains Mono", ui-monospace, "Noto Sans Mono", monospace`.
- **Icons**: Material Symbols Outlined, 24px default, 2px-equivalent stroke (`font-weight 400`), active states use `FILL 1`. RTL: mirror directional icons (arrows, chevrons) via `.flip-rtl`; never mirror clocks, media, or status glyphs (`.no-flip`).

Scale (Tailwind names → families): `display-hero/-mobile`, `headline-lg/md/sm` → Space Grotesk; `body-lg/md/sm`, `label-md` → Geist; `code-terminal`, `code-header` → JetBrains Mono. Sizes/line-heights per `theme-config.js`.

## Spacing & Layout
- **Grid**: 12-column foundation, `1440px` max-width centered container, 24px gutters, 28px outer margins. Workspaces span 8 cols; auxiliary rails 4 cols.
- **Rhythm**: `space-xs` 4px, `space-sm` 8px, `space-md` 16px, `space-lg` 24px, `space-xl` 40px (also `--space-*` vars).
- **Anatomy**: fixed sidebar 240px; top bar 64px; right rail 320–360px.
- **Collapse**: `>1200px` triple-column; `768–1199px` sidebar → 64px icon rail/drawer, right rail stacks below stage; `<767px` 4-col fluid, single stacked cards, bottom tab pills.
- **150% zoom**: layouts must reflow (no fixed pixel heights on text containers; grids collapse at the 768px-equivalent breakpoint; telemetry log bodies scroll internally, never paginate the page).

## Shapes & Elevation
- Base `0.25rem`; modules/cards `28px` (`.card`, 1px outline boundaries); pills `9999px`.
- Light: Level 0 `#EBECEF` matte; Level 1 `#FFFFFF` + `1px rgba(0,0,0,.04)` + `0 8px 32px rgba(17,19,21,.03)`; Level 2 interactive `0 4px 16px rgba(0,0,0,.06)` + lime perimeter blur.
- Dark: flat panel stacking + border contrast; elevated `.card-elevated`; neon ring `0 0 16px rgba(182,244,56,.35)` on active targets only. No decorative gradients (radial lime blurs behind active targets only).

## Components & Micro-Interactions
Global easing: `--ease-out: cubic-bezier(0.22,1,0.36,1)`; durations `--dur-fast 120ms`, `--dur-med 240ms`, `--dur-slow 480ms`. Canonical classes `.btn-lime` / `.btn-outline` in `theme.css` (legacy Tailwind-encoded buttons keep working via the override layer).

- **Primary lime (`#b6f438`, text `#131f00`)**: `:hover` brightness 1.05 + scale 1.02; `:active` scale 0.97; `:disabled` 40% opacity, no pointer; `:focus-visible` `0 0 0 2px rgba(182,244,56,.6)` ring.
- **Secondary outline** (surface fill, 1px `--outline-variant`): `:hover` surface-high; `:active` scale 0.97; `:disabled` 40% opacity; same focus ring.
- **Search Pod**: pill compound, focus-within lime ring + lowest-surface fill (see `.search-pod`, `--focus-ring`). All inputs share the `:focus-visible` ring; never remove outlines without replacement.
- **Toggles/switches**: track `surface-highest` off / lime on; knob slides; `aria-checked` sync (see `darkmode.js`).
- **`prefers-reduced-motion: reduce`**: all animations/transitions/shimmer forced to `0.01ms`, single iteration; shimmer static.

## Feedback, Validation & Z-Index
- Inline validation: error-container fill + error icon + `font-body-sm` message under the field; offending cards get `ring-error` treatment (see `showCardError`).
- Global toasts: bottom-center pill, `z-index: var(--z-toast)` (50), 3.2s autodismiss; error toasts use error-container.
- Hierarchy: content 1 < sticky 30 < dropdown/tooltip 40 < toast 50 < modal 60 < nav-loader 70.
- Overlays: modals use dark scrim `var(--overlay-scrim)` + 6px blur (`.app-modal__scrim`); tooltips/dropdowns solid surface, no blur.

## Telemetry, Scrollbars, Skeletons
- Terminal module: always `#111315`, 24–28px radius, inner `1px #23272B` border, JetBrains Mono rows (timestamp muted, tag lime, body `#DFE2E6`).
- Log bodies: fixed max-height + internal scroll (`.log-feed-scroll`); long lines wrap (`overflow-wrap:anywhere`); vertical scrollbar hidden until hover.
- Custom scrollbars: `.terminal-scroll` (8px, `#3a4048` thumb, hover lighten) — dark-canvas optimized.
- Truncation: `.log-clamp-2` (2-line clamp) and `.log-ellipsis` for dense rows.
- Skeletons: `.skeleton` (+`--round/--card`), shimmer gradient 1.6s; static under reduced-motion.
- Charts: axes `var(--chart-grid)`, ink `var(--chart-ink)`; sequential lime ramp `--chart-seq-1..4`; categorical `--chart-cat-1..6`; sparklines 2px round-cap lime.

## States & Edge Cases
- **Empty states**: centered orbital/graphic + headline + one primary CTA (e.g. Matches → Dashboard; Analytics → queue from Matches).
- **404**: `frontend/404.html` (served by FastAPI handler; API routes return JSON). **500**: `frontend/500.html` + Retry; server logs `ERR_500` to telemetry.
- **Print**: `@media print` forces light ink-safe output, hides chrome/toggles/animations.

## i18n
Font fallbacks above; layouts must use logical properties for new CSS; icon flip policy per Typography; date/time via server locale strings; never hardcode LTR-only flex orders in new components.

## Implementation Rules (production)
1. `theme.css` is the only place for raw hex values in new work; pages use tokens/utilities.
2. No new Google-Fonts links; no new inline `tailwind.config` (use `/static/theme-config.js`).
3. No new `.dark` selectors — `[data-theme="dark"]` only.
4. Every new interactive element gets `:hover/:active/:disabled/:focus-visible`.
5. Mock/static data must be replaceable by live bindings (empty states stay truthful).
