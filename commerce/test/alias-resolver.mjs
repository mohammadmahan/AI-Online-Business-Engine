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
 *   4. EXTENSIONLESS DEPENDENCY SUBPATHS — `next` ships real files and declares
 *      NO `exports` map, so `import { revalidatePath } from 'next/cache'` (which
 *      the storefront's server actions need, and which Next/webpack resolve)
 *      is unresolvable to Node's own ESM resolver. As a FALLBACK — only after
 *      the plain specifier has failed — an extensionless bare subpath is retried
 *      as `X.js`, which is CommonJS resolution's own rule. Nothing that already
 *      resolves changes shape, and the original error is re-raised when the
 *      fallback fails too.
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

  try {
    return asEsm(await next(specifier, context));
  } catch (error) {
    const isBareSubpath =
      !specifier.startsWith('.') &&
      !specifier.startsWith('/') &&
      !specifier.startsWith('node:') &&
      !/\.[cm]?js$/.test(specifier);
    if (isBareSubpath) {
      const retried = await firstResolvable([`${specifier}.js`], context, next);
      if (retried) {
        return asEsm(retried);
      }
    }
    throw error;
  }
}
