import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  ASSISTANT_TOKEN_ENV,
  ASSISTANT_URL_ENV,
  handleAssistantRequest,
  resolveAssistantConfig,
  validateAssistantInput,
} from '@/server/ai/assistant';

const TOKEN = 'test-token-0123456789abcdef';
const ENV: NodeJS.ProcessEnv = {
  NODE_ENV: 'test',
  [ASSISTANT_URL_ENV]: 'http://127.0.0.1:8099',
  [ASSISTANT_TOKEN_ENV]: TOKEN,
};

const INPUT = {
  channel: 'seo_copy' as const,
  title: 'مانتو کتان',
  fabricType: 'کتان',
  season: 'پاییز',
  notes: 'برش راحت و آستین بلند',
  tone: 'luxury' as const,
};

const PROPOSAL = {
  meta_description_fa: 'توضیح متای محصول پوشاک زنانه برای فروشگاه محلی.',
  web_copy_fa: 'متن معرفی محصول با جزئیات پارچه، فصل و کاربرد روزمره.',
  seo_keywords: ['پوشاک', 'مانتو'],
  rationale: 'بر اساس مشخصات اعلام‌شدهٔ فروشنده.',
};

function okBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    channel: 'seo_copy',
    mode: 'dry-run',
    proposal: PROPOSAL,
    provider: 'ollama',
    model: 'llama3.2',
    usage: { prompt_tokens: 10, completion_tokens: 20 },
    warnings: [],
    ...overrides,
  };
}

function fakeFetch(body: unknown, status = 200) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }) as typeof fetch;
  return { calls, fetchImpl };
}

describe('assistant input validation', () => {
  it('accepts the structured merchant brief', () => {
    const result = validateAssistantInput(INPUT);
    assert.equal(result.ok, true);
    if (result.ok) assert.equal(result.value.channel, 'seo_copy');
  });

  it('rejects unknown fields, including customer/order material', () => {
    const result = validateAssistantInput({ ...INPUT, customerPhone: '09123456789' });
    assert.deepEqual(result, { ok: false, field: 'form' });
  });

  it('rejects contact data in every free-text field', () => {
    for (const field of ['title', 'fabricType', 'season', 'notes'] as const) {
      const result = validateAssistantInput({ ...INPUT, [field]: 'تماس 09123456789' });
      assert.deepEqual(result, { ok: false, field });
    }
  });

  it('rejects URLs and unsupported channels', () => {
    assert.deepEqual(validateAssistantInput({ ...INPUT, notes: 'https://example.com' }), {
      ok: false,
      field: 'notes',
    });
    assert.deepEqual(validateAssistantInput({ ...INPUT, channel: 'orders' }), {
      ok: false,
      field: 'channel',
    });
  });
});

describe('assistant configuration', () => {
  it('requires an explicit loopback port and a long token', () => {
    assert.equal(resolveAssistantConfig(ENV)?.endpoint, 'http://127.0.0.1:8099/assistant');
    assert.equal(resolveAssistantConfig({ ...ENV, [ASSISTANT_URL_ENV]: 'http://127.0.0.1' }), null);
    assert.equal(resolveAssistantConfig({ ...ENV, [ASSISTANT_TOKEN_ENV]: 'short' }), null);
  });

  it('refuses remote, credential-bearing and path-bearing URLs', () => {
    for (const url of [
      'https://127.0.0.1:8099',
      'http://192.168.1.5:8099',
      'http://host.docker.internal:8099',
      'http://user:pass@127.0.0.1:8099',
      'http://127.0.0.1:8099/admin',
      'http://127.0.0.1:8099/?x=1',
    ]) {
      assert.equal(resolveAssistantConfig({ ...ENV, [ASSISTANT_URL_ENV]: url }), null, url);
    }
  });
});

describe('assistant request boundary', () => {
  it('refuses before fetch when the action is unauthorized', async () => {
    const { calls, fetchImpl } = fakeFetch(okBody());
    const result = await handleAssistantRequest(INPUT, {
      authorized: false,
      env: ENV,
      fetch: fetchImpl,
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.code, 'UNAUTHORIZED');
    assert.equal(calls.length, 0);
  });

  it('refuses before fetch when the bridge is not configured', async () => {
    const { calls, fetchImpl } = fakeFetch(okBody());
    const result = await handleAssistantRequest(INPUT, {
      authorized: true,
      env: { NODE_ENV: 'test', [ASSISTANT_URL_ENV]: 'http://127.0.0.1:8099' },
      fetch: fetchImpl,
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.code, 'AI_NOT_CONFIGURED');
    assert.equal(calls.length, 0);
  });

  it('sends only allowlisted product fields to the loopback bridge', async () => {
    const { calls, fetchImpl } = fakeFetch(okBody());
    const result = await handleAssistantRequest(INPUT, {
      authorized: true,
      env: ENV,
      fetch: fetchImpl,
    });
    assert.equal(result.ok, true);
    assert.equal(calls.length, 1);
    const call = calls[0];
    assert.ok(call);
    assert.equal(call.url, 'http://127.0.0.1:8099/assistant');
    assert.equal(call.init.method, 'POST');
    assert.equal(call.init.cache, 'no-store');
    assert.equal(
      (call.init.headers as Record<string, string>).authorization,
      `Bearer ${TOKEN}`,
    );
    const body = JSON.parse(String(call.init.body)) as Record<string, unknown>;
    assert.deepEqual(Object.keys(body).sort(), [
      'channel',
      'fabric_type',
      'notes',
      'season',
      'title',
      'tone',
    ]);
    assert.equal(body.channel, 'seo_copy');
  });

  it('maps bridge refusals without exposing upstream messages', async () => {
    for (const [status, code] of [
      [401, 'AI_UNAUTHORIZED'],
      [422, 'AI_REFUSED'],
      [503, 'AI_UNAVAILABLE'],
    ] as const) {
      const { fetchImpl } = fakeFetch(
        { ok: false, code: 'LEAKY', message: 'token=secret path=/tmp' },
        status,
      );
      const result = await handleAssistantRequest(INPUT, {
        authorized: true,
        env: ENV,
        fetch: fetchImpl,
      });
      assert.equal(result.ok, false);
      if (!result.ok) {
        assert.equal(result.code, code);
        assert.doesNotMatch(result.message, /secret|token=|\/tmp/);
      }
    }
  });

  it('rejects a valid-looking response with the wrong channel or shape', async () => {
    for (const body of [
      okBody({ channel: 'instagram_caption' }),
      okBody({ proposal: { ...PROPOSAL, extra: 'x' } }),
      okBody({ proposal: { ...PROPOSAL, meta_description_fa: 'تماس 09123456789' } }),
      okBody({ mode: 'persist' }),
    ]) {
      const { fetchImpl } = fakeFetch(body);
      const result = await handleAssistantRequest(INPUT, {
        authorized: true,
        env: ENV,
        fetch: fetchImpl,
      });
      assert.equal(result.ok, false);
      if (!result.ok) assert.equal(result.code, 'AI_INVALID_RESPONSE');
    }
  });

  it('maps transport failures to timeout/unavailable', async () => {
    const timeoutFetch = (async () => {
      throw new DOMException('aborted', 'TimeoutError');
    }) as typeof fetch;
    const timedOut = await handleAssistantRequest(INPUT, {
      authorized: true,
      env: ENV,
      fetch: timeoutFetch,
    });
    assert.equal(timedOut.ok, false);
    if (!timedOut.ok) assert.equal(timedOut.code, 'AI_TIMEOUT');

    const offlineFetch = (async () => {
      throw new TypeError('fetch failed');
    }) as typeof fetch;
    const offline = await handleAssistantRequest(INPUT, {
      authorized: true,
      env: ENV,
      fetch: offlineFetch,
    });
    assert.equal(offline.ok, false);
    if (!offline.ok) assert.equal(offline.code, 'AI_UNAVAILABLE');
  });
});
