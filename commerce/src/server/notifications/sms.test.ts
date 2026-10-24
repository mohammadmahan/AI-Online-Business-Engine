import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ORDER_CONFIRMED_KIND } from '@/lib/notification-rules';
import {
  KAVENEGAR_API_KEY_ENV,
  KAVENEGAR_SENDER_ENV,
  KavenegarSmsChannel,
  MockSmsChannel,
  SMS_LIVE_ENABLED_ENV,
  classifyKavenegarStatus,
  createSmsChannelFromEnv,
  type SmsHttpRequest,
  type SmsTransport,
} from '@/server/notifications/sms';

/**
 * D-172 §6.2 — the SMS channel adapter.
 *
 * The live half is tested entirely through an INJECTED transport: no test reaches
 * Kavenegar, and the fake records what the adapter would have sent so the URL
 * (which carries the key), the form fields and the classification can all be
 * asserted. The mock half is asserted to validate the same two things the live
 * adapter does — recipient and body — because a mock that accepts anything would
 * hide a go-live failure rather than prevent it.
 */

const API_KEY = 'kavenegar-test-key-0123456789';
const SENDER = '10004346';

function recordingTransport(response: { status: number; body: unknown }) {
  const calls: SmsHttpRequest[] = [];
  const transport: SmsTransport = async (request) => {
    calls.push(request);
    return response;
  };
  return { calls, transport };
}

function liveChannel(response: { status: number; body: unknown }) {
  const recorder = recordingTransport(response);
  const channel = new KavenegarSmsChannel(recorder.transport, {
    apiKey: API_KEY,
    sender: SENDER,
  });
  return { ...recorder, channel };
}

const MESSAGE = {
  to: '09123456789',
  kind: ORDER_CONFIRMED_KIND,
  body: 'سفارش AB12CD34 ثبت شد. از خرید شما سپاسگزاریم.',
} as const;

describe('§6.2 mock channel (D-045 local mode)', () => {
  it('records the call and sends nothing', async () => {
    const channel = new MockSmsChannel();
    const result = await channel.send(MESSAGE);

    assert.deepEqual(result, { ok: true, providerMessageId: 'MOCK-SMS-1' });
    assert.equal(channel.mode, 'MOCK');
    assert.equal(channel.calls.length, 1);
    assert.equal(channel.calls[0]?.to, '09123456789');
    assert.equal(channel.calls[0]?.body, MESSAGE.body);
    assert.equal(channel.calls[0]?.kind, ORDER_CONFIRMED_KIND);
  });

  it('numbers its accepted messages deterministically', async () => {
    const channel = new MockSmsChannel();
    await channel.send(MESSAGE);
    await channel.send(MESSAGE);
    assert.deepEqual(
      channel.calls.map((call) => call.providerMessageId),
      ['MOCK-SMS-1', 'MOCK-SMS-2'],
    );
  });

  it('refuses an unusable recipient and records nothing', async () => {
    const channel = new MockSmsChannel();
    const result = await channel.send({ ...MESSAGE, to: 'user-42-sms' });

    assert.deepEqual(result, { ok: false, code: 'invalid_recipient', retryable: false });
    assert.equal(channel.calls.length, 0);
  });

  it('refuses an empty body and records nothing', async () => {
    const channel = new MockSmsChannel();
    const result = await channel.send({ ...MESSAGE, body: '' });

    assert.deepEqual(result, { ok: false, code: 'body_unavailable', retryable: false });
    assert.equal(channel.calls.length, 0);
  });
});

describe('§6.2 channel construction gate', () => {
  it('defaults to the mock when the live flag is absent', () => {
    const resolution = createSmsChannelFromEnv({});
    assert.equal(resolution.ok, true);
    assert.equal(resolution.ok && resolution.mode, 'MOCK');
    assert.equal(resolution.ok && resolution.channel.id, 'mock');
  });

  it('defaults to the mock for any value other than exactly true', () => {
    for (const value of ['false', '1', 'yes', '', 'enabled']) {
      const resolution = createSmsChannelFromEnv({ [SMS_LIVE_ENABLED_ENV]: value });
      assert.equal(resolution.ok, true, `flag=${JSON.stringify(value)} must stay mock`);
      assert.equal(resolution.ok && resolution.mode, 'MOCK');
    }
  });

  it('accepts a padded upper-case true as live (and then demands a credential)', () => {
    const resolution = createSmsChannelFromEnv({ [SMS_LIVE_ENABLED_ENV]: ' TRUE ' });
    // The flag is honoured (trimmed/lower-cased, like sms_adapter.live_enabled),
    // and because no credential exists the gate REFUSES rather than mocking.
    assert.equal(resolution.ok, false);
  });

  it('REFUSES live mode without a credential instead of silently mocking', () => {
    const missingKey = createSmsChannelFromEnv({ [SMS_LIVE_ENABLED_ENV]: 'true' });
    assert.equal(missingKey.ok, false);
    assert.equal(missingKey.ok === false ? missingKey.code : '', 'SMS_LIVE_MODE_MISSING_CREDENTIAL');

    const missingSender = createSmsChannelFromEnv({
      [SMS_LIVE_ENABLED_ENV]: 'true',
      [KAVENEGAR_API_KEY_ENV]: API_KEY,
    });
    assert.equal(missingSender.ok, false);
  });

  it('builds the live adapter when the flag and both credential parts are present', () => {
    const resolution = createSmsChannelFromEnv(
      {
        [SMS_LIVE_ENABLED_ENV]: 'true',
        [KAVENEGAR_API_KEY_ENV]: API_KEY,
        [KAVENEGAR_SENDER_ENV]: SENDER,
      },
      recordingTransport({ status: 200, body: {} }).transport,
    );
    assert.equal(resolution.ok, true);
    assert.equal(resolution.ok && resolution.mode, 'LIVE');
    assert.equal(resolution.ok && resolution.channel.id, 'kavenegar');
  });

  it('refuses to construct the live adapter with a blank credential', () => {
    assert.throws(
      () =>
        new KavenegarSmsChannel(async () => ({ status: 200, body: {} }), {
          apiKey: '   ',
          sender: SENDER,
        }),
    );
    assert.throws(
      () =>
        new KavenegarSmsChannel(async () => ({ status: 200, body: {} }), {
          apiKey: API_KEY,
          sender: '  ',
        }),
    );
  });

describe('§6.2 Kavenegar adapter', () => {
  it('POSTs the plain-text route with the normalised recipient and sender', async () => {
    const { channel, calls } = liveChannel({
      status: 200,
      body: { return: { status: 200, message: 'ok' }, entries: [{ messageid: 987654321 }] },
    });

    const result = await channel.send({ ...MESSAGE, to: '+989123456789' });

    assert.deepEqual(result, { ok: true, providerMessageId: '987654321' });
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, `https://api.kavenegar.com/v1/${API_KEY}/sms/send.json`);
    assert.deepEqual(calls[0]?.form, {
      receptor: '09123456789',
      sender: SENDER,
      message: MESSAGE.body,
    });
    // The credential travels as a path segment and must never be echoed back.
    assert.ok(!JSON.stringify(result).includes(API_KEY));
  });

  it('refuses an unusable recipient BEFORE any provider call', async () => {
    const { channel, calls } = liveChannel({ status: 200, body: { return: { status: 200 } } });
    const result = await channel.send({ ...MESSAGE, to: 'user-42-sms' });

    assert.deepEqual(result, { ok: false, code: 'invalid_recipient', retryable: false });
    assert.equal(calls.length, 0);
  });

  it('classifies a provider rejection as permanent and never echoes the key', async () => {
    const { channel } = liveChannel({
      status: 200,
      body: { return: { status: 401, message: `invalid key ${API_KEY}` } },
    });
    const result = await channel.send(MESSAGE);

    assert.deepEqual(result, { ok: false, code: 'invalid_api_key', retryable: false });
    assert.ok(!JSON.stringify(result).includes(API_KEY));
  });

  it('classifies provider pacing as retryable with the indicated wait', async () => {
    const { channel } = liveChannel({ status: 200, body: { return: { status: 427 } } });
    const result = await channel.send(MESSAGE);

    assert.deepEqual(result, {
      ok: false,
      code: 'rate_limited',
      retryable: true,
      retryAfterSeconds: 3_600,
    });
  });

  it('treats an HTTP 5xx as transient and an HTTP 4xx as terminal', async () => {
    const server = liveChannel({ status: 503, body: null });
    assert.deepEqual(await server.channel.send(MESSAGE), {
      ok: false,
      code: 'provider_unavailable',
      retryable: true,
    });

    const badRequest = liveChannel({ status: 400, body: 'not-json' });
    assert.deepEqual(await badRequest.channel.send(MESSAGE), {
      ok: false,
      code: 'provider_refused',
      retryable: false,
    });
  });

  it('refuses a 200 that carries no usable provider envelope', async () => {
    const { channel } = liveChannel({ status: 200, body: '<html>gateway</html>' });
    assert.deepEqual(await channel.send(MESSAGE), {
      ok: false,
      code: 'malformed_response',
      retryable: false,
    });
  });

  it('reports a thrown transport as transient without surfacing its message', async () => {
    const channel = new KavenegarSmsChannel(
      async () => {
        throw new Error(`connect ECONNREFUSED https://api.kavenegar.com/v1/${API_KEY}/`);
      },
      { apiKey: API_KEY, sender: SENDER },
    );

    const result = await channel.send(MESSAGE);
    assert.deepEqual(result, { ok: false, code: 'transport_error', retryable: true });
    assert.ok(!JSON.stringify(result).includes(API_KEY));
  });
});

describe('§6.2 Kavenegar status classification (parity with sms_adapter)', () => {
  it('maps the documented bands', () => {
    assert.deepEqual(classifyKavenegarStatus(412), {
      ok: false,
      code: 'invalid_recipient',
      retryable: false,
    });
    assert.deepEqual(classifyKavenegarStatus(422), {
      ok: false,
      code: 'template_not_registered',
      retryable: false,
    });
    assert.deepEqual(classifyKavenegarStatus(451), {
      ok: false,
      code: 'no_credit',
      retryable: false,
    });
    assert.deepEqual(classifyKavenegarStatus(429), {
      ok: false,
      code: 'rate_limited',
      retryable: true,
      retryAfterSeconds: 60,
    });
    assert.deepEqual(classifyKavenegarStatus(504), {
      ok: false,
      code: 'provider_unavailable',
      retryable: true,
    });
    // Unknown codes fail in the SAFE direction: 4xx terminal, 5xx transient.
    assert.deepEqual(classifyKavenegarStatus(499), {
      ok: false,
      code: 'provider_refused',
      retryable: false,
    });
    assert.deepEqual(classifyKavenegarStatus(599), {
      ok: false,
      code: 'provider_unavailable',
      retryable: true,
    });
  });
});

});
