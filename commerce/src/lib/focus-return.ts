/**
 * D-177 Phase 2A — where focus goes when the cart drawer closes.
 *
 * The storefront cart button is NOT a Radix `Dialog.Trigger` (it lives in the
 * header, the drawer is rendered by the layout), so Radix has no trigger to
 * return focus to and drops it on `<body>`. The drawer therefore remembers the
 * element that had focus when it opened and restores it on close.
 *
 * The order is: the opener, then the visible header cart trigger, then the main
 * landmark / its heading (see `focusStorefrontLandmark`). The first two are pure
 * decisions, pinned by a Node test with structural stubs; the last one touches
 * the DOM and is proven by the real-browser check.
 */

/** The subset of `HTMLElement` the decision needs. */
export interface FocusCandidate {
  isConnected: boolean;
  tabIndex: number;
  hasAttribute(name: string): boolean;
  getAttribute(name: string): string | null;
  getClientRects(): { length: number };
  focus(): void;
}

/** Can this element still receive focus right now? */
export function canRestoreFocus(element: FocusCandidate | null | undefined): boolean {
  if (!element) return false;
  if (!element.isConnected) return false;
  if (element.hasAttribute('disabled')) return false;
  if (element.getAttribute('aria-hidden') === 'true') return false;
  if (element.tabIndex < 0) return false;
  // A detached-but-connected element inside `display:none` has no client rects.
  return element.getClientRects().length > 0;
}

/**
 * The opener wins; the fallback is used only when the opener can no longer take
 * focus. Returns `null` when neither is usable, so the caller can leave focus
 * where the browser put it rather than focusing something arbitrary.
 */
export function resolveFocusReturn<T extends FocusCandidate>(
  opener: T | null | undefined,
  fallback: T | null | undefined,
): T | null {
  if (canRestoreFocus(opener)) return opener as T;
  if (canRestoreFocus(fallback)) return fallback as T;
  return null;
}

/**
 * The last resort: the storefront's main landmark or its heading.
 *
 * Used only when BOTH the opener and the header cart trigger are gone, so focus
 * must not be abandoned on `<body>`. The heading is the most informative visible
 * destination; the landmark itself is the fallback when the page has no heading
 * (an error state).
 *
 * Focusability is granted with `tabindex="-1"` — negative, so the normal Tab
 * order is unchanged — and the attribute is removed again on blur so the markup
 * returns to its original state. Nothing here is time-based: it runs inside
 * Radix's close event, after `preventDefault()`.
 */
export function focusStorefrontLandmark(root: ParentNode): HTMLElement | null {
  const main = root.querySelector<HTMLElement>('#main-content');
  if (!main || main.getClientRects().length === 0) return null;

  const heading = main.querySelector<HTMLElement>('h1, h2');
  const target = heading && heading.getClientRects().length > 0 ? heading : main;

  const addedTabIndex = !target.hasAttribute('tabindex');
  if (addedTabIndex) target.setAttribute('tabindex', '-1');

  target.focus();
  if (target.ownerDocument.activeElement !== target) {
    if (addedTabIndex) target.removeAttribute('tabindex');
    return null;
  }

  if (addedTabIndex) {
    target.addEventListener('blur', () => target.removeAttribute('tabindex'), { once: true });
  }
  return target;
}
