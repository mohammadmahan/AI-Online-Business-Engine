/**
 * D-172 §3 — storefront primitives.
 *
 * The merchant panel's `ui/primitives.tsx` is a DATA surface: bordered cards,
 * dense tables, status badges. The storefront is an EDITORIAL surface, so it gets
 * its own small vocabulary instead of restyling the panel's — one token layer per
 * surface (`--sf-*` in `globals.css`), no raw hex, no second colour system.
 *
 * Both variants keep a 44px minimum target on touch pointers (`min-h-11`) while
 * staying visually quiet on a mouse, and neither communicates state by colour
 * alone — the label always carries the meaning.
 */

export const sfButton = {
  /** Primary action: ink block on ivory, inverted text (17.46:1). */
  primary:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-sf border border-sf-ink bg-sf-ink px-6 py-3 text-sf-caption font-medium text-sf-ink-inverse transition-opacity hover:opacity-90',
  /** Secondary action: hairline outline, same ink text (16.57:1 on canvas). */
  quiet:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-sf border border-sf-edge-strong px-6 py-3 text-sf-caption font-medium text-sf-ink transition-colors hover:bg-sf-muted',
  /** Header-sized quiet action: the same hairline, tighter at phone widths. */
  quietCompact:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-sf border border-sf-edge-strong px-3 text-sf-caption font-medium text-sf-ink transition-colors hover:bg-sf-muted sm:px-6',
  /** Square 44px control for a stepper: icon-only, labelled by `aria-label`. */
  icon:
    'inline-flex size-11 items-center justify-center rounded-sf border border-sf-edge-strong text-sf-ink transition-colors hover:bg-sf-muted disabled:opacity-40',
  /** Compact labelled control; the Persian label carries the meaning, not colour. */
  compact:
    'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-sf border border-sf-edge-strong px-3 text-sf-caption font-medium text-sf-ink transition-colors hover:bg-sf-muted disabled:opacity-40',
} as const;

/** Section eyebrow: small, letterspaced, muted — editorial, not decorative. */
export function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return <p className="sf-eyebrow font-medium">{children}</p>;
}

/** Section heading: the display face, sized by the token scale. */
export function SectionTitle({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="font-display text-sf-title font-semibold text-sf-ink">
      {children}
    </h2>
  );
}
