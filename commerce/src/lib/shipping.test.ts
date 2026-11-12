import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DEFAULT_SHIPPING_METHOD_ID,
  NO_ELIGIBLE_CARRIER_MESSAGE,
  SHIPPING_METHODS,
  ShippingConfigError,
  applyShippingOverrides,
  eligibleShippingOptions,
  estimateParcel,
  quoteShipping,
  shippingAmountFor,
  shippingMethodById,
  validateShippingConfig,
  VALIDATED_DEFAULT_SHIPPING_CONFIG,
} from '@/lib/shipping';

/**
 * D-175 / MCS-02 — registry, eligibility and price.
 *
 * The load-bearing rules are refusal and no-fallback: an unknown, disabled or
 * ineligible carrier is never priced as zero, never swapped for another, and
 * never offered. The three owner-approved modes are configuration-only.
 */
describe('shipping registry (D-175 / MCS-02)', () => {
  const config = VALIDATED_DEFAULT_SHIPPING_CONFIG;
  const parcel = estimateParcel(config.parcelPolicy, 2);
  assert.ok(parcel, 'the default parcel policy must estimate two items');

  it('offers the three approved carriers with stable ids and integer Toman', () => {
    assert.deepEqual(
      config.carriers.map((carrier) => carrier.id),
      ['POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY', 'EXPRESS_COURIER'],
    );
    assert.deepEqual(
      config.carriers.map((carrier) => carrier.name),
      ['پست ایران (پیشتاز)', 'تیپاکس', 'پیک محلی'],
    );
    for (const carrier of config.carriers) {
      assert.equal(carrier.enabled, true);
      assert.ok(carrier.description.length > 0);
      assert.ok(carrier.deliveryEstimate.label.length > 0);
    }
    assert.ok(shippingMethodById(DEFAULT_SHIPPING_METHOD_ID), 'the default must exist');
    assert.equal(validateShippingConfig(config).length, 0);
  });

  it('keeps the legacy catalogue view compatible', () => {
    assert.deepEqual(
      SHIPPING_METHODS.map((method) => method.id),
      ['POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY', 'EXPRESS_COURIER'],
    );
    assert.equal(shippingAmountFor('POST_PISHTAZ'), 45_000);
    assert.equal(shippingAmountFor('EXPRESS_COURIER'), 90_000);
    assert.equal(shippingAmountFor('TIPAX_PAY_ON_DELIVERY'), 0);
    assert.equal(shippingAmountFor('SAME_DAY_DRONE'), null);
    assert.equal(shippingMethodById('same_day_drone'), undefined);
  });

  it('mode ALL: no override keeps three enabled carriers in priority order', () => {
    const resolved = applyShippingOverrides(config, {});
    assert.deepEqual(
      resolved.carriers.map((carrier) => carrier.id),
      ['POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY', 'EXPRESS_COURIER'],
    );
    const eligible = eligibleShippingOptions(resolved, {
      address: 'تهران، خیابان ولیعصر',
      parcel,
    });
    assert.deepEqual(
      eligible.map((option) => option.carrierId),
      ['POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY', 'EXPRESS_COURIER'],
    );
  });

  it('mode SUBSET: the enabled list hides every unlisted carrier', () => {
    const resolved = applyShippingOverrides(config, {
      enabled: 'POST_PISHTAZ,EXPRESS_COURIER',
    });
    const eligible = eligibleShippingOptions(resolved, {
      address: 'تهران، خیابان ولیعصر',
      parcel,
    });
    assert.deepEqual(
      eligible.map((option) => option.carrierId),
      ['POST_PISHTAZ', 'EXPRESS_COURIER'],
    );
    assert.equal(
      quoteShipping(resolved, 'TIPAX_PAY_ON_DELIVERY', { address: 'تهران', parcel }).ok,
      false,
    );
  });

  it('mode SINGLE: exactly one carrier is selectable and eligible', () => {
    const resolved = applyShippingOverrides(config, { enabled: 'EXPRESS_COURIER' });
    const inTehran = eligibleShippingOptions(resolved, {
      address: 'تهران، خیابان ولیعصر',
      parcel,
    });
    assert.deepEqual(inTehran.map((option) => option.carrierId), ['EXPRESS_COURIER']);
    assert.equal(inTehran[0]?.amount, 90_000);

    const inMashhad = eligibleShippingOptions(resolved, {
      address: 'مشهد، بلوار وکیل‌آباد',
      parcel,
    });
    assert.deepEqual(inMashhad, []);
  });

  it('mode NONE: all carriers disabled yields the explicit no-eligible state', () => {
    const resolved = applyShippingOverrides(config, { enabled: 'none' });
    assert.deepEqual(
      eligibleShippingOptions(resolved, { address: 'تهران', parcel }),
      [],
    );
    assert.match(NO_ELIGIBLE_CARRIER_MESSAGE, /هیچ روش ارسالی/);
  });

  it('honours a priority override without touching checkout code', () => {
    const resolved = applyShippingOverrides(config, {
      priority: 'EXPRESS_COURIER,POST_PISHTAZ,TIPAX_PAY_ON_DELIVERY',
    });
    assert.deepEqual(
      eligibleShippingOptions(resolved, { address: 'تهران', parcel }).map(
        (option) => option.carrierId,
      ),
      ['EXPRESS_COURIER', 'POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY'],
    );
  });

  it('refuses unknown, disabled and ineligible ids instead of guessing', () => {
    assert.deepEqual(quoteShipping(config, 'SAME_DAY_DRONE', { address: 'تهران', parcel }), {
      ok: false,
      code: 'SHIPPING_UNKNOWN',
      message: 'روش ارسال انتخابی معتبر نیست.',
    });

    const subset = applyShippingOverrides(config, { enabled: 'POST_PISHTAZ' });
    const disabled = quoteShipping(subset, 'TIPAX_PAY_ON_DELIVERY', {
      address: 'تهران',
      parcel,
    });
    assert.equal(disabled.ok, false);
    assert.equal(!disabled.ok && disabled.code, 'SHIPPING_DISABLED');

    const outside = quoteShipping(config, 'EXPRESS_COURIER', {
      address: 'مشهد',
      parcel,
    });
    assert.equal(outside.ok, false);
    assert.equal(!outside.ok && outside.code, 'SHIPPING_INELIGIBLE');
  });

  it('validates destination and weight/dimension limits', () => {
    const heavy = estimateParcel(config.parcelPolicy, 40);
    assert.equal(heavy, null, 'the policy refuses more items than it can parcel');

    const byWeight = { ...parcel, weightGrams: 15_001 };
    const local = quoteShipping(config, 'EXPRESS_COURIER', {
      address: 'تهران',
      parcel: byWeight,
    });
    assert.equal(local.ok, false);
    assert.equal(!local.ok && local.code, 'SHIPPING_INELIGIBLE');

    const byDimension = { ...parcel, lengthCm: 101 };
    const oversized = quoteShipping(config, 'EXPRESS_COURIER', {
      address: 'تهران',
      parcel: byDimension,
    });
    assert.equal(oversized.ok, false);
    assert.equal(!oversized.ok && oversized.code, 'SHIPPING_INELIGIBLE');
  });

  it('supports a PER_KG price rule as registry data', () => {
    const perKg = structuredClone(config);
    const post = perKg.carriers.find((carrier) => carrier.id === 'POST_PISHTAZ');
    assert.ok(post);
    post.pricing = { type: 'PER_KG', base: 10_000, perKg: 5_000 };
    assert.ok(validateShippingConfig(perKg).length === 0);
    const result = quoteShipping(perKg, 'POST_PISHTAZ', {
      address: 'تهران',
      parcel: { ...parcel, weightGrams: 2_300 },
    });
    assert.equal(result.ok, true);
    assert.equal(result.ok && result.quote.amount, 25_000);
  });

  it('rejects malformed enablement, unknown ids and invalid JSON-shaped data', () => {
    assert.throws(
      () => applyShippingOverrides(config, { enabled: 'POST_PISHTAZ,NO_SUCH' }),
      ShippingConfigError,
    );
    assert.throws(
      () => applyShippingOverrides(config, { enabled: '' }),
      ShippingConfigError,
    );
    assert.throws(
      () => applyShippingOverrides(config, { priority: 'POST_PISHTAZ,POST_PISHTAZ' }),
      ShippingConfigError,
    );
    assert.ok(
      validateShippingConfig({ ...config, carriers: [] }).some((error) =>
        error.includes('non-empty array'),
      ),
    );
    const broken = structuredClone(config) as unknown as Record<string, unknown>;
    (broken.carriers as Array<Record<string, unknown>>)[0]!.priority = 0;
    assert.ok(
      validateShippingConfig(broken).some((error) => error.includes('priority')),
    );
  });
});
