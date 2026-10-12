import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  SIZE_CHART,
  SIZE_CHART_COLUMNS,
  SIZE_CHART_NOTE,
  SIZE_CHART_UNKNOWN_NOTE,
  sizeChartRow,
} from '@/lib/size-chart';

/**
 * D-172 §3.3 — the size-chart guide.
 *
 * The guide is generic, so the rules worth testing are that it is unambiguous
 * (centimetres, stated as a guide), complete for the sizes the matrix offers,
 * and that an unknown size yields null rather than a made-up row.
 */
describe('size chart (§3.3)', () => {
  it('covers the sizes the variant matrix offers, in order, in centimetres', () => {
    assert.deepEqual(
      SIZE_CHART.map((row) => row.size),
      ['S', 'M', 'L', 'XL', '2XL'],
    );
    for (const row of SIZE_CHART) {
      for (const value of [row.chest, row.waist, row.hip, row.length]) {
        assert.equal(Number.isInteger(value), true);
        assert.ok(value > 40 && value < 200, `${row.size} measurement looks like centimetres`);
      }
      assert.ok(row.chest >= row.waist, 'chest is never smaller than waist in this guide');
    }
    assert.equal(SIZE_CHART_COLUMNS.length, 4);
  });

  it('says it is a guide, and says why an unknown size has no answer', () => {
    assert.match(SIZE_CHART_NOTE, /سانتی‌متر/);
    assert.match(SIZE_CHART_NOTE, /راهنمای کلی/);
    assert.match(SIZE_CHART_UNKNOWN_NOTE, /راهنمای ثبت‌شده/);
  });

  it('looks up a size tolerantly and refuses to invent a missing one', () => {
    assert.equal(sizeChartRow('m')?.chest, 94);
    assert.equal(sizeChartRow(' XL ')?.hip, 112);
    assert.equal(sizeChartRow('XXXL'), null);
    assert.equal(sizeChartRow(''), null);
  });
});
