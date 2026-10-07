/**
 * D-171 §3.1 — native `node:test` coverage for the deterministic formatters.
 *
 * These are the values a Business page renders as text, so they are pinned
 * exactly: Persian numerals in narrative counts (Phase 27.12 directive), Latin
 * numerals for amounts and timestamps, and a formatter that must produce the
 * SAME string on the build machine, the server and every browser (no ICU
 * variance, no hydration difference).
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  formatCountFa,
  formatNumber,
  formatPercent,
  formatTimeUtc,
  formatToman,
  formatUptimeSeconds,
  toPersianDigits,
} from '@/lib/format';

describe('toPersianDigits', () => {
  it('maps every Latin digit to its Persian numeral', () => {
    assert.equal(toPersianDigits('0123456789'), '۰۱۲۳۴۵۶۷۸۹');
  });

  it('accepts a number as well as a string', () => {
    assert.equal(toPersianDigits(2450), '۲۴۵۰');
  });

  it('leaves non-digit characters untouched', () => {
    assert.equal(toPersianDigits('ORD-01001'), 'ORD-۰۱۰۰۱');
    assert.equal(toPersianDigits('۳ موجود'), '۳ موجود');
  });
});

describe('formatCountFa', () => {
  it('renders zero as the Persian zero, never as empty text', () => {
    assert.equal(formatCountFa(0), '۰');
  });

  it('groups thousands with the Persian thousands mark', () => {
    assert.equal(formatCountFa(2450), '۲٬۴۵۰');
  });

  it('keeps the sign of a negative count', () => {
    assert.equal(formatCountFa(-1234), '−۱٬۲۳۴');
  });

  it('rounds to a whole count', () => {
    assert.equal(formatCountFa(2.6), '۳');
    assert.equal(formatCountFa(2.4), '۲');
  });
});

describe('Latin-numeral formatters (D-171 §3.1)', () => {
  it('formatNumber groups with Latin digits for tabular data', () => {
    assert.equal(formatNumber(1000000), '1,000,000');
  });

  it('formatPercent keeps one decimal place', () => {
    assert.equal(formatPercent(12.345), '12.3%');
    assert.equal(formatPercent(0), '0.0%');
  });

  it('formatToman carries the unit so a bare number cannot be misread', () => {
    assert.equal(formatToman(186400000), '186,400,000 تومان');
  });
});

describe('formatUptimeSeconds', () => {
  it('reports seconds below a minute', () => {
    assert.equal(formatUptimeSeconds(0), '0 ثانیه');
    assert.equal(formatUptimeSeconds(59), '59 ثانیه');
  });

  it('clamps a negative duration to zero rather than showing a negative age', () => {
    assert.equal(formatUptimeSeconds(-5), '0 ثانیه');
  });

  it('reports minutes, hours and days with the largest unit first', () => {
    assert.equal(formatUptimeSeconds(60), '1 دقیقه');
    assert.equal(formatUptimeSeconds(3600), '1 ساعت');
    assert.equal(formatUptimeSeconds(3661), '1 ساعت و 1 دقیقه');
    assert.equal(formatUptimeSeconds(86400), '1 روز');
    assert.equal(formatUptimeSeconds(90000), '1 روز و 1 ساعت');
  });
});

describe('formatTimeUtc', () => {
  it('pins the time zone to UTC, so the same instant never renders twice', () => {
    assert.equal(formatTimeUtc('2026-10-07T09:30:00.000Z'), '09:30');
    assert.equal(formatTimeUtc('2026-10-07T23:05:00.000Z'), '23:05');
  });
});
