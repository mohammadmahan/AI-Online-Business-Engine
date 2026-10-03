#!/usr/bin/env node
/**
 * D-171 contrast gate — fail-closed WCAG 2.2 AA verification of the palette.
 *
 * Enforces every pairing declared in `src/lib/palette.mjs` and the D-171
 * shape/target floors. A single sub-threshold pairing exits non-zero, so the
 * design system cannot silently regress.
 *
 * Exit codes: 0 = all enforced pairings pass, 1 = at least one violation.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  DECORATIVE_EXEMPTIONS,
  PAIRINGS,
  PALETTE,
  SHAPE,
} from '../src/lib/palette.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

const HEX = /^#[0-9a-fA-F]{6}$/;

/** WCAG relative luminance. */
function luminance(hex) {
  if (!HEX.test(hex)) throw new Error(`not a 6-digit hex colour: ${hex}`);
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/** WCAG contrast ratio, 1..21. */
function contrast(fg, bg) {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const fmt = (n) => n.toFixed(2).padStart(6);

let failures = 0;

console.log('D-171 contrast gate — WCAG 2.2 AA (measured, fail-closed)');
console.log('='.repeat(74));

for (const theme of ['light', 'dark']) {
  console.log(`\n[${theme}]  canvas ${PALETTE[theme].canvas}  surface ${PALETTE[theme].surface}`);
  const rows = PAIRINGS.filter((p) => p.theme === theme);
  for (const rule of rows) {
    const ratio = contrast(rule.fg, rule.bg);
    const pass = ratio >= rule.min;
    if (!pass) failures += 1;
    console.log(
      `  ${pass ? 'PASS' : 'FAIL'}  ${fmt(ratio)}:1  ` +
        `(min ${rule.min.toFixed(1)})  ${rule.fg} on ${rule.bg}  — ${rule.label}`,
    );
  }
}

console.log('\n[shape & target floors]');
const floorChecks = [
  { label: 'web pointer target ≥ 24 CSS px (WCAG 2.2 AA)', ok: SHAPE.targetWeb >= 24 },
  { label: 'native touch target ≥ 44 pt (Apple HIG)', ok: SHAPE.targetTouch >= 44 },
  { label: 'target gap ≥ 8 px', ok: SHAPE.targetGap >= 8 },
  { label: 'focus indicator ≥ 2 px', ok: SHAPE.focusRingWidth >= 2 },
  { label: 'radius is a token, not a literal', ok: /^\d+px$/.test(SHAPE.radius) },
];
for (const check of floorChecks) {
  if (!check.ok) failures += 1;
  console.log(`  ${check.ok ? 'PASS' : 'FAIL'}  ${check.label}`);
}

console.log('\n[recorded decorative exemptions — no threshold applied]');
for (const ex of DECORATIVE_EXEMPTIONS) {
  console.log(
    `  NOTE  ${fmt(contrast(ex.fg, ex.bg))}:1  ${ex.fg} on ${ex.bg}  — ${ex.label}`,
  );
}

// The directive's warning value must never be used as text on the light canvas,
// and the approved spec value must never be used as text on the dark canvas.
console.log('\n[directive/spec reconciliation guards]');
const guards = [
  {
    label: '#1E40AF clears 4.5:1 as text on the LIGHT canvas (directive primary)',
    ok: contrast('#1E40AF', PALETTE.light.canvas) >= 4.5,
  },
  {
    label: '#1E40AF FAILS 4.5:1 on the dark canvas — never a dark-theme text colour',
    ok: contrast('#1E40AF', PALETTE.dark.canvas) < 4.5,
  },
  {
    label: '#15803D clears 4.5:1 as text on the LIGHT canvas (directive success)',
    ok: contrast('#15803D', PALETTE.light.canvas) >= 4.5,
  },
  {
    label: '#DC2626 clears 4.5:1 as text on the LIGHT canvas (directive danger)',
    ok: contrast('#DC2626', PALETTE.light.canvas) >= 4.5,
  },
  {
    label: '#F59E0B FAILS 4.5:1 on the light canvas — replaced there by #B45309',
    ok: contrast('#F59E0B', PALETTE.light.canvas) < 4.5,
  },
  {
    label: 'light warning #B45309 clears 4.5:1 on the light canvas',
    ok: contrast(PALETTE.light.warning, PALETTE.light.canvas) >= 4.5,
  },
  {
    label: '#F59E0B clears 4.5:1 on the dark canvas (directive warning, dark theme)',
    ok: contrast('#F59E0B', PALETTE.dark.canvas) >= 4.5,
  },
];
for (const guard of guards) {
  if (!guard.ok) failures += 1;
  console.log(`  ${guard.ok ? 'PASS' : 'FAIL'}  ${guard.label}`);
}

/**
 * Token discipline — fail-closed.
 *
 * Every file under `src/` is scanned for 6-digit hex literals. Only the two
 * files that DEFINE tokens may contain them: `globals.css` (CSS custom
 * properties) and `lib/tokens.ts` (the typed mirror). A hex literal anywhere
 * else — a component, a page, a type module — fails the gate, which is
 * exactly the directive's "no inline hardcoded hex values" requirement.
 */
const TOKEN_DEFINITION_FILES = new Set([
  'src/app/globals.css',
  'src/lib/palette.mjs',
  'src/lib/tokens.ts',
]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(resolve(ROOT, dir), { withFileTypes: true })) {
    const rel = `${dir}/${entry.name}`;
    if (entry.isDirectory()) out.push(...walk(rel));
    else out.push(rel);
  }
  return out;
}

console.log('\n[token discipline — no raw hex outside the token layer]');
const sourceFiles = walk('src');
let offenders = 0;
let permitted = 0;
for (const rel of sourceFiles) {
  const hits = (readFileSync(resolve(ROOT, rel), 'utf8').match(/#[0-9a-fA-F]{6}/g) || []).length;
  if (hits === 0) continue;
  if (TOKEN_DEFINITION_FILES.has(rel)) {
    permitted += hits;
    console.log(`  NOTE  ${rel}: ${hits} hex literal(s) — token definitions (permitted)`);
    continue;
  }
  offenders += hits;
  console.log(`  FAIL  ${rel}: ${hits} raw hex literal(s) — components must use tokens`);
}
if (offenders > 0) failures += offenders;
console.log(
  `  ${offenders === 0 ? 'PASS' : 'FAIL'}  ${sourceFiles.length} source file(s) scanned, ` +
    `${offenders} raw hex outside the token layer, ${permitted} permitted token definitions`,
);

console.log('\n' + '='.repeat(74));
if (failures > 0) {
  console.error(`CONTRAST GATE FAILED — ${failures} violation(s)`);
  process.exit(1);
}
console.log(`CONTRAST GATE PASSED — ${PAIRINGS.length} enforced pairings, 0 violations`);
