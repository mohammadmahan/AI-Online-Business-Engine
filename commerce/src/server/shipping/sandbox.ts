import {
  type CarrierAdapter,
  type CarrierShipmentRequest,
  type CarrierShipmentResult,
  parcelHash,
  validateCarrierRequest,
} from './carrier-adapter';

/**
 * D-175 / MCS-05 — local sandbox adapters for the three approved carriers.
 *
 * No socket, credential, label purchase or durable shipment exists here. Each
 * adapter has a stable prefix and a deterministic tracking number derived from
 * the address-free parcel identity. Injected faults exist only for tests.
 */

export type SandboxFault = 'timeout' | 'partition' | 'refuse';

export interface SandboxCarrierOptions {
  /** Delays the promise, used by the timeout test. */
  delayMs?: number;
  fault?: SandboxFault;
}

interface SandboxProfile {
  carrierId: string;
  displayName: string;
  prefix: string;
  barcode: boolean;
  pickupPoint?: string;
}

const PROFILES: Record<string, SandboxProfile> = {
  POST_PISHTAZ: {
    carrierId: 'POST_PISHTAZ',
    displayName: 'پست ایران (پیشتاز)',
    prefix: 'SANDBOX-IRANPOST',
    barcode: true,
  },
  TIPAX_PAY_ON_DELIVERY: {
    carrierId: 'TIPAX_PAY_ON_DELIVERY',
    displayName: 'تیپاکس',
    prefix: 'SANDBOX-TIPAX',
    barcode: true,
  },
  EXPRESS_COURIER: {
    carrierId: 'EXPRESS_COURIER',
    displayName: 'پیک محلی',
    prefix: 'SANDBOX-LOCAL',
    barcode: false,
    pickupPoint: 'نقطهٔ تحویل محلی (نمایشی)',
  },
};

export const SANDBOX_CARRIER_IDS = Object.keys(PROFILES);

function failure(
  kind: 'TIMEOUT' | 'TRANSPORT' | 'REFUSED',
  code: string,
  message: string,
): CarrierShipmentResult {
  return {
    ok: false,
    error: {
      kind,
      code,
      retryable: kind === 'TIMEOUT' || kind === 'TRANSPORT',
      message,
    },
  };
}

class SandboxCarrier implements CarrierAdapter {
  readonly carrierId: string;
  readonly displayName: string;
  private readonly profile: SandboxProfile;
  private readonly options: SandboxCarrierOptions;

  constructor(profile: SandboxProfile, options: SandboxCarrierOptions) {
    this.profile = profile;
    this.carrierId = profile.carrierId;
    this.displayName = profile.displayName;
    this.options = options;
  }

  async createShipment(request: CarrierShipmentRequest): Promise<CarrierShipmentResult> {
    if (this.options.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, this.options.delayMs));
    }
    if (this.options.fault === 'timeout') {
      return failure('TIMEOUT', 'CARRIER_TIMEOUT', 'مهلت شرکت حمل به پایان رسید.');
    }
    if (this.options.fault === 'partition') {
      return failure('TRANSPORT', 'CARRIER_TRANSPORT_ERROR', 'ارتباط با شرکت حمل قطع شد.');
    }
    if (this.options.fault === 'refuse') {
      return failure('REFUSED', 'CARRIER_REFUSED', 'شرکت حمل این مرسوله را نپذیرفت.');
    }

    const errors = validateCarrierRequest(request);
    if (request.carrierId !== this.carrierId) {
      errors.push('request carrierId does not match this adapter');
    }
    if (errors.length > 0) {
      return {
        ok: false,
        error: {
          kind: 'INVALID_REQUEST',
          code: 'CARRIER_INVALID_REQUEST',
          retryable: false,
          message: `درخواست مرسوله معتبر نیست: ${errors.join('; ')}`,
        },
      };
    }

    const suffix = parcelHash(request.parcel).slice(0, 12).toUpperCase();
    return {
      ok: true,
      carrierId: this.carrierId,
      trackingNumber: `${this.profile.prefix}-${suffix}`,
      barcode: this.profile.barcode ? `BC-${suffix}` : '',
      labelReference: `${this.profile.prefix}-LABEL-${suffix}`,
      ...(this.profile.pickupPoint ? { pickupPoint: this.profile.pickupPoint } : {}),
      dryRun: true,
    };
  }
}

/** Returns the sandbox adapter for one approved carrier, or `null`. */
export function sandboxCarrierFor(
  carrierId: string,
  options: SandboxCarrierOptions = {},
): CarrierAdapter | null {
  const profile = PROFILES[carrierId];
  return profile ? new SandboxCarrier(profile, options) : null;
}
