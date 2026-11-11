#!/usr/bin/env node
/**
 * Static dashboard freshness guard.
 *
 * The dashboard is deliberately static, so it cannot prove current health.
 * This check enforces the next best thing:
 *
 *  - every snapshot declares its kind, source, environment, commit and time;
 *  - a HISTORICAL_STATIC snapshot must say so in the JSON and the HTML and must
 *    not present itself as Operational/current;
 *  - a CURRENT snapshot is only accepted when its commit equals HEAD and its
 *    observation is no older than MAX_AGE_HOURS.
 *
 * Usage: node dashboard/check-snapshot.mjs
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAX_AGE_HOURS = 24;
const root = fileURLToPath(new URL('..', import.meta.url));
const jsonPath = new URL('./state_summary.json', import.meta.url);
const htmlPath = new URL('./index.html', import.meta.url);

const problems = [];
const requireString = (value, name) => {
  if (typeof value !== 'string' || value.trim() === '') {
    problems.push(`${name} must be a non-empty string`);
  }
};

const data = JSON.parse(readFileSync(jsonPath, 'utf8'));
const html = readFileSync(htmlPath, 'utf8');
const snapshot = data.snapshot;

if (typeof snapshot !== 'object' || snapshot === null) {
  problems.push('state_summary.json is missing the snapshot metadata object');
} else {
  requireString(snapshot.kind, 'snapshot.kind');
  requireString(snapshot.label, 'snapshot.label');
  requireString(snapshot.source, 'snapshot.source');
  requireString(snapshot.environment, 'snapshot.environment');
  requireString(snapshot.git_commit, 'snapshot.git_commit');
  requireString(snapshot.observed_at, 'snapshot.observed_at');

  const observed = Date.parse(snapshot.observed_at);
  if (!Number.isFinite(observed)) {
    problems.push('snapshot.observed_at must be an ISO timestamp');
  } else if (observed > Date.now() + 60_000) {
    problems.push('snapshot.observed_at is in the future');
  }

  if (snapshot.kind === 'HISTORICAL_STATIC') {
    requireString(snapshot.note, 'snapshot.note');
    if (!String(data.system_info?.current_phase || '').includes('HISTORICAL')) {
      problems.push('historical snapshot must mark current_phase as HISTORICAL');
    }
    if (!String(data.system_info?.system_status || '').includes('HISTORICAL')) {
      problems.push('historical snapshot must mark system_status as HISTORICAL');
    }
    for (const marker of [
      'HISTORICAL_STATIC',
      'آرشیو تاریخی',
      'وضعیت جاری نیست',
      `content="${snapshot.git_commit}"`,
      `content="${snapshot.observed_at}"`,
    ]) {
      if (!html.includes(marker)) {
        problems.push(`index.html is missing historical marker: ${marker}`);
      }
    }
  } else if (snapshot.kind === 'CURRENT') {
    const head = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: new URL('.', import.meta.url),
      encoding: 'utf8',
    }).trim();
    if (snapshot.git_commit !== head) {
      problems.push(`current snapshot commit ${snapshot.git_commit} does not match HEAD ${head}`);
    }
    if (Number.isFinite(observed) && Date.now() - observed > MAX_AGE_HOURS * 3_600_000) {
      problems.push(`current snapshot is older than ${MAX_AGE_HOURS} hours`);
    }
  } else {
    problems.push(`unsupported snapshot.kind: ${snapshot.kind}`);
  }
}

if (problems.length > 0) {
  console.error('DASHBOARD SNAPSHOT CHECK FAILED');
  for (const problem of problems) console.error(`- ${problem}`);
  process.exit(1);
}

console.log(`DASHBOARD SNAPSHOT CHECK PASSED (${snapshot.kind}, observed ${snapshot.observed_at})`);
