import { createHash } from 'node:crypto';

/**
 * D-175 / MCS-05 — the ONE internal carrier adapter contract.
 *
 * Every adapter (sandbox today, a future owner-approved live adapter later)
 * receives the same request and returns the same success/failure union. There is
 * no provider SDK, credential or network call in this module. A failure is
 * returned to the caller; it is NEVER replaced by another carrier.
 */

export interface CarrierParcel {
  weightGrams: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
  declaredValueToman: number;
}

export interface CarrierShipmentRequest {
  orderId: string;
  carrierId: string;
  /** Deterministic identity, not a booking id. */
  shipmentKey: string;
  parcel: CarrierParcel;
  /** Needed to address the operation; deliberately not part of any hash. */
  destination: { address: string };
}

export type CarrierErrorKind =
  | 'TIMEOUT'
  | 'TRANSPORT'
  | 'REFUSED'
  | 'INVALID_REQUEST'
  | 'NOT_CONFIGURED';

export interface CarrierError {
  kind: CarrierErrorKind;
  code: string;
  retryable: boolean;
  message: string;
}

export interface CarrierShipmentSuccess {
  ok: true;
  carrierId: string;
  trackingNumber: string;
  barcode: string;
  labelReference: string;
  pickupPoint?: string;
  dryRun: true;
}

export interface CarrierShipmentFailure {
  ok: false;
  error: CarrierError;
}

export type CarrierShipmentResult = CarrierShipmentSuccess | CarrierShipmentFailure;

export interface CarrierAdapter {
  readonly carrierId: string;
  readonly displayName: string;
  createShipment(request: CarrierShipmentRequest): Promise<CarrierShipmentResult>;
}

/** D-114 ceilings mirrored from the canonical parcel boundary (D-162). */
export const MAX_PARCEL_WEIGHT_GRAMS = 100_000;
export const MAX_PARCEL_DIMENSION_CM = 150;
export const MAX_DECLARED_VALUE_TOMAN = 1_000_000_000_000;
export const DEFAULT_CARRIER_TIMEOUT_MS = 15_000;
export const MAX_CARRIER_RETRIES = 2;

export function validateCarrierRequest(request: CarrierShipmentRequest): string[] {
  const errors: string[] = [];
  if (typeof request.orderId !== 'string' || request.orderId.trim() === '') {
    errors.push('orderId must be non-empty');
  }
  if (typeof request.carrierId !== 'string' || request.carrierId.trim() === '') {
    errors.push('carrierId must be non-empty');
  }
  if (typeof request.shipmentKey !== 'string' || !/^[0-9a-f]{64}$/.test(request.shipmentKey)) {
    errors.push('shipmentKey must be a lowercase SHA-256 hex digest');
  }
  if (typeof request.destination?.address !== 'string' || request.destination.address.trim() === '') {
    errors.push('destination.address must be non-empty');
  }

  const parcel = request.parcel;
  if (!Number.isSafeInteger(parcel?.weightGrams) || parcel.weightGrams < 1 || parcel.weightGrams > MAX_PARCEL_WEIGHT_GRAMS) {
    errors.push(`weightGrams must be an integer 1..${MAX_PARCEL_WEIGHT_GRAMS}`);
  }
  for (const key of ['lengthCm', 'widthCm', 'heightCm'] as const) {
    const value = parcel?.[key];
    if (!Number.isSafeInteger(value) || value < 1 || value > MAX_PARCEL_DIMENSION_CM) {
      errors.push(`${key} must be an integer 1..${MAX_PARCEL_DIMENSION_CM}`);
    }
  }
  if (
    !Number.isSafeInteger(parcel?.declaredValueToman) ||
    parcel.declaredValueToman < 0 ||
    parcel.declaredValueToman > MAX_DECLARED_VALUE_TOMAN
  ) {
    errors.push(`declaredValueToman must be an integer 0..${MAX_DECLARED_VALUE_TOMAN}`);
  }
  return errors;
}

/** Address-free parcel identity, mirroring D-162's `parcel_hash`. */
export function parcelHash(parcel: CarrierParcel): string {
  return createHash('sha256')
    .update(
      JSON.stringify({
        weight_grams: parcel.weightGrams,
        length_cm: parcel.lengthCm,
        width_cm: parcel.widthCm,
        height_cm: parcel.heightCm,
        declared_value_toman: parcel.declaredValueToman,
      }),
    )
    .digest('hex');
}

/** Deterministic shipment key; no wall clock and no address. */
export function shipmentKey(orderId: string, carrierId: string, parcel: CarrierParcel): string {
  return createHash('sha256')
    .update(`${orderId}\u0000${carrierId}\u0000${parcelHash(parcel)}`)
    .digest('hex');
}

export interface CarrierRetryOptions {
  timeoutMs?: number;
  maxRetries?: number;
  /** Injected only in tests, so a retry loop does not sleep for seconds. */
  sleep?: (ms: number) => Promise<void>;
}

function timeoutFailure(): CarrierShipmentFailure {
  return {
    ok: false,
    error: {
      kind: 'TIMEOUT',
      code: 'CARRIER_TIMEOUT',
      retryable: true,
      message: 'ارتباط با شرکت حمل در زمان مجاز برقرار نشد؛ سفارش به حامل دیگری منتقل نشد.',
    },
  };
}

/**
 * Timeout + bounded retry around ONE adapter. Only TIMEOUT/TRANSPORT are
 * retried. No branch ever calls a different carrier.
 */
export async function createShipmentWithRetry(
  adapter: CarrierAdapter,
  request: CarrierShipmentRequest,
  options: CarrierRetryOptions = {},
): Promise<CarrierShipmentResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_CARRIER_TIMEOUT_MS;
  const maxRetries = options.maxRetries ?? MAX_CARRIER_RETRIES;
  const sleep = options.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)));
  let last: CarrierShipmentResult = timeoutFailure();

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      last = await Promise.race([
        adapter.createShipment(request),
        new Promise<CarrierShipmentResult>((resolve) => {
          setTimeout(() => resolve(timeoutFailure()), timeoutMs);
        }),
      ]);
    } catch (error) {
      last = {
        ok: false,
        error: {
          kind: 'TRANSPORT',
          code: 'CARRIER_TRANSPORT_ERROR',
          retryable: true,
          message: 'ارتباط با شرکت حمل قطع شد؛ سفارش به حامل دیگری منتقل نشد.',
        },
      };
      console.error('[commerce] carrier adapter threw', {
        carrierId: adapter.carrierId,
        name: error instanceof Error ? error.name : 'UnknownError',
      });
    }

    if (last.ok || !last.error.retryable) return last;
    if (attempt < maxRetries) {
      await sleep(50 * 2 ** attempt);
    }
  }

  return last;
}
