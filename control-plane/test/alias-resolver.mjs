/**
 * D-171 — module-resolution hook for the native unit-test surface.
 *
 * Two problems the compiled output has, both solved here without a dependency:
 *
 *   1. PATH ALIAS — `tsconfig.json` maps `@/*` onto `./src/*`, and `tsc` does
 *      not rewrite import specifiers, so `.test-build/lib/business-summary.js`
 *      still asks for `@/lib/format`. Map that id onto the compiled file.
 *   2. MODULE FORMAT — `control-plane/package.json` declares no `"type"`, so a
 *      bare `.js` file is CommonJS to Node while the emitted code is ESM. The
 *      format is stated per file here instead of changing the package type
 *      (which Next.js owns).
 *
 * Only `.test-build/` output is affected; application and dependency modules
 * resolve exactly as they always do.
 */
const BUILD_DIR = '/.test-build/';

export async function resolve(specifier, context, next) {
  const request = specifier.startsWith('@/')
    ? new URL(`../.test-build/${specifier.slice('@/'.length)}.js`, import.meta.url).href
    : specifier;

  const resolved = await next(request, context);
  if (resolved.url.includes(BUILD_DIR)) {
    return { ...resolved, format: 'module' };
  }
  return resolved;
}
