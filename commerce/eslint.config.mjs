import coreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

/**
 * Flat ESLint config — the same shape as `control-plane/eslint.config.mjs`, so
 * both surfaces enforce one design rule: the palette lives in the token layer
 * (`src/app/globals.css`, which mirrors the D-171 §3 measured tokens), and a raw
 * hex literal in a component is a design-system violation.
 */
const config = [
  {
    ignores: ['.next/**', 'node_modules/**', '.test-build/**', 'next-env.d.ts'],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Literal[value=/^#[0-9a-fA-F]{6}$/]',
          message:
            'Raw hex colour literal — use a D-171 §3 semantic token (bg-surface, text-ink, …) or the token layer in src/app/globals.css.',
        },
      ],
    },
  },
  {
    // A literal colour is allowed ONLY where the hex IS catalog data, never a
    // style: the garment-colour palette (§2.1 `color_hex`), the payload fixtures,
    // the specs that assert colour normalisation, and tooling. Components and
    // every other module stay under the rule. (The CSS token layer is not parsed
    // by ESLint at all, so it needs no exemption.)
    files: [
      'src/lib/color-palette.ts',
      'src/lib/validation.fixtures.ts',
      'src/**/*.test.ts',
      'scripts/**',
    ],
    rules: { 'no-restricted-syntax': 'off' },
  },
];

export default config;
