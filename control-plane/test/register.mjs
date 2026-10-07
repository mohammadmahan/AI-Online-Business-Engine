/**
 * D-171 — native unit-test loader registration (`npm test`).
 *
 * `test:build` compiles the test graph with the project's existing `tsc` into
 * `.test-build/`. That output still asks for the project's TypeScript path alias
 * (`@/lib/format`) because `tsc` does not rewrite import specifiers, and Node 20
 * cannot load TypeScript at all — so the two gaps are closed at LOAD time by the
 * hook registered here. No dependency is added: `node:module` is a built-in.
 *
 * Usage (already wired into `control-plane/package.json`):
 *   node --import ./test/register.mjs --test .test-build
 */
import { register } from 'node:module';

register(new URL('./alias-resolver.mjs', import.meta.url));
