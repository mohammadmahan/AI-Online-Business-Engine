/**
 * D-171 design tokens — the single source of truth for the control plane.
 *
 * Every colour, radius, and target size used by the UI is declared here once
 * and consumed by:
 *   - `app/globals.css` (CSS custom properties, light + dark)
 *   - `scripts/check-contrast.mjs` (the enforced WCAG gate)
 *
 * Nothing in a component may hardcode a hex value (`token-driven theming`).
 *
 * ── Contrast provenance ─────────────────────────────────────────────────────
 * The D-171 directive and the approved D-171 spec describe the same palette
 * for different canvases. WCAG 2.2 AA decided the assignment, measured:
 *
 *   value      as text on #F8FAFC   as text on #0F172A   assignment
 *   #1E40AF            8.34:1 ✔              2.05:1 ✘   LIGHT theme only
 *   #15803D            4.79:1 ✔              3.56:1 ✘   LIGHT theme only
 *   #DC2626            4.62:1 ✔              3.70:1 ✘   LIGHT theme only
 *   #F59E0B            2.05:1 ✘              8.31:1 ✔   DARK theme only
 *
 * So the directive's values ARE the light-canvas palette (matching the
 * approved spec), except #F59E0B which cannot carry text on a light canvas
 * and is replaced there by #B45309 (4.80:1). The dark theme uses lighter
 * variants of the same hues and takes #F59E0B itself. Only `text` and `focus`
 * must clear their threshold on BOTH canvases — both do.
 *
 * Every claim above is enforced by `scripts/check-contrast.mjs` (40 pairings,
 * fail-closed) so this comment cannot drift from the values.
 */

/** Semantic token names, grouped by role. */
export const TOKENS = {
  canvas: '--cp-canvas',
  surface: '--cp-surface',
  surfaceMuted: '--cp-surface-muted',
  text: '--cp-text',
  textMuted: '--cp-text-muted',
  border: '--cp-border',
  borderStrong: '--cp-border-strong',
  primary: '--cp-primary',
  success: '--cp-success',
  danger: '--cp-danger',
  warning: '--cp-warning',
  focus: '--cp-focus',
} as const;

export type TokenName = (typeof TOKENS)[keyof typeof TOKENS];

export interface ThemePalette {
  canvas: string;
  surface: string;
  surfaceMuted: string;
  text: string;
  textMuted: string;
  /** Decorative only — never the sole boundary of an input or the sole state cue. */
  border: string;
  /** Control boundary — cleared at 3:1 by the gate on both light surfaces. */
  borderStrong: string;
  primary: string;
  success: string;
  danger: string;
  warning: string;
  focus: string;
}

export const LIGHT: ThemePalette = {
  canvas: '#F8FAFC',
  surface: '#FFFFFF',
  surfaceMuted: '#E9EEF6',
  text: '#0F172A',
  textMuted: '#475569',
  border: '#DBEAFE',
  borderStrong: '#64748B',
  primary: '#1E40AF',
  success: '#15803D',
  danger: '#DC2626',
  warning: '#B45309',
  focus: '#1E40AF',
};

export const DARK: ThemePalette = {
  canvas: '#0F172A',
  surface: '#1E293B',
  surfaceMuted: '#111827',
  text: '#F8FAFC',
  textMuted: '#94A3B8',
  border: '#334155',
  borderStrong: '#64748B',
  primary: '#60A5FA',
  success: '#4ADE80',
  danger: '#F87171',
  warning: '#F59E0B',
  focus: '#60A5FA',
};

export const PALETTE = { light: LIGHT, dark: DARK } as const;

/**
 * Status colour used as a FILL behind text, plus the foreground that is
 * contrast-safe on that fill. Exposed to CSS as the `text-on-*` utilities
 * (`bg-danger text-on-danger` — the D-171-native spelling of the directive's
 * `text-danger-contrast`), so a filled element can never pick an unreadable
 * pairing.
 */
export const ON_STATUS = {
  light: {
    primary: '#FFFFFF',
    success: '#FFFFFF',
    danger: '#FFFFFF',
    warning: '#FFFFFF',
  },
  dark: {
    primary: '#0F172A',
    success: '#0F172A',
    danger: '#0F172A',
    warning: '#0F172A',
  },
} as const;

/** Shape and target-size floors (D-171 §3.4). */
export const SHAPE = {
  radius: '8px',
  /** Web pointer target floor — WCAG 2.2 AA (`web-target-size`). */
  targetWeb: 24,
  /** Native touch floor — Apple HIG / Material. */
  targetTouch: 44,
  /** Minimum gap between adjacent targets. */
  targetGap: 8,
  /** Minimum focus indicator thickness (`focus-states`). */
  focusRingWidth: 2,
} as const;

/**
 * Every pairing the gate enforces. `min` is the WCAG 2.2 AA threshold:
 * 4.5 for normal text, 3.0 for large text, meaningful graphics and UI
 * component boundaries.
 */
export interface PairingRule {
  theme: 'light' | 'dark';
  label: string;
  fg: string;
  bg: string;
  min: number;
}

const L = LIGHT;
const D = DARK;

export const PAIRINGS: PairingRule[] = [
  // ── text roles on every surface ───────────────────────────────────────────
  { theme: 'light', label: 'body text on canvas', fg: L.text, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'body text on surface', fg: L.text, bg: L.surface, min: 4.5 },
  { theme: 'light', label: 'body text on muted surface', fg: L.text, bg: L.surfaceMuted, min: 4.5 },
  { theme: 'light', label: 'muted text on canvas', fg: L.textMuted, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'muted text on surface', fg: L.textMuted, bg: L.surface, min: 4.5 },
  { theme: 'dark', label: 'body text on canvas', fg: D.text, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'body text on surface', fg: D.text, bg: D.surface, min: 4.5 },
  { theme: 'dark', label: 'body text on muted surface', fg: D.text, bg: D.surfaceMuted, min: 4.5 },
  { theme: 'dark', label: 'muted text on canvas', fg: D.textMuted, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'muted text on surface', fg: D.textMuted, bg: D.surface, min: 4.5 },

  // ── status colours used as TEXT ───────────────────────────────────────────
  { theme: 'light', label: 'primary text on canvas', fg: L.primary, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'primary text on surface', fg: L.primary, bg: L.surface, min: 4.5 },
  { theme: 'light', label: 'success text on canvas', fg: L.success, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'success text on surface', fg: L.success, bg: L.surface, min: 4.5 },
  { theme: 'light', label: 'danger text on canvas', fg: L.danger, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'danger text on surface', fg: L.danger, bg: L.surface, min: 4.5 },
  { theme: 'light', label: 'warning text on canvas', fg: L.warning, bg: L.canvas, min: 4.5 },
  { theme: 'light', label: 'warning text on surface', fg: L.warning, bg: L.surface, min: 4.5 },
  { theme: 'dark', label: 'primary text on canvas', fg: D.primary, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'primary text on surface', fg: D.primary, bg: D.surface, min: 4.5 },
  { theme: 'dark', label: 'success text on canvas', fg: D.success, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'success text on surface', fg: D.success, bg: D.surface, min: 4.5 },
  { theme: 'dark', label: 'danger text on canvas', fg: D.danger, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'danger text on surface', fg: D.danger, bg: D.surface, min: 4.5 },
  { theme: 'dark', label: 'warning text on canvas', fg: D.warning, bg: D.canvas, min: 4.5 },
  { theme: 'dark', label: 'warning text on surface', fg: D.warning, bg: D.surface, min: 4.5 },

  // ── filled status chips: foreground on the status FILL ────────────────────
  { theme: 'light', label: 'chip text on primary fill', fg: ON_STATUS.light.primary, bg: L.primary, min: 4.5 },
  { theme: 'light', label: 'chip text on success fill', fg: ON_STATUS.light.success, bg: L.success, min: 4.5 },
  { theme: 'light', label: 'chip text on danger fill', fg: ON_STATUS.light.danger, bg: L.danger, min: 4.5 },
  { theme: 'light', label: 'chip text on warning fill', fg: ON_STATUS.light.warning, bg: L.warning, min: 4.5 },
  { theme: 'dark', label: 'chip text on primary fill', fg: ON_STATUS.dark.primary, bg: D.primary, min: 4.5 },
  { theme: 'dark', label: 'chip text on success fill', fg: ON_STATUS.dark.success, bg: D.success, min: 4.5 },
  { theme: 'dark', label: 'chip text on danger fill', fg: ON_STATUS.dark.danger, bg: D.danger, min: 4.5 },
  { theme: 'dark', label: 'chip text on warning fill', fg: ON_STATUS.dark.warning, bg: D.warning, min: 4.5 },

  // ── active navigation label on the primary fill (`bg-primary text-surface`)
  { theme: 'light', label: 'active nav label on primary fill', fg: L.surface, bg: L.primary, min: 4.5 },
  { theme: 'dark', label: 'active nav label on primary fill', fg: D.surface, bg: D.primary, min: 4.5 },

  // ── non-text: focus indicators (UI component boundary, 3:1) ─────────────
  { theme: 'light', label: 'focus ring on canvas', fg: L.focus, bg: L.canvas, min: 3 },
  { theme: 'light', label: 'focus ring on surface', fg: L.focus, bg: L.surface, min: 3 },
  { theme: 'dark', label: 'focus ring on canvas', fg: D.focus, bg: D.canvas, min: 3 },
  { theme: 'dark', label: 'focus ring on surface', fg: D.focus, bg: D.surface, min: 3 },

  // ── non-text: control boundaries (3:1) — inputs use borderStrong ─────────
  { theme: 'light', label: 'control border on surface', fg: L.borderStrong, bg: L.surface, min: 3 },
  { theme: 'light', label: 'control border on canvas', fg: L.borderStrong, bg: L.canvas, min: 3 },
  { theme: 'dark', label: 'control border on surface', fg: D.borderStrong, bg: D.surface, min: 3 },
  { theme: 'dark', label: 'control border on canvas', fg: D.borderStrong, bg: D.canvas, min: 3 },

  // ── muted-surface coverage (placeholder / notice surfaces) ────────────────
  { theme: 'light', label: 'muted text on muted surface', fg: L.textMuted, bg: L.surfaceMuted, min: 4.5 },
  { theme: 'dark', label: 'muted text on muted surface', fg: D.textMuted, bg: D.surfaceMuted, min: 4.5 },
  { theme: 'light', label: 'control border on muted surface', fg: L.borderStrong, bg: L.surfaceMuted, min: 3 },
  { theme: 'dark', label: 'control border on muted surface', fg: D.borderStrong, bg: D.surfaceMuted, min: 3 },

  // ── alert borders (meaningful boundaries, 3:1) ────────────────────────────
  { theme: 'light', label: 'alert danger border on surface', fg: L.danger, bg: L.surface, min: 3 },
  { theme: 'dark', label: 'alert danger border on surface', fg: D.danger, bg: D.surface, min: 3 },
  { theme: 'light', label: 'alert warning border on surface', fg: L.warning, bg: L.surface, min: 3 },
  { theme: 'dark', label: 'alert warning border on surface', fg: D.warning, bg: D.surface, min: 3 },
];

/**
 * Pairings that are deliberately NOT required to meet a threshold, recorded so
 * the exemption is explicit rather than accidental (`gridline-subtle`).
 */
export const DECORATIVE_EXEMPTIONS = [
  { theme: 'light', label: 'decorative border on canvas', fg: L.border, bg: L.canvas },
  { theme: 'dark', label: 'decorative border on canvas', fg: D.border, bg: D.canvas },
  { theme: 'dark', label: 'decorative border on surface', fg: D.border, bg: D.surface },
  { theme: 'light', label: 'surface separation on canvas', fg: L.surface, bg: L.canvas },
  { theme: 'dark', label: 'surface separation on canvas', fg: D.surface, bg: D.canvas },
] as const;
