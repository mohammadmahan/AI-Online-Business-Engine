import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  formatCountFa,
  formatDateFa,
  formatDateTimeFa,
  formatMachineCode,
  formatToman,
  toDateTimeLocalValue,
  toPersianDigits,
} from '@/lib/format';

/**
 * D-172 §2 — formatting is a display CONTRACT (D-171 §3.1): Persian numerals in
 * prose, and machine identifiers left in Latin so they can be read aloud or
 * pasted into a carrier's tracking page.
 */
describe('format — Persian numerals (§2)', () => {
  it('maps Latin digits to Persian and passes everything else through', () => {
    assert.equal(toPersianDigits('SKU-12'), 'SKU-۱۲');
    assert.equal(toPersianDigits(2026), '۲۰۲۶');
    assert.equal(toPersianDigits('۱۲'), '۱۲');
  });

  it('groups thousands and truncates to a whole count', () => {
    assert.equal(formatCountFa(1250), '۱٬۲۵۰');
    assert.equal(formatCountFa(0), '۰');
    assert.equal(formatCountFa(3.9), '۳');
  });

  it('always renders money with its unit', () => {
    assert.equal(formatToman(1_250_000), '۱٬۲۵۰٬۰۰۰ تومان');
  });

  it('formats dates in the Persian calendar', () => {
    const value = new Date('2026-10-10T09:30:00.000Z');
    assert.match(formatDateFa(value), /[۰-۹]/);
    assert.match(formatDateTimeFa(value), /[۰-۹]/);
  });

  it('emits a datetime-local value that round-trips the wall clock', () => {
    const value = new Date(2026, 9, 10, 9, 5);
    assert.equal(toDateTimeLocalValue(value), '2026-10-10T09:05');
  });

  it('keeps machine identifiers Latin and states absence explicitly', () => {
    assert.equal(formatMachineCode('24IR1234567890'), '24IR1234567890');
    assert.equal(formatMachineCode(null), '—');
    assert.equal(formatMachineCode(''), '—');
  });
});
