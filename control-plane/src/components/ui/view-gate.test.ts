/**
 * D-171 §2.3 / §10 (Phase 27.13) — native `node:test` coverage for the view-gate
 * mechanism that separates the Business view from the Technical console.
 *
 * The gate is CSS-only and decided BEFORE first paint, so its contract is a pair
 * of exact class strings plus the `data-view-gate` / `data-surface` census hooks.
 * Those strings are what `scripts/check-view-isolation.mjs` walks and what the
 * browser-resolved isolation depends on, so a silent edit to either one would
 * disable the isolation without failing anything else — this test pins them.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { BusinessOnly, TechnicalOnly, VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { cn } from '@/lib/utils';

/** Read the props of a React element without mounting anything. */
function propsOf(element: unknown): Record<string, unknown> {
  return (element as { props: Record<string, unknown> }).props;
}

/**
 * Invoke one function component with the props its parent element carries and
 * read the props it returns — i.e. follow `BusinessOnly` → `Gate` → `<div>`
 * without a renderer. Both hops are part of the contract under test.
 */
function expand(element: unknown): Record<string, unknown> {
  const { type, props } = element as { type: (props: unknown) => unknown; props: unknown };
  return propsOf(type(props));
}

describe('VIEW_GATE_CLASS — the frozen gate contract', () => {
  it('hides a business surface while the technical console is active', () => {
    assert.equal(VIEW_GATE_CLASS.business, '[[data-view-mode=technical]_&]:hidden');
  });

  it('hides a technical surface while the business view is active', () => {
    assert.equal(VIEW_GATE_CLASS.technical, '[[data-view-mode=business]_&]:hidden');
  });

  it('exposes exactly the two views, so a third gate cannot appear unnoticed', () => {
    assert.deepEqual(Object.keys(VIEW_GATE_CLASS).sort(), ['business', 'technical']);
  });
});

describe('BusinessOnly / TechnicalOnly — the gated wrappers', () => {
  it('binds the Business wrapper to the business view and forwards its surface id', () => {
    const gate = propsOf(BusinessOnly({ surface: 'dashboard-health', children: null }));
    assert.equal(gate.view, 'business');
    assert.equal(gate.surface, 'dashboard-health');
  });

  it('binds the Technical wrapper to the technical view and forwards its surface id', () => {
    const gate = propsOf(TechnicalOnly({ surface: 'automations-gates', children: null }));
    assert.equal(gate.view, 'technical');
    assert.equal(gate.surface, 'automations-gates');
  });

  it('marks a Business surface with the census hooks the isolation script reads', () => {
    const props = expand(BusinessOnly({ surface: 'dashboard-health', children: null }));
    assert.equal(props['data-view-gate'], 'business');
    assert.equal(props['data-surface'], 'dashboard-health');
    assert.ok(String(props.className).includes(VIEW_GATE_CLASS.business));
  });

  it('marks a Technical surface with the census hooks the isolation script reads', () => {
    const props = expand(TechnicalOnly({ surface: 'automations-gates', children: null }));
    assert.equal(props['data-view-gate'], 'technical');
    assert.equal(props['data-surface'], 'automations-gates');
    assert.ok(String(props.className).includes(VIEW_GATE_CLASS.technical));
  });

  it('adds no box of its own (display: contents), so no layout can shift', () => {
    const business = expand(BusinessOnly({ surface: 's', children: null }));
    const technical = expand(TechnicalOnly({ surface: 's', children: null }));
    assert.equal(String(business.className).split(' ')[0], 'contents');
    assert.equal(String(technical.className).split(' ')[0], 'contents');
  });

  it('does not cross the views: a business wrapper never carries the technical gate', () => {
    const business = expand(BusinessOnly({ surface: 's', children: null }));
    const technical = expand(TechnicalOnly({ surface: 's', children: null }));
    assert.ok(!String(business.className).includes(VIEW_GATE_CLASS.technical));
    assert.ok(!String(technical.className).includes(VIEW_GATE_CLASS.business));
  });

  it('passes an extra className through and forwards its children untouched', () => {
    const props = expand(BusinessOnly({ surface: 's', children: 'gated child', className: 'lg:block' }));
    assert.equal(props.children, 'gated child');
    assert.match(String(props.className), /lg:block$/);
  });
});

describe('cn — the gate class joiner', () => {
  it('joins the truthy classes in order', () => {
    assert.equal(cn('contents', 'a', 'b'), 'contents a b');
  });

  it('drops falsy entries so a conditional gate never emits an empty class token', () => {
    assert.equal(cn('contents', false, null, undefined, 'gate'), 'contents gate');
    assert.equal(cn(false, null), '');
  });
});
