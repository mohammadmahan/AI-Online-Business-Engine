import coreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

/**
 * Flat ESLint config.
 *
 * Next 16 ships native flat configs, so no `FlatCompat` shim is needed
 * (the compat layer cannot serialize these plugin objects).
 */
const config = [
  {
    ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // D-171 §3.3 — the palette lives in the token layer. A raw hex literal
      // in a component is a design-system violation.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Literal[value=/^#[0-9a-fA-F]{6}$/]',
          message:
            'Raw hex colour literal — use a D-171 semantic token from src/lib/tokens.ts instead.',
        },
      ],
    },
  },
  {
    // The token layer and tooling are where hex values are allowed to exist.
    files: ['src/lib/tokens.ts', 'src/lib/palette.mjs', 'scripts/**'],
    rules: { 'no-restricted-syntax': 'off' },
  },
];

export default config;
