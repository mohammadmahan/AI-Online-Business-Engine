import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it } from 'node:test';

/**
 * D-172 §3 — the storefront visual system's regression gate.
 *
 * The editorial storefront adds its own token layer (`--sf-*`) beside the D-171 §3
 * merchant tokens. Two things must never regress silently:
 *
 *  1. EVERY text pairing clears WCAG 2.2 AA (>= 4.5:1). A palette tweak is a
 *     one-character edit in CSS, so the floor is enforced here rather than left to
 *     a comment.
 *  2. The merchant panel's measured tokens keep their EXACT values — the
 *     storefront restyle must not drag the admin palette with it (the D-171
 *     contrast gate in `control-plane/` measures those hexes).
 *
 * The CSS is parsed rather than duplicated in TypeScript on purpose: the token
 * layer in `globals.css` is the single source of truth, and a second copy here
 * would be exactly the drift this test exists to catch.
 */

const CSS = readFileSync(resolve(process.cwd(), 'src/app/globals.css'), 'utf8');

function token(name: string): string {
  const match = CSS.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6})\\s*;`));
  assert.ok(match, `token --${name} is not defined as a 6-digit hex in globals.css`);
  const value = match[1] ?? '';
  assert.ok(value, `token --${name} must carry a hex value`);
  return value.toLowerCase();
}

function luminance(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const channel = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const first = luminance(a);
  const second = luminance(b);
  const hi = Math.max(first, second);
  const lo = Math.min(first, second);
  return (hi + 0.05) / (lo + 0.05);
}

/** Every pairing the storefront actually renders as text. */
const TEXT_PAIRINGS: ReadonlyArray<readonly [fg: string, bg: string, where: string]> = [
  ['sf-ink', 'sf-canvas', 'body copy on the page'],
  ['sf-ink', 'sf-surface', 'card / empty-state copy'],
  ['sf-ink', 'sf-surface-muted', 'copy on a muted block'],
  ['sf-ink-muted', 'sf-canvas', 'captions and eyebrows on the page'],
  ['sf-ink-muted', 'sf-surface', 'card captions'],
  ['sf-ink-muted', 'sf-surface-muted', 'muted-block captions'],
  ['sf-accent', 'sf-canvas', 'discount label'],
  ['sf-accent', 'sf-surface', 'discount label on a card'],
  ['sf-ink-inverse', 'sf-inverse', 'inverted primary button'],
  ['sf-ink', 'sf-surface-muted', 'hover state of a storefront control'],
];

describe('D-172 §3 storefront visual system', () => {
  it('defines the storefront token layer', () => {
    for (const name of [
      'sf-canvas',
      'sf-surface',
      'sf-surface-muted',
      'sf-ink',
      'sf-ink-muted',
      'sf-edge',
      'sf-edge-strong',
      'sf-accent',
      'sf-inverse',
      'sf-ink-inverse',
    ]) {
      assert.match(token(name), /^#[0-9a-f]{6}$/, `--${name} must be a hex token`);
    }
  });

  it('keeps every storefront text pairing at WCAG AA or better', () => {
    const failures: string[] = [];
    for (const [fg, bg, where] of TEXT_PAIRINGS) {
      const ratio = contrast(token(fg), token(bg));
      if (ratio < 4.5) {
        failures.push(`${where}: --${fg} on --${bg} = ${ratio.toFixed(2)}:1 (< 4.5:1)`);
      }
    }
    assert.deepEqual(failures, [], `contrast below AA:\n${failures.join('\n')}`);
  });

  it('leaves the D-171 merchant tokens untouched', () => {
    // Measured values recorded in D-171 §3; the storefront restyle must not move
    // them (control-plane/scripts/check-contrast.mjs measures the same palette).
    assert.equal(token('cp-canvas'), '#f8fafc');
    assert.equal(token('cp-surface'), '#ffffff');
    assert.equal(token('cp-text'), '#0f172a');
    assert.equal(token('cp-text-muted'), '#475569');
    assert.equal(token('cp-primary'), '#1e40af');
  });

  it('keeps the cart drawer on the storefront layer, with no admin token left', () => {
    const drawer = readFileSync(resolve(process.cwd(), 'src/components/storefront/cart-drawer.tsx'), 'utf8');
    // A customer surface must not borrow the merchant panel's palette or its
    // button/primitive vocabulary — that is what made the drawer read as a
    // different product. This is a source assertion on purpose: a class edit is
    // exactly how the regression would come back.
    assert.doesNotMatch(drawer, /\bcp-[a-z]/, 'the drawer must not use any --cp-* / cp-* utility');
    assert.doesNotMatch(drawer, /--radius-cp|buttonClass\./, 'the drawer must not use admin primitives');
    assert.doesNotMatch(drawer, /\b(bg-surface|text-ink|border-edge|border-edge-strong|text-danger)\b/);
    assert.match(drawer, /surface="storefront"/, 'the drawer must request the storefront chrome');
    assert.match(drawer, /sfButton\./, 'the drawer must use the storefront interaction set');
  });

  it('preserves the drawer accessibility contract across the restyle', () => {
    const drawer = readFileSync(resolve(process.cwd(), 'src/components/storefront/cart-drawer.tsx'), 'utf8');
    const dialog = readFileSync(resolve(process.cwd(), 'src/components/ui/dialog.tsx'), 'utf8');
    // Live region for quantity changes, labelled steppers, and the Radix dialog
    // (focus trap + Escape + focus return) are behavioural, not visual. They must
    // survive any chrome change.
    assert.match(drawer, /aria-live="polite"/);
    assert.match(drawer, /aria-label=\{`کاهش تعداد/);
    assert.match(drawer, /aria-label=\{`افزودن یک عدد به/);
    assert.match(drawer, /aria-label=\{`حذف /);
    assert.match(dialog, /aria-label="بستن"/);
    assert.match(dialog, /RadixDialog\.Root/);
    assert.match(dialog, /onOpenChange/);
  });

  it('adds the storefront chrome without changing the admin dialog default', () => {
    const dialog = readFileSync(resolve(process.cwd(), 'src/components/ui/dialog.tsx'), 'utf8');
    const sfChrome = dialog.slice(dialog.indexOf('storefront: {'), dialog.indexOf('} as const;'));
    assert.doesNotMatch(sfChrome, /\bcp-[a-z]/, 'the storefront chrome must not carry admin tokens');
    assert.match(sfChrome, /bg-sf-surface/);
    assert.match(sfChrome, /border-sf-edge/);
    assert.match(sfChrome, /font-display/, 'the drawer heading uses the display face');
    // The admin default is untouched: still the panel chrome, still the default.
    const panelChrome = dialog.slice(dialog.indexOf('panel: {'), dialog.indexOf('storefront: {'));
    assert.match(panelChrome, /bg-surface/);
    assert.match(panelChrome, /--radius-cp/);
    assert.match(dialog, /surface = 'panel'/);
    assert.match(dialog, /data-surface=\{surface === 'storefront'/);
  });

  it('returns focus to the cart opener instead of leaving it on <body>', () => {
    const drawer = readFileSync(resolve(process.cwd(), 'src/components/storefront/cart-drawer.tsx'), 'utf8');
    const header = readFileSync(resolve(process.cwd(), 'src/components/storefront/storefront-header.tsx'), 'utf8');
    const dialog = readFileSync(resolve(process.cwd(), 'src/components/ui/dialog.tsx'), 'utf8');
    // The opener is remembered before Radix moves focus, and the close event is
    // handled rather than left to Radix (there is no Dialog.Trigger to restore).
    assert.match(drawer, /onOpenAutoFocus=\{rememberOpener\}/);
    assert.match(drawer, /onCloseAutoFocus=\{returnFocus\}/);
    assert.match(drawer, /resolveFocusReturn\(opener, trigger\)/);
    // Last resort when both preferred targets are gone: the page's own heading.
    assert.match(drawer, /focusStorefrontLandmark\(document\)/);
    // A stable fallback target that still exists when the opener does not.
    assert.match(header, /data-cart-trigger/);
    // The shared Modal only forwards the events; admin passes neither.
    assert.match(dialog, /onOpenAutoFocus\?: \(event: Event\) => void/);
    assert.match(dialog, /onCloseAutoFocus\?: \(event: Event\) => void/);
    assert.match(dialog, /onCloseAutoFocus=\{onCloseAutoFocus\}/);
  });

  it('encodes direction nowhere in the storefront tokens', () => {
    // RTL is a document-level switch (src/lib/document.ts); a storefront token
    // must not hard-code a side, or the two would fight after a dir change.
    const sfBlock = CSS.slice(CSS.indexOf('--sf-canvas'), CSS.indexOf('@theme inline'));
    assert.doesNotMatch(sfBlock, /left|right/i, 'storefront tokens must stay direction-neutral');
  });
});
