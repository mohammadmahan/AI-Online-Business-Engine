import type {
  ProductCreatePayload,
  VariantPayload,
} from '@/contracts/catalog';
import type { CouponCreatePayload } from '@/contracts/promotions';

/**
 * D-172 Phase 2 — fail-closed validation for every write the merchant panel can
 * make (D-171 §2.2 discipline: invalid or missing input is REFUSED, never
 * normalised into something that looks fine).
 *
 * Pure module: no I/O, no environment, no React — so every rule here is unit
 * tested directly (`src/server/validation.test.ts`).
 *
 * Messages are Persian because they are shown to the boutique owner verbatim;
 * the machine-readable `field` stays in English for the UI to anchor on.
 */

export interface ValidationIssue {
  field: string;
  message: string;
}

export type Validation = { ok: true } | { ok: false; issues: ValidationIssue[] };

/** D-114 money ceiling — the canonical limit, stated once. */
export const MAX_MONEY_TOMAN = 1_000_000_000_000;

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const SKU_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/;
const COUPON_RE = /^[A-Z0-9][A-Z0-9._-]{2,31}$/;
const TRACKING_RE = /^[A-Za-z0-9-]{8,24}$/;

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

/** Integer Toman, 0 ≤ value ≤ the D-114 ceiling. Rejects floats by design. */
export function isMoney(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= 0 &&
    value <= MAX_MONEY_TOMAN
  );
}

export function isPositiveMoney(value: unknown): value is number {
  return isMoney(value) && value > 0;
}

export function isStock(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 1_000_000;
}

export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && HEX_RE.test(value);
}

export function normalizeSku(value: string): string {
  return value.trim().toUpperCase();
}

export function normalizeCouponCode(value: string): string {
  return value.trim().toUpperCase();
}

/**
 * Parse an ISO-8601 instant from a form/JSON value.
 *
 * Returns `undefined` for "present but invalid" and `null` for "absent", so the
 * caller can tell the two apart — an empty date field is fine, a typo is not.
 */
export function parseInstant(value: string | null | undefined): Date | null | undefined {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

function issue(field: string, message: string): ValidationIssue {
  return { field, message };
}

function fromIssues(issues: ValidationIssue[]): Validation {
  return issues.length === 0 ? { ok: true } : { ok: false, issues };
}

/* --------------------------------------------------------------- §2.1 input */

export function validateVariant(variant: VariantPayload, index: number): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const at = `variants.${index}`;

  if (!isNonEmptyString(variant.sku)) {
    issues.push(issue(`${at}.sku`, 'کد کالا (SKU) الزامی است.'));
  } else if (!SKU_RE.test(normalizeSku(variant.sku))) {
    issues.push(
      issue(`${at}.sku`, 'کد کالا باید ۲ تا ۶۴ نویسهٔ لاتین، رقم، نقطه، خط تیره یا زیرخط باشد.'),
    );
  }
  if (!isNonEmptyString(variant.colorName)) {
    issues.push(issue(`${at}.colorName`, 'نام رنگ الزامی است.'));
  }
  if (!isHexColor(variant.colorHex)) {
    issues.push(issue(`${at}.colorHex`, 'کد رنگ باید در قالب #RRGGBB باشد.'));
  }
  if (!isNonEmptyString(variant.size)) {
    issues.push(issue(`${at}.size`, 'اندازه (سایز) الزامی است.'));
  }
  if (variant.stockQuantity !== undefined && !isStock(variant.stockQuantity)) {
    issues.push(issue(`${at}.stockQuantity`, 'موجودی باید عدد صحیح و نامنفی باشد.'));
  }
  if (
    variant.priceOverride !== undefined &&
    variant.priceOverride !== null &&
    !isMoney(variant.priceOverride)
  ) {
    issues.push(issue(`${at}.priceOverride`, 'قیمت اختصاصی باید عدد صحیح و نامنفی به تومان باشد.'));
  }
  return issues;
}

/**
 * Validates a whole product submission (§2.1): product fields, the variant
 * matrix, media flags and the two uniqueness rules the database also enforces —
 * unique SKU, and one row per colour × size. Catching them here turns a
 * constraint violation into a field-level message.
 */
export function validateProduct(payload: ProductCreatePayload): Validation {
  const issues: ValidationIssue[] = [];

  if (!isNonEmptyString(payload.title)) {
    issues.push(issue('title', 'عنوان محصول الزامی است.'));
  } else if (payload.title.trim().length > 500) {
    issues.push(issue('title', 'عنوان محصول بیش از ۵۰۰ نویسه است.'));
  }
  if (!isNonEmptyString(payload.slug) || !SLUG_RE.test(payload.slug.trim())) {
    issues.push(
      issue('slug', 'نشانی محصول باید با حروف کوچک لاتین، عدد و خط تیره نوشته شود (مثال: manto-keti).'),
    );
  }
  if (!isNonEmptyString(payload.categoryId)) {
    issues.push(issue('categoryId', 'دستهٔ محصول را انتخاب کنید.'));
  }
  if (!isMoney(payload.basePrice) || payload.basePrice <= 0) {
    issues.push(issue('basePrice', 'قیمت پایه باید عدد صحیح و بزرگ‌تر از صفر به تومان باشد.'));
  }
  if (payload.discountPrice !== undefined && payload.discountPrice !== null) {
    if (!isPositiveMoney(payload.discountPrice)) {
      issues.push(issue('discountPrice', 'قیمت تخفیف‌دار باید عدد صحیح و بزرگ‌تر از صفر باشد.'));
    } else if (isMoney(payload.basePrice) && payload.discountPrice > payload.basePrice) {
      issues.push(issue('discountPrice', 'قیمت تخفیف‌دار نمی‌تواند از قیمت پایه بیشتر باشد.'));
    }
  }
  if (!isNonEmptyString(payload.descriptionRaw)) {
    issues.push(issue('descriptionRaw', 'توضیح خام محصول (ورودی موتور هوش مصنوعی) الزامی است.'));
  }
  if (!isNonEmptyString(payload.fabricType)) {
    issues.push(issue('fabricType', 'نوع پارچه الزامی است.'));
  }
  if (!isNonEmptyString(payload.season)) {
    issues.push(issue('season', 'فصل الزامی است.'));
  }
  if (!Array.isArray(payload.variants) || payload.variants.length === 0) {
    issues.push(issue('variants', 'حداقل یک ترکیب رنگ و سایز لازم است.'));
  } else {
    payload.variants.forEach((variant, index) => {
      issues.push(...validateVariant(variant, index));
    });

    const skus = payload.variants.map((variant) => normalizeSku(variant.sku ?? ''));
    if (dupes(skus).length > 0) {
      issues.push(issue('variants', 'کد کالا (SKU) در سطرهای ماتریس تکراری است.'));
    }
    const cells = payload.variants.map(
      (variant) => `${variant.size?.trim()}::${variant.colorName?.trim()}`,
    );
    if (dupes(cells).length > 0) {
      issues.push(issue('variants', 'ترکیب رنگ و سایز تکراری است؛ هر ترکیب فقط یک سطر دارد.'));
    }
  }

  const images = payload.images ?? [];
  const primaries = images.filter((image) => image.isPrimary).length;
  if (primaries > 1) {
    issues.push(issue('images', 'فقط یک تصویر می‌تواند تصویر اصلی باشد.'));
  }
  images.forEach((image, index) => {
    if (!isNonEmptyString(image.storagePath) || !isNonEmptyString(image.publicUrl)) {
      issues.push(issue(`images.${index}`, 'مسیر ذخیره‌سازی و نشانی تصویر الزامی است.'));
    }
    if (
      image.variantId !== undefined &&
      image.variantId !== null &&
      isNonEmptyString(image.variantId)
    ) {
      issues.push(
        issue(
          `images.${index}.variantId`,
          'اتصال تصویر به گونه در فرم ارسال نمی‌شود؛ در این مرحله پیوند با رنگ انجام می‌شود.',
        ),
      );
    }
  });

  return fromIssues(issues);
}

/* --------------------------------------------------------------- §2.2 input */

export function validateStockValue(value: unknown): Validation {
  return isStock(value)
    ? { ok: true }
    : { ok: false, issues: [issue('stockQuantity', 'موجودی باید عدد صحیح و نامنفی باشد.')] };
}

export function validatePriceOverride(value: unknown): Validation {
  if (value === null) {
    return { ok: true };
  }
  return isMoney(value)
    ? { ok: true }
    : { ok: false, issues: [issue('priceOverride', 'قیمت اختصاصی باید عدد صحیح و نامنفی به تومان باشد.')] };
}

/* --------------------------------------------------------------- §2.3 input */

export function validateTrackingCode(value: unknown): Validation {
  return typeof value === 'string' && TRACKING_RE.test(value.trim())
    ? { ok: true }
    : {
        ok: false,
        issues: [issue('trackingCode', 'کد رهگیری پستی باید ۸ تا ۲۴ نویسهٔ لاتین، رقم یا خط تیره باشد.')],
      };
}

/* --------------------------------------------------------------- §2.4 input */

export function validateCoupon(payload: CouponCreatePayload, now = new Date()): Validation {
  const issues: ValidationIssue[] = [];
  const code = isNonEmptyString(payload.code) ? normalizeCouponCode(payload.code) : '';

  if (!code || !COUPON_RE.test(code)) {
    issues.push(issue('code', 'کد تخفیف باید ۳ تا ۳۲ نویسهٔ لاتین بزرگ، رقم، نقطه، خط تیره یا زیرخط باشد.'));
  }
  if (payload.discountType !== 'PERCENT' && payload.discountType !== 'FIXED') {
    issues.push(issue('discountType', 'نوع تخفیف باید درصدی یا مبلغ ثابت باشد.'));
  } else if (payload.discountType === 'PERCENT') {
    if (
      typeof payload.discountValue !== 'number' ||
      !Number.isInteger(payload.discountValue) ||
      payload.discountValue < 1 ||
      payload.discountValue > 100
    ) {
      issues.push(issue('discountValue', 'درصد تخفیف باید عدد صحیح بین ۱ تا ۱۰۰ باشد.'));
    }
  } else if (!isPositiveMoney(payload.discountValue)) {
    issues.push(issue('discountValue', 'مبلغ تخفیف ثابت باید عدد صحیح و بزرگ‌تر از صفر به تومان باشد.'));
  }

  if (payload.minSpend !== undefined && !isMoney(payload.minSpend)) {
    issues.push(issue('minSpend', 'حداقل مبلغ خرید باید عدد صحیح و نامنفی به تومان باشد.'));
  }
  if (payload.usageLimit !== undefined && payload.usageLimit !== null) {
    if (
      typeof payload.usageLimit !== 'number' ||
      !Number.isInteger(payload.usageLimit) ||
      payload.usageLimit < 1
    ) {
      issues.push(issue('usageLimit', 'سقف استفاده باید عدد صحیح و بزرگ‌تر از صفر باشد (یا خالی بماند).'));
    }
  }
  const expiresAt = parseInstant(payload.expiresAt);
  if (expiresAt === undefined) {
    issues.push(issue('expiresAt', 'تاریخ انقضا معتبر نیست.'));
  } else if (expiresAt !== null && expiresAt.getTime() <= now.getTime()) {
    issues.push(issue('expiresAt', 'تاریخ انقضا باید در آینده باشد.'));
  }

  return fromIssues(issues);
}

/* --------------------------------------------------------------- §3.4 input */

const PERSIAN_DIGITS_RE = /[\u06F0-\u06F9]/g;
const ARABIC_INDIC_DIGITS_RE = /[\u0660-\u0669]/g;

/**
 * Latin digits from whatever the customer's keyboard produced.
 *
 * Persian and Arabic-Indic numerals are the DEFAULT on many Iranian phones, so
 * a phone number typed as «۰۹۱۲…» must not be rejected as malformed. This
 * normalises the three digit sets — and only those — leaving every other
 * character for the validators below to judge.
 */
export function normalizeDigits(value: string): string {
  return value
    .replace(PERSIAN_DIGITS_RE, (digit) => String(digit.charCodeAt(0) - 0x06f0))
    .replace(ARABIC_INDIC_DIGITS_RE, (digit) => String(digit.charCodeAt(0) - 0x0660));
}

const MOBILE_RE = /^09\d{9}$/;
const POSTAL_RE = /^\d{10}$/;

/** Iranian mobile number (`09xxxxxxxxx`) after digit and separator normalisation. */
export function normalizePhoneNumber(value: string): string {
  return normalizeDigits(value).replace(/[\s\-()]/g, '');
}

export function validatePhoneNumber(value: unknown): Validation {
  if (typeof value !== 'string') {
    return { ok: false, issues: [issue('phoneNumber', 'شمارهٔ موبایل الزامی است.')] };
  }
  const normalized = normalizePhoneNumber(value);
  if (!MOBILE_RE.test(normalized)) {
    return {
      ok: false,
      issues: [issue('phoneNumber', 'شمارهٔ موبایل باید ۱۱ رقم و با ۰۹ شروع شود (مثال: ۰۹۱۲۰۰۰۰۰۰۰).')],
    };
  }
  return { ok: true };
}

/** Iranian postal code: exactly ten digits (IMEI-style separators tolerated). */
export function normalizePostalCode(value: string): string {
  return normalizeDigits(value).replace(/[\s\-]/g, '');
}

export function validatePostalCode(value: unknown): Validation {
  if (typeof value !== 'string') {
    return { ok: false, issues: [issue('postalCode', 'کد پستی الزامی است.')] };
  }
  if (!POSTAL_RE.test(normalizePostalCode(value))) {
    return { ok: false, issues: [issue('postalCode', 'کد پستی باید ۱۰ رقم باشد.')] };
  }
  return { ok: true };
}

function lengthIssue(field: string, label: string, value: unknown, min: number, max: number): ValidationIssue[] {
  if (!isNonEmptyString(value)) {
    return [issue(field, `${label} الزامی است.`)];
  }
  const trimmed = value.trim();
  if (trimmed.length < min) {
    return [issue(field, `${label} حداقل ${min} نویسه باشد.`)];
  }
  if (trimmed.length > max) {
    return [issue(field, `${label} بیش از ${max} نویسه است.`)];
  }
  return [];
}

export function validateCustomerName(value: unknown): Validation {
  return fromIssues(lengthIssue('fullName', 'نام و نام خانوادگی', value, 3, 120));
}

export function validateAddress(value: unknown): Validation {
  return fromIssues(lengthIssue('address', 'نشانی', value, 10, 500));
}

/**
 * One checkout submission (§3.4): the customer block only. Lines, coupon and
 * shipping are validated by `placeOrder`, which also re-resolves them against
 * the SSOT — format validation and stock/pricing authority are separate steps
 * on purpose.
 */
export function validateCheckoutCustomer(input: {
  fullName: unknown;
  phoneNumber: unknown;
  address: unknown;
  postalCode: unknown;
}): Validation {
  const results = [
    validateCustomerName(input.fullName),
    validatePhoneNumber(input.phoneNumber),
    validateAddress(input.address),
    validatePostalCode(input.postalCode),
  ];
  return fromIssues(results.flatMap((result) => (result.ok ? [] : result.issues)));
}

/* ------------------------------------------------------------------ helpers */

export function dupes(values: string[]): string[] {
  const seen = new Set<string>();
  const repeated = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) {
      repeated.add(value);
    }
    seen.add(value);
  }
  return [...repeated];
}

export function issuesToMessage(issues: ValidationIssue[]): string {
  return issues.map((entry) => entry.message).join(' ');
}
