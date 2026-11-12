import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  type CarrierAdapter,
  type CarrierShipmentRequest,
  type CarrierShipmentResult,
  createShipmentWithRetry,
  parcelHash,
  shipmentKey,
  validateCarrierRequest,
} from './carrier-adapter';
import { SANDBOX_CARRIER_IDS, sandboxCarrierFor } from './sandbox';

/**
 * D-175 / MCS-05 — adapter contract, identity and fault policy.
 *
 * Every test is offline: the adapters are local sandboxes and the retry test
 * injects a sleep. No carrier endpoint is contacted.
 */

const PARCEL = {
  weightGrams: 2_000,
  lengthCm: 35,
  widthCm: 30,
  heightCm: 10,
  declaredValueToman: 450_000,
};

function request(overrides: Partial<CarrierShipmentRequest> = {}): CarrierShipmentRequest {
  return {
    orderId: 'order-sandbox-1',
    carrierId: 'POST_PISHTAZ',
    shipmentKey: shipmentKey('order-sandbox-1', 'POST_PISHTAZ', PARCEL),
    parcel: PARCEL,
    destination: { address: 'تهران، خیابان آزمایشی، پلاک ۱' },
    ...overrides,
  };
}

function transientFailure(): CarrierShipmentResult {
  return {
    ok: false,
    error: {
      kind: 'TRANSPORT',
      code: 'TEST_TRANSPORT',
      retryable: true,
      message: 'local test transport failure',
    },
  };
}

const SUCCESS: CarrierShipmentResult = {
  ok: true,
  carrierId: 'POST_PISHTAZ',
  trackingNumber: 'TEST-1',
  barcode: 'BC-1',
  labelReference: 'LABEL-1',
  dryRun: true,
};

function scriptedAdapter(results: CarrierShipmentResult[]): CarrierAdapter & { calls: number } {
  const adapter = {
    carrierId: 'POST_PISHTAZ',
    displayName: 'scripted',
    calls: 0,
    async createShipment(): Promise<CarrierShipmentResult> {
      adapter.calls += 1;
      return results[Math.min(adapter.calls - 1, results.length - 1)] as CarrierShipmentResult;
    },
  };
  return adapter;
}

describe('carrier adapter contract (D-175 / MCS-05)', () => {
  it('hashes parcel identity deterministically and excludes the address', () => {
    const first = parcelHash(PARCEL);
    const second = parcelHash({ ...PARCEL });
    const heavier = parcelHash({ ...PARCEL, weightGrams: 2_001 });
    assert.equal(first, second);
    assert.equal(first.length, 64);
    assert.notEqual(first, heavier);
    assert.ok(!first.includes('تهران'));
    assert.equal(
      shipmentKey('order-sandbox-1', 'POST_PISHTAZ', PARCEL),
      shipmentKey('order-sandbox-1', 'POST_PISHTAZ', { ...PARCEL }),
    );
    assert.notEqual(
      shipmentKey('order-sandbox-1', 'POST_PISHTAZ', PARCEL),
      shipmentKey('order-sandbox-1', 'TIPAX_PAY_ON_DELIVERY', PARCEL),
    );
  });

  it('refuses invalid parcel invariants before any adapter call', () => {
    const errors = validateCarrierRequest(
      request({
        parcel: { ...PARCEL, weightGrams: 0 },
        shipmentKey: 'not-a-digest',
        destination: { address: '   ' },
      }),
    );
    assert.ok(errors.some((error) => error.includes('weightGrams')));
    assert.ok(errors.some((error) => error.includes('shipmentKey')));
    assert.ok(errors.some((error) => error.includes('destination.address')));
  });

  it('has a sandbox for each approved carrier with its own identity', async () => {
    assert.deepEqual(SANDBOX_CARRIER_IDS.sort(), [
      'EXPRESS_COURIER',
      'POST_PISHTAZ',
      'TIPAX_PAY_ON_DELIVERY',
    ]);
    const prefixes = new Set<string>();
    for (const carrierId of SANDBOX_CARRIER_IDS) {
      const adapter = sandboxCarrierFor(carrierId);
      assert.ok(adapter, `${carrierId} must have an adapter`);
      const result = await adapter.createShipment(
        request({
          carrierId,
          shipmentKey: shipmentKey('order-sandbox-1', carrierId, PARCEL),
        }),
      );
      assert.equal(result.ok, true);
      if (!result.ok) continue;
      assert.equal(result.dryRun, true);
      assert.equal(result.carrierId, carrierId);
      assert.ok(result.trackingNumber.includes('SANDBOX'));
      prefixes.add(result.trackingNumber.split('-')[1] ?? '');
      if (carrierId === 'EXPRESS_COURIER') assert.ok(result.pickupPoint);
      if (carrierId === 'TIPAX_PAY_ON_DELIVERY') assert.ok(result.barcode.length > 0);
    }
    assert.equal(prefixes.size, 3, 'every carrier has a distinct tracking prefix');
  });

  it('refuses a mismatched carrier request instead of booking under another id', async () => {
    const adapter = sandboxCarrierFor('POST_PISHTAZ');
    assert.ok(adapter);
    const result = await adapter.createShipment(request({ carrierId: 'TIPAX_PAY_ON_DELIVERY' }));
    assert.equal(result.ok, false);
    assert.equal(!result.ok && result.error.kind, 'INVALID_REQUEST');
    assert.equal(!result.ok && result.error.retryable, false);
  });

  it('times out once with a retryable typed error', async () => {
    const adapter: CarrierAdapter = {
      carrierId: 'POST_PISHTAZ',
      displayName: 'slow',
      createShipment: () => new Promise(() => undefined),
    };
    const result = await createShipmentWithRetry(adapter, request(), {
      timeoutMs: 5,
      maxRetries: 0,
    });
    assert.equal(result.ok, false);
    assert.equal(!result.ok && result.error.kind, 'TIMEOUT');
    assert.equal(!result.ok && result.error.retryable, true);
  });

  it('retries a transient failure and stops after success', async () => {
    const adapter = scriptedAdapter([transientFailure(), SUCCESS]);
    const result = await createShipmentWithRetry(adapter, request(), {
      maxRetries: 2,
      sleep: async () => undefined,
    });
    assert.equal(result.ok, true);
    assert.equal(adapter.calls, 2);
  });

  it('does not retry a refusal and never falls back to another carrier', async () => {
    const adapter = scriptedAdapter([
      {
        ok: false,
        error: {
          kind: 'REFUSED',
          code: 'CARRIER_REFUSED',
          retryable: false,
          message: 'refused',
        },
      },
    ]);
    const result = await createShipmentWithRetry(adapter, request(), {
      maxRetries: 2,
      sleep: async () => undefined,
    });
    assert.equal(result.ok, false);
    assert.equal(!result.ok && result.error.code, 'CARRIER_REFUSED');
    assert.equal(adapter.calls, 1, 'a refusal is not retried');
    assert.equal(adapter.carrierId, 'POST_PISHTAZ', 'the same adapter owns the failure');
  });
});
