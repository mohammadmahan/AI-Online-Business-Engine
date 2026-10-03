/**
 * Minimal class-name joiner.
 *
 * A `clsx` / `tailwind-merge` dependency is deliberately avoided: the
 * control plane's primitives take a single `className` passthrough and never
 * need conflict resolution, so a small local helper keeps the dependency
 * surface minimal.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}
