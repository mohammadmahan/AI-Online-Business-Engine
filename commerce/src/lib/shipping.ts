import type { ShippingMethod } from '@/contracts/storefront';

/**
 * D-175 / MCS-02 — the ONE declarative carrier registry.
 *
 * This module is client-safe on purpose: checkout must render the same
 * enablement, priority, coverage and price that the server will enforce. Real
 * carrier calls do not live here; they sit behind `server/shipping/*` and are
 * sandbox-only today.
 *
 * The three ids are the existing stable shipping-method ids, so no historical
 * order value is renamed. Their customer-facing identities are the owner's
 * approved carriers: Iran Post, Tipax and local courier.
 */

export type ShippingCoverage =
  | { type: 'NATIONWIDE' }
  | { type: 'CITIES'; cities: readonly string[] };

export type ShippingPriceRule =
  | { type: 'FLAT'; amount: number }
  | { type: 'PER_KG'; base: number; perKg: number }
  | { type: 'FREE' }
  | { type: 'CASH_ON_DELIVERY' };

export interface ShippingCapabilities {
  tracking: boolean;
  barcode: boolean;
  cashOnDelivery: boolean;
  pickupPoint: boolean;
}

export interface ShippingDeliveryEstimate {
  minDays: number;
  maxDays: number;
  label: string;
}

export interface ShippingCarrier {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  coverage: ShippingCoverage;
  limits: {
    maxWeightGrams: number;
    maxLengthCm: number;
    maxWidthCm: number;
    maxHeightCm: number;
  };
  pricing: ShippingPriceRule;
  deliveryEstimate: ShippingDeliveryEstimate;
  capabilities: ShippingCapabilities;
  description: string;
}

export interface ShippingParcelPolicy {
  packagingGrams: number;
  gramsPerItem: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
  maxItems: number;
}

export interface ShippingConfig {
  version: 1;
  parcelPolicy: ShippingParcelPolicy;
  carriers: ShippingCarrier[];
}

export interface ParcelEstimate {
  weightGrams: number;
  lengthCm: number;
  widthCm: number;
  heightCm: number;
}

export interface ShippingQuoteInput {
  address: string;
  parcel: ParcelEstimate;
}

export interface ShippingQuote {
  carrierId: string;
  carrierName: string;
  amount: number;
  priority: number;
  deliveryEstimate: ShippingDeliveryEstimate;
  capabilities: ShippingCapabilities;
}

export type ShippingRefusalCode =
  | 'SHIPPING_UNKNOWN'
  | 'SHIPPING_DISABLED'
  | 'SHIPPING_INELIGIBLE';

export type ShippingQuoteResult =
  | { ok: true; quote: ShippingQuote }
  | { ok: false; code: ShippingRefusalCode; message: string };

/** Named so a bad environment is distinguishable from a bad request. */
export class ShippingConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ShippingConfigError';
  }
}

export const NO_ELIGIBLE_CARRIER_MESSAGE =
  'هیچ روش ارسالی برای این نشانی و سبد خرید موجود نیست.';

/** Historical orders predate carrier persistence; never invent a carrier. */
export const LEGACY_CARRIER_LABEL = 'ثبت‌نشده (سفارش قدیمی)';

/**
 * Local commercial placeholders, NOT carrier quotations or legal rates.
 * Coverage uses visible province/city names because checkout collects one
 * free-text address; a city-limited carrier is hidden until it matches.
 */
export const DEFAULT_SHIPPING_CONFIG: ShippingConfig = {
  version: 1,
  parcelPolicy: {
    packagingGrams: 250,
    gramsPerItem: 450,
    lengthCm: 35,
    widthCm: 30,
    heightCm: 10,
    maxItems: 20,
  },
  carriers: [
    {
      id: 'POST_PISHTAZ',
      name: 'پست ایران (پیشتاز)',
      enabled: true,
      priority: 10,
      coverage: { type: 'NATIONWIDE' },
      limits: {
        maxWeightGrams: 30_000,
        maxLengthCm: 150,
        maxWidthCm: 150,
        maxHeightCm: 150,
      },
      pricing: { type: 'FLAT', amount: 45_000 },
      deliveryEstimate: { minDays: 3, maxDays: 5, label: '۳ تا ۵ روز کاری' },
      capabilities: {
        tracking: true,
        barcode: true,
        cashOnDelivery: false,
        pickupPoint: false,
      },
      description: 'تحویل ۳ تا ۵ روز کاری در سراسر ایران.',
    },
    {
      id: 'TIPAX_PAY_ON_DELIVERY',
      name: 'تیپاکس',
      enabled: true,
      priority: 20,
      coverage: { type: 'NATIONWIDE' },
      limits: {
        maxWeightGrams: 30_000,
        maxLengthCm: 150,
        maxWidthCm: 150,
        maxHeightCm: 150,
      },
      pricing: { type: 'CASH_ON_DELIVERY' },
      deliveryEstimate: { minDays: 2, maxDays: 4, label: '۲ تا ۴ روز کاری' },
      capabilities: {
        tracking: true,
        barcode: true,
        cashOnDelivery: true,
        pickupPoint: false,
      },
      description: 'هزینهٔ ارسال هنگام تحویل به تیپاکس پرداخت می‌شود.',
    },
    {
      id: 'EXPRESS_COURIER',
      name: 'پیک محلی',
      enabled: true,
      priority: 30,
      coverage: {
        type: 'CITIES',
        cities: ['تهران', 'کرج', 'البرز', 'شهریار', 'اسلامشهر'],
      },
      limits: {
        maxWeightGrams: 15_000,
        maxLengthCm: 100,
        maxWidthCm: 100,
        maxHeightCm: 100,
      },
      pricing: { type: 'FLAT', amount: 90_000 },
      deliveryEstimate: { minDays: 1, maxDays: 2, label: '۱ تا ۲ روز کاری' },
      capabilities: {
        tracking: true,
        barcode: false,
        cashOnDelivery: false,
        pickupPoint: true,
      },
      description: 'تحویل سریع در تهران، کرج و شهرهای اطراف.',
    },
  ],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function positiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

/** Returns every problem instead of failing at the first one. */
export function validateShippingConfig(input: unknown): string[] {
  const errors: string[] = [];
  if (!isRecord(input)) return ['shipping config must be an object'];
  if (input.version !== 1) errors.push('version must be 1');

  const policy = input.parcelPolicy;
  if (!isRecord(policy)) {
    errors.push('parcelPolicy must be an object');
  } else {
    for (const key of ['packagingGrams', 'gramsPerItem'] as const) {
      if (!nonNegativeInteger(policy[key])) errors.push(`parcelPolicy.${key} must be a non-negative integer`);
    }
    for (const key of ['lengthCm', 'widthCm', 'heightCm', 'maxItems'] as const) {
      if (!positiveInteger(policy[key])) errors.push(`parcelPolicy.${key} must be a positive integer`);
    }
  }

  if (!Array.isArray(input.carriers) || input.carriers.length === 0) {
    errors.push('carriers must be a non-empty array');
    return errors;
  }

  const ids = new Set<string>();
  const priorities = new Set<number>();
  input.carriers.forEach((raw, index) => {
    const at = `carriers[${index}]`;
    if (!isRecord(raw)) {
      errors.push(`${at} must be an object`);
      return;
    }
    if (typeof raw.id !== 'string' || !/^[A-Z][A-Z0-9_]{1,63}$/.test(raw.id)) {
      errors.push(`${at}.id must be an uppercase stable id`);
    } else if (ids.has(raw.id)) {
      errors.push(`${at}.id is duplicated`);
    } else {
      ids.add(raw.id);
    }
    if (typeof raw.name !== 'string' || raw.name.trim().length === 0) {
      errors.push(`${at}.name must be non-empty`);
    }
    if (typeof raw.enabled !== 'boolean') errors.push(`${at}.enabled must be boolean`);
    if (!positiveInteger(raw.priority)) {
      errors.push(`${at}.priority must be a positive integer`);
    } else if (priorities.has(raw.priority)) {
      errors.push(`${at}.priority is duplicated`);
    } else {
      priorities.add(raw.priority);
    }

    const coverage = raw.coverage;
    if (!isRecord(coverage)) {
      errors.push(`${at}.coverage must be an object`);
    } else if (coverage.type === 'CITIES') {
      if (
        !Array.isArray(coverage.cities) ||
        coverage.cities.length === 0 ||
        coverage.cities.some((city) => typeof city !== 'string' || city.trim().length === 0)
      ) {
        errors.push(`${at}.coverage.cities must be a non-empty string array`);
      }
    } else if (coverage.type !== 'NATIONWIDE') {
      errors.push(`${at}.coverage.type must be NATIONWIDE or CITIES`);
    }

    const limits = raw.limits;
    if (!isRecord(limits)) {
      errors.push(`${at}.limits must be an object`);
    } else {
      for (const key of ['maxWeightGrams', 'maxLengthCm', 'maxWidthCm', 'maxHeightCm'] as const) {
        if (!positiveInteger(limits[key])) errors.push(`${at}.limits.${key} must be a positive integer`);
      }
    }

    const pricing = raw.pricing;
    if (!isRecord(pricing)) {
      errors.push(`${at}.pricing must be an object`);
    } else if (pricing.type === 'FLAT') {
      if (!nonNegativeInteger(pricing.amount)) errors.push(`${at}.pricing.amount must be non-negative integer Toman`);
    } else if (pricing.type === 'PER_KG') {
      if (!nonNegativeInteger(pricing.base)) errors.push(`${at}.pricing.base must be non-negative integer Toman`);
      if (!positiveInteger(pricing.perKg)) errors.push(`${at}.pricing.perKg must be a positive integer`);
    } else if (pricing.type !== 'FREE' && pricing.type !== 'CASH_ON_DELIVERY') {
      errors.push(`${at}.pricing.type is unsupported`);
    }

    const eta = raw.deliveryEstimate;
    if (!isRecord(eta)) {
      errors.push(`${at}.deliveryEstimate must be an object`);
    } else {
      if (!positiveInteger(eta.minDays)) errors.push(`${at}.deliveryEstimate.minDays must be positive`);
      if (!positiveInteger(eta.maxDays)) errors.push(`${at}.deliveryEstimate.maxDays must be positive`);
      if (typeof eta.label !== 'string' || eta.label.trim().length === 0) {
        errors.push(`${at}.deliveryEstimate.label must be non-empty`);
      }
      if (positiveInteger(eta.minDays) && positiveInteger(eta.maxDays) && eta.minDays > eta.maxDays) {
        errors.push(`${at}.deliveryEstimate.minDays must be <= maxDays`);
      }
    }

    const caps = raw.capabilities;
    if (!isRecord(caps)) {
      errors.push(`${at}.capabilities must be an object`);
    } else {
      for (const key of ['tracking', 'barcode', 'cashOnDelivery', 'pickupPoint'] as const) {
        if (typeof caps[key] !== 'boolean') errors.push(`${at}.capabilities.${key} must be boolean`);
      }
    }

    if (typeof raw.description !== 'string' || raw.description.trim().length === 0) {
      errors.push(`${at}.description must be non-empty`);
    }
  });

  return errors;
}

export function assertValidShippingConfig(input: unknown): ShippingConfig {
  const errors = validateShippingConfig(input);
  if (errors.length > 0) {
    throw new ShippingConfigError(`Invalid shipping configuration: ${errors.join('; ')}`);
  }
  return input as ShippingConfig;
}

/** The base registry validated once at module load: a typo cannot ship. */
export const VALIDATED_DEFAULT_SHIPPING_CONFIG = assertValidShippingConfig(DEFAULT_SHIPPING_CONFIG);

export interface ShippingOverrides {
  /** Raw comma list. `undefined` keeps registry flags; `none` disables all. */
  enabled?: string;
  /** Raw comma list; reorders the listed carriers first, by this order. */
  priority?: string;
}

function parseIdList(raw: string): string[] {
  return raw
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

/**
 * Applies environment-level enablement/priority to a validated base config.
 * This is the ONLY place modes are decided; checkout and order code never
 * branch on a carrier list.
 */
export function applyShippingOverrides(
  base: ShippingConfig,
  overrides: ShippingOverrides,
): ShippingConfig {
  const known = new Set(base.carriers.map((carrier) => carrier.id));
  let carriers = base.carriers.map((carrier) => ({ ...carrier }));

  if (overrides.enabled !== undefined) {
    const raw = overrides.enabled.trim().toLowerCase();
    if (raw === 'none') {
      carriers = carriers.map((carrier) => ({ ...carrier, enabled: false }));
    } else {
      const ids = parseIdList(overrides.enabled);
      if (ids.length === 0) {
        throw new ShippingConfigError('COMMERCE_SHIPPING_ENABLED is set but names no carrier');
      }
      for (const id of ids) {
        if (!known.has(id)) {
          throw new ShippingConfigError(`COMMERCE_SHIPPING_ENABLED names an unknown carrier: ${id}`);
        }
      }
      const enabled = new Set(ids);
      carriers = carriers.map((carrier) => ({ ...carrier, enabled: enabled.has(carrier.id) }));
    }
  }

  if (overrides.priority !== undefined) {
    const ids = parseIdList(overrides.priority);
    if (ids.length === 0) {
      throw new ShippingConfigError('COMMERCE_SHIPPING_PRIORITY is set but names no carrier');
    }
    const seen = new Set<string>();
    for (const id of ids) {
      if (!known.has(id)) {
        throw new ShippingConfigError(`COMMERCE_SHIPPING_PRIORITY names an unknown carrier: ${id}`);
      }
      if (seen.has(id)) {
        throw new ShippingConfigError(`COMMERCE_SHIPPING_PRIORITY repeats a carrier: ${id}`);
      }
      seen.add(id);
    }
    const order = [...ids, ...carriers.map((carrier) => carrier.id).filter((id) => !seen.has(id))];
    carriers = order.map((id, index) => ({
      ...(carriers.find((carrier) => carrier.id === id) as ShippingCarrier),
      priority: (index + 1) * 10,
    }));
  }

  carriers.sort((a, b) => a.priority - b.priority || a.id.localeCompare(b.id));
  return assertValidShippingConfig({ ...base, carriers });
}

/**
 * Estimated parcel, not a measured one: commerce has no per-SKU weight yet.
 * The policy is registry data and the result is validated against carrier
 * limits; a future weight source replaces this function, not its callers.
 */
export function estimateParcel(policy: ShippingParcelPolicy, totalQuantity: number): ParcelEstimate | null {
  if (!Number.isSafeInteger(totalQuantity) || totalQuantity <= 0 || totalQuantity > policy.maxItems) {
    return null;
  }
  return {
    weightGrams: policy.packagingGrams + totalQuantity * policy.gramsPerItem,
    lengthCm: policy.lengthCm,
    widthCm: policy.widthCm,
    heightCm: policy.heightCm,
  };
}

function normalized(value: string): string {
  return value.replace(/\u064a/g, 'ی').replace(/\u0643/g, 'ک').replace(/\s+/g, ' ').trim();
}

function coverageMatches(carrier: ShippingCarrier, address: string): boolean {
  if (carrier.coverage.type === 'NATIONWIDE') return true;
  const haystack = normalized(address);
  return carrier.coverage.cities.some((city) => haystack.includes(normalized(city)));
}

function priceFor(rule: ShippingPriceRule, weightGrams: number): number {
  if (rule.type === 'FLAT') return rule.amount;
  if (rule.type === 'PER_KG') {
    return rule.base + Math.ceil(weightGrams / 1000) * rule.perKg;
  }
  return 0;
}

function limitsAllow(carrier: ShippingCarrier, parcel: ParcelEstimate): boolean {
  return (
    parcel.weightGrams <= carrier.limits.maxWeightGrams &&
    parcel.lengthCm <= carrier.limits.maxLengthCm &&
    parcel.widthCm <= carrier.limits.maxWidthCm &&
    parcel.heightCm <= carrier.limits.maxHeightCm
  );
}

/** Authoritative quote for ONE carrier. Never swaps in another on refusal. */
export function quoteShipping(
  config: ShippingConfig,
  carrierId: string,
  input: ShippingQuoteInput,
): ShippingQuoteResult {
  const carrier = config.carriers.find((entry) => entry.id === carrierId);
  if (!carrier) {
    return { ok: false, code: 'SHIPPING_UNKNOWN', message: 'روش ارسال انتخابی معتبر نیست.' };
  }
  if (!carrier.enabled) {
    return {
      ok: false,
      code: 'SHIPPING_DISABLED',
      message: 'این روش ارسال در حال حاضر غیرفعال است؛ روش دیگری انتخاب کنید.',
    };
  }
  if (!limitsAllow(carrier, input.parcel)) {
    return {
      ok: false,
      code: 'SHIPPING_INELIGIBLE',
      message: 'ابعاد یا وزن سبد خرید برای این روش ارسال مناسب نیست.',
    };
  }
  if (!coverageMatches(carrier, input.address)) {
    return {
      ok: false,
      code: 'SHIPPING_INELIGIBLE',
      message: 'این روش ارسال به نشانی انتخابی ارائه نمی‌شود.',
    };
  }
  return {
    ok: true,
    quote: {
      carrierId: carrier.id,
      carrierName: carrier.name,
      amount: priceFor(carrier.pricing, input.parcel.weightGrams),
      priority: carrier.priority,
      deliveryEstimate: carrier.deliveryEstimate,
      capabilities: carrier.capabilities,
    },
  };
}

/** Enabled + eligible carriers only, in registry priority order. */
export function eligibleShippingOptions(
  config: ShippingConfig,
  input: ShippingQuoteInput,
): ShippingQuote[] {
  return config.carriers
    .filter((carrier) => carrier.enabled)
    .map((carrier) => quoteShipping(config, carrier.id, input))
    .filter((result): result is { ok: true; quote: ShippingQuote } => result.ok)
    .map((result) => result.quote)
    .sort((a, b) => a.priority - b.priority || a.carrierId.localeCompare(b.carrierId));
}

/* ------------------------------------------------------- compatibility view */

/**
 * The pre-MCS public view, retained for callers/tests that only need the base
 * catalogue. Checkout uses `eligibleShippingOptions`/`quoteShipping` instead.
 */
export const SHIPPING_METHODS: ShippingMethod[] = VALIDATED_DEFAULT_SHIPPING_CONFIG.carriers.map(
  (carrier) => ({
    id: carrier.id,
    label: carrier.name,
    amount:
      carrier.pricing.type === 'FLAT'
        ? carrier.pricing.amount
        : carrier.pricing.type === 'PER_KG'
          ? carrier.pricing.base
          : 0,
    description: carrier.description,
  }),
);

export const DEFAULT_SHIPPING_METHOD_ID = 'POST_PISHTAZ';

export function shippingMethodById(id: string): ShippingMethod | undefined {
  return SHIPPING_METHODS.find((method) => method.id === id);
}

/**
 * Base amount for the DEFAULT registry only. It does not check enablement,
 * destination or parcel limits; the authoritative checkout path is
 * `quoteShipping`. Unknown ids still return null so no caller prices a typo as 0.
 */
export function shippingAmountFor(id: string): number | null {
  const carrier = VALIDATED_DEFAULT_SHIPPING_CONFIG.carriers.find((entry) => entry.id === id);
  if (!carrier) return null;
  if (carrier.pricing.type === 'FLAT') return carrier.pricing.amount;
  if (carrier.pricing.type === 'PER_KG') return carrier.pricing.base;
  return 0;
}
