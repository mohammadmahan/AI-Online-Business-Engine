import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  MAX_SMS_CHARS,
  ORDER_CONFIRMED_KIND,
  ORDER_NOTIFICATION_CHANNELS,
  ORDER_NOTIFICATION_KINDS,
  SMS_BACKOFF_SECONDS,
  countCharacters,
  maskSmsRecipient,
  normalizeSmsRecipient,
  orderReference,
  renderNotificationBody,
  smsBackoffSeconds,
} from '@/lib/notification-rules';

/**
 * D-172 §6.2 — the notification RULES, asserted without a queue, a provider or a
 * clock.
 *
 * Three of these assertions are parity checks, not preferences:
 *  - the Persian body is byte-identical to
 *    `local/canonical/sms_adapter.py::_BODY_TEMPLATES['order.confirmed.v1']`, so
 *    the same order reads the same from either sender;
 *  - the recipient rule is the adapter's `normalize_recipient` (an Iranian
 *    MSISDN in `09xxxxxxxxx` form, or nothing);
 *  - the kind/channel sets are closed, which is what makes "an unknown
 *    notification" impossible to enqueue rather than merely discouraged.
 */

describe('§6.2 notification vocabulary', () => {
  it('admits exactly one kind and one channel today', () => {
    assert.deepEqual([...ORDER_NOTIFICATION_KINDS], ['order.confirmed']);
    assert.deepEqual([...ORDER_NOTIFICATION_CHANNELS], ['SMS']);
  });
});

describe('§6.2 order reference', () => {
  it('is a short upper-case slice of the order id', () => {
    assert.equal(orderReference('a1b2c3d4-0000-4000-8000-000000000001'), 'A1B2C3D4');
  });

  it('never returns an empty body for an id without alphanumerics', () => {
    assert.equal(orderReference('---'), 'UNKNOWN');
  });
});

describe('§6.2 order confirmation body', () => {
  it('renders the canonical Persian sentence with the order reference', () => {
    assert.equal(
      renderNotificationBody(ORDER_CONFIRMED_KIND, { orderRef: 'AB12CD34' }),
      'سفارش AB12CD34 ثبت شد. از خرید شما سپاسگزاریم.',
    );
  });

  it('stays inside the SMS bound the canonical adapter enforces', () => {
    const body = renderNotificationBody(ORDER_CONFIRMED_KIND, { orderRef: 'AB12CD34' });
    assert.ok(body !== null);
    assert.ok(countCharacters(body) <= MAX_SMS_CHARS);
    // Persian text is measured in code points, so a UTF-16 length would report
    // a different number for the same string.
    assert.equal(countCharacters(body), Array.from(body).length);
  });
});

describe('§6.2 recipient normalisation (parity with sms_adapter.normalize_recipient)', () => {
  it('accepts a national MSISDN unchanged', () => {
    assert.equal(normalizeSmsRecipient('09123456789'), '09123456789');
  });

  it('collapses +98 / 0098 / spaced forms to the 09xxxxxxxxx form', () => {
    assert.equal(normalizeSmsRecipient('+989123456789'), '09123456789');
    assert.equal(normalizeSmsRecipient('0912 345 6789'), '09123456789');
    assert.equal(normalizeSmsRecipient(' 09123456789 '), '09123456789');
  });

  it('refuses a symbolic reference, a landline and an empty value', () => {
    assert.equal(normalizeSmsRecipient('user-42-sms'), null);
    assert.equal(normalizeSmsRecipient('0212345678'), null);
    assert.equal(normalizeSmsRecipient('00989123456789'), null);
    assert.equal(normalizeSmsRecipient(''), null);
    assert.equal(normalizeSmsRecipient(null), null);
    assert.equal(normalizeSmsRecipient(undefined), null);
  });

  it('masks a recipient for a log line', () => {
    assert.equal(maskSmsRecipient('09123456789'), '0912***789');
    assert.equal(maskSmsRecipient('12'), '***');
  });
});

describe('§6.2 retry backoff', () => {
  it('walks the table and then holds at the last interval', () => {
    assert.deepEqual([...SMS_BACKOFF_SECONDS], [60, 300, 1_800]);
    assert.equal(smsBackoffSeconds(1), 60);
    assert.equal(smsBackoffSeconds(2), 300);
    assert.equal(smsBackoffSeconds(3), 1_800);
    assert.equal(smsBackoffSeconds(9), 1_800);
    // A nonsensical attempt number is clamped rather than producing a negative
    // or fractional wait.
    assert.equal(smsBackoffSeconds(0), 60);
  });
});
