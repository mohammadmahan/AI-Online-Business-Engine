/**
 * D-172 Phase 2 — module-resolution hook for the native unit-test surface.
 *
 * Three problems the compiled output has, all solved here without adding a
 * dependency (unlike `control-plane`, whose runtime code happens to use the
 * `@/…` alias everywhere and therefore never hit the third one):
 *
 *   1. PATH ALIAS — `tsconfig.json` maps `@/*` onto `./src/*`, and `tsc` does
 *      not rewrite import specifiers, so `.test-build/lib/variant-matrix.js`
 *      still asks for `@/lib/validation`. Map that id onto the compiled file.
 *   2. SHAPE — TypeScript emits `from './validation'` verbatim, and a directory
 *      id (`@/db`, `./schema`) is legal too, so both `X.js` and `X/index.js` are
 *      tried. ESM has no bare-specifier resolution of its own.
 *   3. MODULE FORMAT — this package declares no `"type"`, so a bare `.js` is
 *      CommonJS to Node while the emitted code is ESM. The format is stated per
 *      file here rather than changing the package type (which Next.js owns).
 *
 * Only `.test-build/` output is affected; application and dependency modules
 * resolve exactly as they always do. Only resolution failures are swallowed
 * while trying a candidate — a module that resolves but fails to load still
 * fails loudly.
 */
const BUILD_DIR = '/.test-build/';

function asEsm(resolved) {
  return resolved.url.includes(BUILD_DIR) ? { ...resolved, format: 'module' } : resolved;
}

async function firstResolvable(candidates, context, next) {
  for (const candidate of candidates) {
    try {
      return await next(candidate, context);
    } catch {
      // Try the next shape; the caller re-raises the real error if none matched.
    }
  }
  return null;
}

export async function resolve(specifier, context, next) {
  if (specifier.startsWith('@/')) {
    const base = new URL(`../.test-build/${specifier.slice('@/'.length)}`, import.meta.url).href;
    const resolved = await firstResolvable([`${base}.js`, `${base}/index.js`], context, next);
    return asEsm(resolved ?? (await next(`${base}.js`, context)));
  }

  if (specifier.startsWith('.') && !/\.[cm]?js$/.test(specifier)) {
    const candidates = [`${specifier}.js`, `${specifier}/index.js`, specifier];
    const resolved = await firstResolvable(candidates, context, next);
    if (resolved) {
      return asEsm(resolved);
    }
  }

  return asEsm(await next(specifier, context));
}
