/**
 * D-172 — the document's language and writing direction, declared ONCE.
 *
 * The whole product is Persian, right-to-left: every surface (storefront and
 * merchant panel) is laid out with logical CSS properties (`start`/`end`), so
 * the `dir` attribute on `<html>` is the single switch. Keeping the values here
 * — rather than as literals inside `app/layout.tsx` — lets the storefront's tests
 * assert the direction the layout actually emits, so a future refactor cannot
 * silently flip the document to LTR.
 */

export const DOCUMENT_LANGUAGE = 'fa' as const;

export const DOCUMENT_DIRECTION = 'rtl' as const;
