/**
 * D-171 canonical palette + pairing rules — the single source of truth.
 *
 * Plain ESM (no build step) so that both the TypeScript app
 * (`src/lib/tokens.ts`) and the plain-Node contrast gate
 * (`scripts/check-contrast.mjs`) consume the exact same values.
 *
 * ── Why each status role has a light and a dark value ──────────────────────
 * The D-171 directive and the approved D-171 spec describe the same palette
 * for different canvases. WCAG 2.2 AA decided the assignment, measured:
 *
 *   value      as text on #F8FAFC   as text on #0F172A   assignment
 *   #1E40AF            8.34:1 ✔              2.05:1 ✘   LIGHT theme only
 *   #15803D            4.79:1 ✔              3.56:1 ✘   LIGHT theme only
 *   #DC2626            4.62:1 ✔              3.70:1 ✘   LIGHT theme only
 *   #F59E0B            2.05:1 ✘              8.31:1 ✔   DARK theme only
 *
 * So the directive's values are the LIGHT-canvas palette (exactly matching
 * the approved spec), with the one exception that #F59E0B cannot carry text
 * on a light canvas and is replaced there by #B45309 (4.80:1). The dark
 * theme uses lighter variants of the same hues, and takes #F59E0B itself.
 * Only `text` and `focus` must clear their threshold on BOTH canvases.
 */

export const LIGHT = {
  canvas: '#F8FAFC',
  surface: '#FFFFFF',
  surfaceMuted: '#E9EEF6',
  text: '#0F172A',
  textMuted: '#475569',
  /** Decorative only — never the sole boundary of an input. */
  border: '#DBEAFE',
  /** Control boundary — cleared at 3:1 by the gate on both light surfaces. */
  borderStrong: '#64748B',
  primary: '#1E40AF',
  success: '#15803D',
  danger: '#DC2626',
  warning: '#B45309',
  focus: '#1E40AF',
};

export const DARK = {
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

export const PALETTE = { light: LIGHT, dark: DARK };

/**
 * Contrast-safe foreground for each status FILL — exposed to CSS as the
 * `text-on-*` utilities (`bg-danger text-on-danger`, the D-171-native spelling
 * of the directive's `text-danger-contrast`).
 */
export const ON_STATUS = {
  light: { primary: '#FFFFFF', success: '#FFFFFF', danger: '#FFFFFF', warning: '#FFFFFF' },
  dark: { primary: '#0F172A', success: '#0F172A', danger: '#0F172A', warning: '#0F172A' },
};

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
};

/**
 * Every pairing the gate enforces. `min` is the WCAG 2.2 AA threshold:
 * 4.5 normal text, 3.0 large text / meaningful graphics / component boundaries.
 */
export const PAIRINGS = [
  // text roles on every surface
  { theme: 'light', label: 'body text on canvas', fg: LIGHT.text, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'body text on surface', fg: LIGHT.text, bg: LIGHT.surface, min: 4.5 },
  { theme: 'light', label: 'body text on muted surface', fg: LIGHT.text, bg: LIGHT.surfaceMuted, min: 4.5 },
  { theme: 'light', label: 'muted text on canvas', fg: LIGHT.textMuted, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'muted text on surface', fg: LIGHT.textMuted, bg: LIGHT.surface, min: 4.5 },
  { theme: 'dark', label: 'body text on canvas', fg: DARK.text, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'body text on surface', fg: DARK.text, bg: DARK.surface, min: 4.5 },
  { theme: 'dark', label: 'body text on muted surface', fg: DARK.text, bg: DARK.surfaceMuted, min: 4.5 },
  { theme: 'dark', label: 'muted text on canvas', fg: DARK.textMuted, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'muted text on surface', fg: DARK.textMuted, bg: DARK.surface, min: 4.5 },

  // status colours used as TEXT
  { theme: 'light', label: 'primary text on canvas', fg: LIGHT.primary, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'primary text on surface', fg: LIGHT.primary, bg: LIGHT.surface, min: 4.5 },
  { theme: 'light', label: 'success text on canvas', fg: LIGHT.success, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'success text on surface', fg: LIGHT.success, bg: LIGHT.surface, min: 4.5 },
  { theme: 'light', label: 'danger text on canvas', fg: LIGHT.danger, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'danger text on surface', fg: LIGHT.danger, bg: LIGHT.surface, min: 4.5 },
  { theme: 'light', label: 'warning text on canvas', fg: LIGHT.warning, bg: LIGHT.canvas, min: 4.5 },
  { theme: 'light', label: 'warning text on surface', fg: LIGHT.warning, bg: LIGHT.surface, min: 4.5 },
  { theme: 'dark', label: 'primary text on canvas', fg: DARK.primary, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'primary text on surface', fg: DARK.primary, bg: DARK.surface, min: 4.5 },
  { theme: 'dark', label: 'success text on canvas', fg: DARK.success, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'success text on surface', fg: DARK.success, bg: DARK.surface, min: 4.5 },
  { theme: 'dark', label: 'danger text on canvas', fg: DARK.danger, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'danger text on surface', fg: DARK.danger, bg: DARK.surface, min: 4.5 },
  { theme: 'dark', label: 'warning text on canvas', fg: DARK.warning, bg: DARK.canvas, min: 4.5 },
  { theme: 'dark', label: 'warning text on surface', fg: DARK.warning, bg: DARK.surface, min: 4.5 },

  // filled status chips: foreground on the status FILL
  { theme: 'light', label: 'chip text on primary fill', fg: ON_STATUS.light.primary, bg: LIGHT.primary, min: 4.5 },
  { theme: 'light', label: 'chip text on success fill', fg: ON_STATUS.light.success, bg: LIGHT.success, min: 4.5 },
  { theme: 'light', label: 'chip text on danger fill', fg: ON_STATUS.light.danger, bg: LIGHT.danger, min: 4.5 },
  { theme: 'light', label: 'chip text on warning fill', fg: ON_STATUS.light.warning, bg: LIGHT.warning, min: 4.5 },
  { theme: 'dark', label: 'chip text on primary fill', fg: ON_STATUS.dark.primary, bg: DARK.primary, min: 4.5 },
  { theme: 'dark', label: 'chip text on success fill', fg: ON_STATUS.dark.success, bg: DARK.success, min: 4.5 },
  { theme: 'dark', label: 'chip text on danger fill', fg: ON_STATUS.dark.danger, bg: DARK.danger, min: 4.5 },
  { theme: 'dark', label: 'chip text on warning fill', fg: ON_STATUS.dark.warning, bg: DARK.warning, min: 4.5 },

  // active navigation label rendered on the primary fill (as built in the
  // sidebar: `bg-primary text-surface`)
  { theme: 'light', label: 'active nav label on primary fill (bg-primary text-surface)', fg: LIGHT.surface, bg: LIGHT.primary, min: 4.5 },
  { theme: 'dark', label: 'active nav label on primary fill (sidebar: bg-primary text-surface)', fg: DARK.surface, bg: DARK.primary, min: 4.5 },

  // non-text: focus indicators (component boundary, 3:1)
  { theme: 'light', label: 'focus ring on canvas', fg: LIGHT.focus, bg: LIGHT.canvas, min: 3 },
  { theme: 'light', label: 'focus ring on surface', fg: LIGHT.focus, bg: LIGHT.surface, min: 3 },
  { theme: 'dark', label: 'focus ring on canvas', fg: DARK.focus, bg: DARK.canvas, min: 3 },
  { theme: 'dark', label: 'focus ring on surface', fg: DARK.focus, bg: DARK.surface, min: 3 },

  // non-text: control boundaries (3:1)
  { theme: 'light', label: 'control border on surface', fg: LIGHT.borderStrong, bg: LIGHT.surface, min: 3 },
  { theme: 'light', label: 'control border on canvas', fg: LIGHT.borderStrong, bg: LIGHT.canvas, min: 3 },
  { theme: 'dark', label: 'control border on surface', fg: DARK.borderStrong, bg: DARK.surface, min: 3 },
  { theme: 'dark', label: 'control border on canvas', fg: DARK.borderStrong, bg: DARK.canvas, min: 3 },

  // muted-surface coverage (placeholder and notice surfaces)
  { theme: 'light', label: 'muted text on muted surface', fg: LIGHT.textMuted, bg: LIGHT.surfaceMuted, min: 4.5 },
  { theme: 'dark', label: 'muted text on muted surface', fg: DARK.textMuted, bg: DARK.surfaceMuted, min: 4.5 },
  { theme: 'light', label: 'control border on muted surface', fg: LIGHT.borderStrong, bg: LIGHT.surfaceMuted, min: 3 },
  { theme: 'dark', label: 'control border on muted surface', fg: DARK.borderStrong, bg: DARK.surfaceMuted, min: 3 },

  // alert borders — meaningful boundaries, not decoration (3:1)
  { theme: 'light', label: 'alert danger border on surface', fg: LIGHT.danger, bg: LIGHT.surface, min: 3 },
  { theme: 'dark', label: 'alert danger border on surface', fg: DARK.danger, bg: DARK.surface, min: 3 },
  { theme: 'light', label: 'alert warning border on surface', fg: LIGHT.warning, bg: LIGHT.surface, min: 3 },
  { theme: 'dark', label: 'alert warning border on surface', fg: DARK.warning, bg: DARK.surface, min: 3 },
];

/**
 * Deliberately threshold-free pairings, recorded so the exemption is explicit
 * rather than accidental (`gridline-subtle`, decorative surfaces).
 */
export const DECORATIVE_EXEMPTIONS = [
  { theme: 'light', label: 'decorative border on canvas', fg: LIGHT.border, bg: LIGHT.canvas },
  { theme: 'dark', label: 'decorative border on canvas', fg: DARK.border, bg: DARK.canvas },
  { theme: 'dark', label: 'decorative border on surface', fg: DARK.border, bg: DARK.surface },
  { theme: 'light', label: 'surface separation on canvas', fg: LIGHT.surface, bg: LIGHT.canvas },
  { theme: 'dark', label: 'surface separation on canvas', fg: DARK.surface, bg: DARK.canvas },
];
