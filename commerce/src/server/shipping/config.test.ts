import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ShippingConfigError } from '@/lib/shipping';
import {
  SHIPPING_CONFIG_JSON_ENV,
  SHIPPING_ENABLED_ENV,
  SHIPPING_PRIORITY_ENV,
  resolveShippingConfig,
} from './config';

/**
 * D-175 — the environment is the only switch for all/subset/single carrier
 * modes. These tests use an explicit env map, so no process-global mutation or
 * restart is required.
 */
describe('shipping environment configuration (D-175)', () => {
  const env = (values: Record<string, string | undefined>) => values;

  it('unset = all three approved carriers', () => {
    const config = resolveShippingConfig(env({}));
    assert.deepEqual(
      config.carriers.filter((carrier) => carrier.enabled).map((carrier) => carrier.id),
      ['POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY', 'EXPRESS_COURIER'],
    );
  });

  it('subset mode enables exactly the listed carriers', () => {
    const config = resolveShippingConfig(
      env({ [SHIPPING_ENABLED_ENV]: 'POST_PISHTAZ,EXPRESS_COURIER' }),
    );
    assert.deepEqual(
      config.carriers.filter((carrier) => carrier.enabled).map((carrier) => carrier.id),
      ['POST_PISHTAZ', 'EXPRESS_COURIER'],
    );
  });

  it('single mode enables exactly one carrier', () => {
    const config = resolveShippingConfig(env({ [SHIPPING_ENABLED_ENV]: 'EXPRESS_COURIER' }));
    assert.deepEqual(
      config.carriers.filter((carrier) => carrier.enabled).map((carrier) => carrier.id),
      ['EXPRESS_COURIER'],
    );
  });

  it('none disables every carrier and is valid', () => {
    const config = resolveShippingConfig(env({ [SHIPPING_ENABLED_ENV]: 'none' }));
    assert.equal(config.carriers.every((carrier) => !carrier.enabled), true);
  });

  it('priority mode reorders without changing enablement', () => {
    const config = resolveShippingConfig(
      env({ [SHIPPING_PRIORITY_ENV]: 'EXPRESS_COURIER,POST_PISHTAZ,TIPAX_PAY_ON_DELIVERY' }),
    );
    assert.deepEqual(
      config.carriers.map((carrier) => carrier.id),
      ['EXPRESS_COURIER', 'POST_PISHTAZ', 'TIPAX_PAY_ON_DELIVERY'],
    );
    assert.equal(config.carriers.every((carrier) => carrier.enabled), true);
  });

  it('rejects unknown ids and malformed JSON instead of falling back', () => {
    assert.throws(
      () => resolveShippingConfig(env({ [SHIPPING_ENABLED_ENV]: 'NO_SUCH_CARRIER' })),
      ShippingConfigError,
    );
    assert.throws(
      () => resolveShippingConfig(env({ [SHIPPING_CONFIG_JSON_ENV]: '{not-json' })),
      ShippingConfigError,
    );
    assert.throws(
      () => resolveShippingConfig(env({ [SHIPPING_CONFIG_JSON_ENV]: '{"version":1}' })),
      ShippingConfigError,
    );
  });

  it('accepts a validated full registry override', () => {
    const override = {
      version: 1,
      parcelPolicy: {
        packagingGrams: 100,
        gramsPerItem: 100,
        lengthCm: 20,
        widthCm: 20,
        heightCm: 5,
        maxItems: 5,
      },
      carriers: [
        {
          id: 'POST_PISHTAZ',
          name: 'پست آزمایشی',
          enabled: true,
          priority: 5,
          coverage: { type: 'NATIONWIDE' },
          limits: { maxWeightGrams: 1_000, maxLengthCm: 30, maxWidthCm: 30, maxHeightCm: 30 },
          pricing: { type: 'FREE' },
          deliveryEstimate: { minDays: 1, maxDays: 2, label: '۱ تا ۲ روز' },
          capabilities: {
            tracking: false,
            barcode: false,
            cashOnDelivery: false,
            pickupPoint: false,
          },
          description: 'فقط برای آزمون محلی.',
        },
      ],
    };
    const config = resolveShippingConfig(
      env({ [SHIPPING_CONFIG_JSON_ENV]: JSON.stringify(override) }),
    );
    assert.equal(config.carriers.length, 1);
    assert.equal(config.carriers[0]?.name, 'پست آزمایشی');
    assert.equal(config.parcelPolicy.maxItems, 5);
  });
});
