import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { canRestoreFocus, focusStorefrontLandmark, resolveFocusReturn } from '../lib/focus-return';
import type { FocusCandidate } from '../lib/focus-return';

/**
 * D-177 Phase 2A — the cart drawer's focus-return decision.
 *
 * The Node test setup has no DOM, so the BROWSER behaviour is proven separately
 * by `scripts/check-cart-focus.mjs` (playwright-core + system Chrome). What is
 * pinned here is the decision table itself: an opener that vanished, is
 * disabled, is hidden, or is not focusable must never receive focus, and the
 * visible fallback must only be used in that case.
 */

function candidate(overrides: Partial<FocusCandidate> & { label?: string } = {}): FocusCandidate {
  return {
    isConnected: true,
    tabIndex: 0,
    hasAttribute: () => false,
    getAttribute: () => null,
    getClientRects: () => ({ length: 1 }),
    focus: () => {},
    ...overrides,
  };
}

describe('D-177 §Phase 2A cart-drawer focus return', () => {
  it('restores the opener when it is still connected and focusable', () => {
    const opener = candidate();
    const fallback = candidate();
    assert.equal(canRestoreFocus(opener), true);
    assert.equal(resolveFocusReturn(opener, fallback), opener);
  });

  it('rejects an opener that is gone, disabled, hidden or unfocusable', () => {
    assert.equal(canRestoreFocus(null), false);
    assert.equal(canRestoreFocus(undefined), false);

    const cases: Array<[string, FocusCandidate]> = [
      ['disconnected', candidate({ isConnected: false })],
      ['disabled', candidate({ hasAttribute: (name) => name === 'disabled' })],
      ['aria-hidden', candidate({ getAttribute: (name) => (name === 'aria-hidden' ? 'true' : null) })],
      ['negative tabindex', candidate({ tabIndex: -1 })],
      ['no layout box', candidate({ getClientRects: () => ({ length: 0 }) })],
    ];
    for (const [why, element] of cases) {
      assert.equal(canRestoreFocus(element), false, `${why} must not be restorable`);
      assert.equal(resolveFocusReturn(element, null), null, `${why} must not be returned`);
    }
  });

  it('falls back to the visible cart trigger only when the opener is unusable', () => {
    const fallback = candidate();
    assert.equal(resolveFocusReturn(candidate({ isConnected: false }), fallback), fallback);
    assert.equal(resolveFocusReturn(null, fallback), fallback);
    assert.equal(resolveFocusReturn(candidate({ tabIndex: -1 }), fallback), fallback);

    // Both unusable: return null rather than focusing something arbitrary.
    assert.equal(resolveFocusReturn(candidate({ isConnected: false }), candidate({ tabIndex: -1 })), null);
  });

  it('prefers a live opener over the fallback', () => {
    const opener = candidate();
    const fallback = candidate();
    assert.equal(resolveFocusReturn(opener, fallback), opener);
    assert.notEqual(resolveFocusReturn(opener, fallback), fallback);
  });
});

describe('D-177 §Phase 2A final focus destination', () => {
  interface StubElement {
    tagName: string;
    attributes: Set<string>;
    blurHandlers: Array<() => void>;
    ownerDocument: { activeElement: unknown };
    getClientRects: () => { length: number };
    hasAttribute: (name: string) => boolean;
    setAttribute: (name: string) => void;
    removeAttribute: (name: string) => void;
    addEventListener: (_: string, handler: () => void) => void;
    focus: () => void;
    querySelector: () => StubElement | null;
  }

  function stubElement(tagName: string, rects = 1): StubElement {
    const attributes = new Set<string>();
    const blurHandlers: Array<() => void> = [];
    const ownerDocument = { activeElement: null as unknown };
    const element: StubElement = {
      tagName,
      attributes,
      blurHandlers,
      ownerDocument,
      getClientRects: () => ({ length: rects }),
      hasAttribute: (name) => attributes.has(name),
      setAttribute: (name) => attributes.add(name),
      removeAttribute: (name) => attributes.delete(name),
      addEventListener: (_name, handler) => blurHandlers.push(handler),
      focus: () => {
        // Resolve at call time: the fixture re-points `ownerDocument` so the
        // heading and the landmark share one document, like real DOM nodes.
        element.ownerDocument.activeElement = element;
      },
      querySelector: () => null,
    };
    return element;
  }

  function fixture(options: { heading?: StubElement | null; mainRects?: number } = {}) {
    const main = stubElement('MAIN', options.mainRects ?? 1);
    const heading = options.heading === undefined ? stubElement('H1') : options.heading;
    for (const el of [main, heading].filter(Boolean) as StubElement[]) {
      el.ownerDocument = main.ownerDocument;
    }
    main.querySelector = () => heading;
    const root = { querySelector: (selector: string) => (selector === '#main-content' ? main : null) };
    return { root: root as unknown as ParentNode, main, heading };
  }

  it('focuses the main heading and grants tabindex only while needed', () => {
    const { root, heading } = fixture();
    const target = focusStorefrontLandmark(root);
    assert.equal(target, heading);
    assert.equal((heading as StubElement).ownerDocument.activeElement, heading);
    assert.equal((heading as StubElement).attributes.has('tabindex'), true, 'heading is made focusable');

    (heading as StubElement).blurHandlers.forEach((fn) => fn());
    assert.equal((heading as StubElement).attributes.has('tabindex'), false, 'the temporary tabindex is removed on blur');
  });

  it('does not add a tabindex when the destination already has one', () => {
    const heading = stubElement('H1');
    heading.setAttribute('tabindex');
    const { root } = fixture({ heading });
    focusStorefrontLandmark(root);
    assert.equal(heading.attributes.has('tabindex'), true);
    assert.equal(heading.blurHandlers.length, 0, 'no cleanup is registered for an existing tabindex');
  });

  it('uses the main landmark when the page has no heading', () => {
    const { root, main } = fixture({ heading: null });
    assert.equal(focusStorefrontLandmark(root), main);
    assert.equal(main.attributes.has('tabindex'), true);
  });

  it('returns null when the landmark is hidden or absent', () => {
    const hidden = fixture({ mainRects: 0 });
    assert.equal(focusStorefrontLandmark(hidden.root), null);
    const absent = { querySelector: () => null } as unknown as ParentNode;
    assert.equal(focusStorefrontLandmark(absent), null);
  });
});
