#!/usr/bin/env node
/**
 * Guard the control plane's MOCK/LIVE boundary.
 *
 * Only `/automations` resolves CP_TELEMETRY_MODE. The other pages are
 * deterministic mock views and must keep using their mock source directly, so
 * a future edit cannot silently label mock data as live.
 */
import { readFileSync } from 'node:fs';

const expectations = [
  ['src/app/dashboard/page.tsx', 'createMockDashboardSource'],
  ['src/app/orders/page.tsx', 'createMockCommerceSource'],
  ['src/app/inventory/page.tsx', 'createMockInventorySource'],
  ['src/app/hitl-queue/page.tsx', 'createMockHitlSource'],
];
const problems = [];

for (const [file, marker] of expectations) {
  const text = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
  if (!text.includes(marker)) {
    problems.push(`${file} no longer uses ${marker}; update the provenance contract and this check together`);
  }
  if (text.includes('getTelemetrySource')) {
    problems.push(`${file} unexpectedly consumes the live telemetry seam`);
  }
}

const automations = readFileSync(
  new URL('../src/app/automations/page.tsx', import.meta.url),
  'utf8',
);
if (!automations.includes('getTelemetrySource')) {
  problems.push('automations no longer consumes getTelemetrySource');
}
if (!automations.includes('sourceMode')) {
  problems.push('automations no longer exposes its source mode');
}

if (problems.length > 0) {
  console.error('CONTROL-PLANE PROVENANCE CHECK FAILED');
  for (const problem of problems) console.error(`- ${problem}`);
  process.exit(1);
}
console.log('CONTROL-PLANE PROVENANCE CHECK PASSED — 4 mock routes, 1 live-capable route');
