import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createMemoryRepository } from '@/server/repository-memory';
import { createCoupon, listCoupons, setCouponActive } from '@/server/services/coupons';

/**
 * D-172 §2.4 — coupon writes. Creation validates the whole coupon, normalises the
 * code and refuses a duplicate before the database's UNIQUE constraint would have
 * to; the state the panel shows is derived at read time in `@/lib/coupon-rules`.
 */

const NOW = new Date('2026-10-10T00:00:00.000Z');

describe('coupon service — creation (§2.4)', () => {
  it('stores a percentage coupon with a normalised code', async () => {
    const repository = createMemoryRepository();

    const result = await createCoupon(
      repository,
      {
        code: ' norooz1405 ',
        discountType: 'PERCENT',
        discountValue: 20,
        minSpend: 500_000,
        expiresAt: '2027-03-20T00:00:00.000Z',
        usageLimit: 100,
        description: 'جشنواره نوروز',
      },
      NOW,
    );

    assert.equal(result.ok, true);
    if (!result.ok) {
      return;
    }
    assert.equal(result.coupon.code, 'NOROOZ1405');
    assert.equal(result.coupon.discountType, 'PERCENT');
    assert.equal(result.coupon.discountValue, 20);
    assert.equal(result.coupon.minSpend, 500_000);
    assert.equal(result.coupon.usageLimit, 100);
    assert.equal(result.coupon.usedCount, 0);
    assert.equal(result.coupon.isActive, true);
    assert.equal(result.coupon.expiresAt?.toISOString(), '2027-03-20T00:00:00.000Z');
  });

  it('stores a fixed-amount coupon and defaults min spend to zero', async () => {
    const repository = createMemoryRepository();

    const result = await createCoupon(
      repository,
      { code: 'WELCOME50', discountType: 'FIXED', discountValue: 50_000 },
      NOW,
    );

    assert.equal(result.ok, true);
    if (!result.ok) {
      return;
    }
    assert.equal(result.coupon.minSpend, 0);
    assert.equal(result.coupon.expiresAt, null);
    assert.equal(result.coupon.usageLimit, null);
    assert.equal(result.coupon.description, null);
  });

  it('refuses a duplicate code, case-insensitively', async () => {
    const repository = createMemoryRepository();

    assert.equal(
      (
        await createCoupon(
          repository,
          { code: 'NOROOZ1405', discountType: 'PERCENT', discountValue: 20 },
          NOW,
        )
      ).ok,
      true,
    );

    const duplicate = await createCoupon(
      repository,
      { code: 'norooz1405', discountType: 'PERCENT', discountValue: 10 },
      NOW,
    );

    assert.equal(duplicate.ok, false);
    assert.ok(!duplicate.ok && duplicate.code === 'CONFLICT');
    assert.equal((await listCoupons(repository)).length, 1);
  });

  it('creates nothing when the payload is invalid', async () => {
    const repository = createMemoryRepository();

    const cases = [
      { code: 'OK', discountType: 'PERCENT' as const, discountValue: 20 },
      { code: 'OKA', discountType: 'PERCENT' as const, discountValue: 0 },
      { code: 'OKB', discountType: 'PERCENT' as const, discountValue: 101 },
      { code: 'OKC', discountType: 'FIXED' as const, discountValue: 0 },
      { code: 'OKD', discountType: 'PERCENT' as const, discountValue: 10, minSpend: -5 },
      { code: 'OKE', discountType: 'PERCENT' as const, discountValue: 10, usageLimit: 0 },
      {
        code: 'OKF',
        discountType: 'PERCENT' as const,
        discountValue: 10,
        expiresAt: '2026-01-01T00:00:00.000Z',
      },
      {
        code: 'OKG',
        discountType: 'PERCENT' as const,
        discountValue: 10,
        expiresAt: 'هفتهٔ آینده',
      },
    ];

    for (const payload of cases) {
      const result = await createCoupon(repository, payload, NOW);
      assert.equal(result.ok, false, `expected refusal for ${payload.code}`);
    }
    assert.deepEqual(await listCoupons(repository), []);
  });
});

describe('coupon service — activation and derived state (§2.4)', () => {
  it('toggles activation and the derived state follows', async () => {
    const repository = createMemoryRepository();
    const created = await createCoupon(
      repository,
      { code: 'TOGGLE', discountType: 'PERCENT', discountValue: 15 },
      NOW,
    );
    assert.equal(created.ok, true);
    if (!created.ok) {
      return;
    }

    assert.equal((await setCouponActive(repository, created.coupon.id, false)).ok, true);
    let views = await listCoupons(repository);
    assert.equal(views[0]?.state, 'INACTIVE');

    assert.equal((await setCouponActive(repository, created.coupon.id, true)).ok, true);
    views = await listCoupons(repository);
    assert.equal(views[0]?.state, 'ACTIVE');
  });

  it('reports a missing coupon', async () => {
    const repository = createMemoryRepository();

    const result = await setCouponActive(repository, 'missing', false);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });

  it('derives EXPIRED and EXHAUSTED at read time from the stored row', async () => {
    const repository = createMemoryRepository({
      coupons: [
        { code: 'PAST', expiresAt: new Date('2026-01-01T00:00:00.000Z') },
        { code: 'MAXED', usageLimit: 2, usedCount: 2 },
      ],
    });

    const views = await listCoupons(repository);
    const byCode = new Map(views.map((coupon) => [coupon.code, coupon]));

    assert.equal(byCode.get('PAST')?.state, 'EXPIRED');
    assert.equal(byCode.get('MAXED')?.state, 'EXHAUSTED');
  });
});
