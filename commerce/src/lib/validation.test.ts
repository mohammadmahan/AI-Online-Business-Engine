import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { validProductPayload, variant } from '@/lib/validation.fixtures';
import {
  MAX_MONEY_TOMAN,
  isHexColor,
  isMoney,
  isStock,
  issuesToMessage,
  normalizeCouponCode,
  normalizeDigits,
  normalizePhoneNumber,
  normalizePostalCode,
  normalizeSku,
  parseInstant,
  validateAddress,
  validateCheckoutCustomer,
  validateCoupon,
  validateCustomerName,
  validatePhoneNumber,
  validatePostalCode,
  validatePriceOverride,
  validateProduct,
  validateStockValue,
  validateTrackingCode,
} from '@/lib/validation';

/** D-172 Phase 2 — one rule per test: an invalid input is refused, never normalised. */
describe('validation — money and primitives', () => {
  it('accepts only non-negative integers up to the D-114 ceiling', () => {
    assert.equal(isMoney(0), true);
    assert.equal(isMoney(1_250_000), true);
    assert.equal(isMoney(MAX_MONEY_TOMAN), true);
    assert.equal(isMoney(1.5), false);
    assert.equal(isMoney(-1), false);
    assert.equal(isMoney(MAX_MONEY_TOMAN + 1), false);
    assert.equal(isMoney('1250000'), false);
    assert.equal(isMoney(Number.NaN), false);
  });

  it('bounds stock and colour values', () => {
    assert.equal(isStock(0), true);
    assert.equal(isStock(-1), false);
    assert.equal(isStock(2.5), false);
    assert.equal(isHexColor('#111111'), true);
    assert.equal(isHexColor('#11111'), false);
    assert.equal(isHexColor('red'), false);
  });

  it('normalises SKUs and coupon codes to upper case', () => {
    assert.equal(normalizeSku(' manto-keti-36-1 '), 'MANTO-KETI-36-1');
    assert.equal(normalizeCouponCode(' norooz1405 '), 'NOROOZ1405');
  });

  it('tells an absent instant apart from an unparsable one', () => {
    assert.equal(parseInstant(null), null);
    assert.equal(parseInstant(''), null);
    assert.equal(parseInstant(undefined), null);
    assert.equal(parseInstant('not-a-date'), undefined);
    assert.equal(parseInstant('2027-01-01T00:00:00.000Z')?.toISOString(), '2027-01-01T00:00:00.000Z');
  });
});

describe('validation — product ingestion (§2.1)', () => {
  it('accepts a well-formed product with its variant matrix', () => {
    assert.deepEqual(validateProduct(validProductPayload()), { ok: true });
  });

  it('refuses a bad slug, colour, price or missing field', () => {
    assert.equal(validateProduct(validProductPayload({ slug: 'مانتو کتی' })).ok, false);
    assert.equal(validateProduct(validProductPayload({ title: '  ' })).ok, false);
    assert.equal(validateProduct(validProductPayload({ categoryId: '' })).ok, false);
    assert.equal(validateProduct(validProductPayload({ basePrice: 0 })).ok, false);
    assert.equal(validateProduct(validProductPayload({ basePrice: 10.5 })).ok, false);
    assert.equal(validateProduct(validProductPayload({ fabricType: '' })).ok, false);
    assert.equal(validateProduct(validProductPayload({ season: '' })).ok, false);
    assert.equal(validateProduct(validProductPayload({ descriptionRaw: '' })).ok, false);

    const badColor = validProductPayload({ variants: [variant({ colorHex: '111111' })] });
    const issues = validateProduct(badColor);
    assert.equal(issues.ok, false);
    assert.match(issuesToMessage(issues.ok ? [] : issues.issues), /#RRGGBB/);
  });

  it('refuses a discount price above the base price', () => {
    const payload = validProductPayload({ basePrice: 1_000_000, discountPrice: 1_100_000 });
    const result = validateProduct(payload);
    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.issues.some((issue) => issue.field === 'discountPrice'));
  });

  it('refuses duplicate SKUs and duplicate colour × size cells', () => {
    const duplicateSku = validateProduct(
      validProductPayload({
        variants: [variant(), variant({ size: '38' })],
      }),
    );
    assert.equal(duplicateSku.ok, false);

    const duplicateCell = validateProduct(
      validProductPayload({
        variants: [variant(), variant({ sku: 'MANTO-KETI-36-OTHER' })],
      }),
    );
    assert.equal(duplicateCell.ok, false);
    assert.match(
      issuesToMessage(duplicateCell.ok ? [] : duplicateCell.issues),
      /ترکیب رنگ و سایز تکراری/,
    );
  });

  it('requires at least one variant row', () => {
    const result = validateProduct(validProductPayload({ variants: [] }));
    assert.equal(result.ok, false);
  });

  it('refuses a second primary image and a variant-bound image from the form', () => {
    const twoPrimaries = validateProduct(
      validProductPayload({
        images: [
          { storagePath: 'a/1.jpg', publicUrl: 'https://cdn.example/1.jpg', isPrimary: true },
          { storagePath: 'a/2.jpg', publicUrl: 'https://cdn.example/2.jpg', isPrimary: true },
        ],
      }),
    );
    assert.equal(twoPrimaries.ok, false);

    const boundImage = validateProduct(
      validProductPayload({
        images: [
          {
            storagePath: 'a/1.jpg',
            publicUrl: 'https://cdn.example/1.jpg',
            isPrimary: true,
            variantId: 'variant-1',
          },
        ],
      }),
    );
    assert.equal(boundImage.ok, false);
  });
});

describe('validation — inventory writes (§2.2)', () => {
  it('accepts a whole non-negative stock value and refuses everything else', () => {
    assert.deepEqual(validateStockValue(0), { ok: true });
    assert.deepEqual(validateStockValue(12), { ok: true });
    assert.equal(validateStockValue(-1).ok, false);
    assert.equal(validateStockValue(2.5).ok, false);
    assert.equal(validateStockValue(Number.NaN).ok, false);
    assert.equal(validateStockValue('5').ok, false);
  });

  it('treats a null price override as "clear it" and validates a present one', () => {
    assert.deepEqual(validatePriceOverride(null), { ok: true });
    assert.deepEqual(validatePriceOverride(1_200_000), { ok: true });
    assert.equal(validatePriceOverride(0.5).ok, false);
    assert.equal(validatePriceOverride(-1).ok, false);
    assert.equal(validatePriceOverride(undefined).ok, false);
  });
});

describe('validation — fulfillment and promotions (§2.3–§2.4)', () => {
  it('accepts a plausible postal tracking code and refuses a short one', () => {
    assert.deepEqual(validateTrackingCode('24IR1234567890'), { ok: true });
    assert.deepEqual(validateTrackingCode(' 12345678 '), { ok: true });
    assert.equal(validateTrackingCode('1234567').ok, false);
    assert.equal(validateTrackingCode('1234567890123456789012345').ok, false);
    assert.equal(validateTrackingCode('کدرهگیری۱۲۳').ok, false);
    assert.equal(validateTrackingCode(12345678).ok, false);
  });

  const now = new Date('2026-10-10T00:00:00.000Z');

  it('accepts a percentage coupon inside 1–100', () => {
    assert.deepEqual(
      validateCoupon(
        { code: 'norooz1405', discountType: 'PERCENT', discountValue: 20, minSpend: 500_000 },
        now,
      ),
      { ok: true },
    );
  });

  it('refuses a percentage outside 1–100 and a non-positive fixed amount', () => {
    const tooBig = validateCoupon(
      { code: 'BIG', discountType: 'PERCENT', discountValue: 101 },
      now,
    );
    assert.equal(tooBig.ok, false);
    const zero = validateCoupon({ code: 'ZERO', discountType: 'PERCENT', discountValue: 0 }, now);
    assert.equal(zero.ok, false);
    const fractional = validateCoupon(
      { code: 'FRAC', discountType: 'PERCENT', discountValue: 12.5 },
      now,
    );
    assert.equal(fractional.ok, false);
    const fixed = validateCoupon({ code: 'FIXED0', discountType: 'FIXED', discountValue: 0 }, now);
    assert.equal(fixed.ok, false);
    const unknownType = validateCoupon(
      {
        code: 'ODD',
        discountType: 'BOGO' as unknown as 'PERCENT',
        discountValue: 10,
      },
      now,
    );
    assert.equal(unknownType.ok, false);
  });

  it('refuses a malformed coupon code and a negative minimum spend', () => {
    assert.equal(
      validateCoupon({ code: 'آ', discountType: 'PERCENT', discountValue: 10 }, now).ok,
      false,
    );
    assert.equal(
      validateCoupon(
        { code: 'OKCODE', discountType: 'PERCENT', discountValue: 10, minSpend: -1 },
        now,
      ).ok,
      false,
    );
    assert.equal(
      validateCoupon(
        { code: 'OKCODE', discountType: 'PERCENT', discountValue: 10, usageLimit: 0 },
        now,
      ).ok,
      false,
    );
  });

  it('requires an expiry date in the future — and an unparsable date is not "no date"', () => {
    assert.deepEqual(
      validateCoupon(
        { code: 'FUTURE', discountType: 'PERCENT', discountValue: 10, expiresAt: null },
        now,
      ),
      { ok: true },
    );
    assert.equal(
      validateCoupon(
        {
          code: 'PAST',
          discountType: 'PERCENT',
          discountValue: 10,
          expiresAt: '2026-01-01T00:00:00.000Z',
        },
        now,
      ).ok,
      false,
    );
    assert.equal(
      validateCoupon(
        {
          code: 'GARBAGE',
          discountType: 'PERCENT',
          discountValue: 10,
          expiresAt: 'next norooz',
        },
        now,
      ).ok,
      false,
    );
  });
});

/**
 * D-172 §3.4 — checkout input rules.
 *
 * The customer types on a phone with a Persian keyboard, so the digit sets are
 * normalised (Persian and Arabic-Indic → Latin) but nothing else is: a phone
 * number that is not an Iranian mobile is refused with its reason rather than
 * "cleaned" into something that looks valid.
 */
describe('validation — checkout customer block (§3.4)', () => {
  it('reads Persian and Arabic-Indic digits as the digits they are', () => {
    assert.equal(normalizeDigits('۰۹۱۲۳۴۵۶۷۸۹'), '09123456789');
    assert.equal(normalizeDigits('٠٩١٢٣٤٥٦٧٨٩'), '09123456789');
    assert.equal(normalizeDigits('۰a1٢'), '0a12');
    assert.equal(normalizeDigits(''), '');
  });

  it('accepts an Iranian mobile written with separators or Persian digits', () => {
    assert.equal(validatePhoneNumber('09123456789').ok, true);
    assert.equal(validatePhoneNumber('۰۹۱۲۳۴۵۶۷۸۹').ok, true);
    assert.equal(validatePhoneNumber('0912-345-6789').ok, true);
    assert.equal(validatePhoneNumber('(0912) 345 6789').ok, true);
    assert.equal(normalizePhoneNumber('۰۹۱۲ ۳۴۵ ۶۷۸۹'), '09123456789');
  });

  it('refuses a number that is not an Iranian mobile, naming the field', () => {
    for (const bad of ['0812345678', '091234567', '091234567890', '+989123456789', 'phone']) {
      const result = validatePhoneNumber(bad);
      assert.equal(result.ok, false, `${bad} must be refused`);
      assert.ok(!result.ok && result.issues[0]?.field === 'phoneNumber');
    }
    assert.equal(validatePhoneNumber(undefined).ok, false);
    assert.equal(validatePhoneNumber(1234).ok, false);
  });

  it('requires a ten-digit postal code', () => {
    assert.equal(validatePostalCode('1234567890').ok, true);
    assert.equal(validatePostalCode('۱۲۳۴۵۶۷۸۹۰').ok, true);
    assert.equal(normalizePostalCode('12345-67890'), '1234567890');
    assert.equal(validatePostalCode('123456789').ok, false);
    assert.equal(validatePostalCode('12345678901').ok, false);
    assert.equal(validatePostalCode('12345abcde').ok, false);
  });

  it('bounds the name and the address by length, not by guesswork', () => {
    assert.equal(validateCustomerName('سارا محمدی').ok, true);
    assert.equal(validateCustomerName(' ا ').ok, false);
    assert.equal(validateCustomerName('x'.repeat(121)).ok, false);
    assert.equal(validateAddress('تهران، خیابان ولیعصر، پلاک ۱۲').ok, true);
    assert.equal(validateAddress('تهران').ok, false);
    assert.equal(validateAddress('ی'.repeat(501)).ok, false);
  });

  it('reports every offending field at once, so nothing is fixed one round-trip at a time', () => {
    const result = validateCheckoutCustomer({
      fullName: 'ا',
      phoneNumber: '123456',
      address: 'کوتاه',
      postalCode: '123',
    });
    assert.equal(result.ok, false);
    assert.ok(!result.ok);
    assert.deepEqual(
      result.issues.map((entry) => entry.field).sort(),
      ['address', 'fullName', 'phoneNumber', 'postalCode'],
    );

    const good = validateCheckoutCustomer({
      fullName: 'سارا محمدی',
      phoneNumber: '۰۹۱۲۳۴۵۶۷۸۹',
      address: 'تهران، خیابان ولیعصر، پلاک ۱۲، واحد ۳',
      postalCode: '۱۲۳۴۵۶۷۸۹۰',
    });
    assert.equal(good.ok, true);
  });
});
