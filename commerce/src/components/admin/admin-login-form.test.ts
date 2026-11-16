import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { AdminLoginForm } from '@/components/admin/admin-login-form';

/**
 * D-172 Phase 4 — the sign-in form's pre-hydration fallback.
 *
 * The hydrated form calls a Server Action, but before React attaches that
 * handler the browser still treats the form as a plain HTML form. Without an
 * explicit POST method, that fallback submits credentials as a GET query string
 * (and into history, proxy logs and referrers), so the method is a security
 * property, not styling.
 */
describe('admin login form — pre-hydration submission', () => {
  const html = renderToStaticMarkup(
    createElement(AdminLoginForm, { next: '/admin/assistant' }),
  );

  it('uses POST so a pre-hydration submit cannot place credentials in a GET URL', () => {
    assert.match(html, /<form[^>]*method="post"/);
    assert.doesNotMatch(html, /<form[^>]*method="get"/);
  });

  it('keeps the credential fields and submit control intact', () => {
    assert.match(html, /name="username"/);
    assert.match(html, /name="password"/);
    assert.match(html, /type="password"/);
    assert.match(html, /type="submit"/);
  });
});
