/**
 * Minimal class-name joiner — the same deliberate choice as the control plane:
 * no `clsx`/`tailwind-merge` dependency for primitives that take a single
 * `className` passthrough.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}
