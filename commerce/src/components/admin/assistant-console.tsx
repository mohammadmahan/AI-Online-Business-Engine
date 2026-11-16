'use client';

import { useState } from 'react';

import { Banner, Card, CardHeader, Field, buttonClass, inputClass } from '@/components/ui/primitives';
import {
  generateAssistantCopyAction,
} from '@/server/actions/assistant';
import type { AssistantChannel, AssistantResult } from '@/server/ai/assistant';

const CHANNELS: Array<{ value: AssistantChannel; label: string }> = [
  { value: 'seo_copy', label: 'متن سئو و صفحهٔ محصول' },
  { value: 'instagram_caption', label: 'کپشن اینستاگرام' },
  { value: 'telegram_announcement', label: 'اطلاعیهٔ تلگرام' },
];

const TONES = [
  { value: 'luxury', label: 'لوکس' },
  { value: 'casual', label: 'خودی' },
  { value: 'trendy', label: 'ترند' },
] as const;

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export function AssistantConsole() {
  const [channel, setChannel] = useState<AssistantChannel>('seo_copy');
  const [title, setTitle] = useState('');
  const [fabricType, setFabricType] = useState('');
  const [season, setSeason] = useState('');
  const [notes, setNotes] = useState('');
  const [tone, setTone] = useState<'luxury' | 'casual' | 'trendy'>('luxury');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AssistantResult | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const next = await generateAssistantCopyAction({
        channel,
        title,
        fabricType,
        season,
        notes,
        tone,
      });
      setResult(next);
    } catch {
      setResult({
        ok: false,
        code: 'AI_UNAVAILABLE',
        message: 'دستیار هوش مصنوعی در دسترس نیست؛ هیچ پیشنهادی ساخته نشد.',
      });
    } finally {
      setBusy(false);
    }
  }

  const proposal = result?.ok ? result.proposal : null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <Card>
        <CardHeader
          title="مشخصات محصول"
          description="فقط واقعیت‌های خود محصول را وارد کنید؛ دادهٔ مشتری، سفارش، تلفن یا نشانی ارسال نمی‌شود."
        />
        <form onSubmit={submit} className="grid gap-3 p-4">
          <Field label="کانال" htmlFor="assistant-channel">
            <select
              id="assistant-channel"
              className={inputClass}
              value={channel}
              onChange={(event) => setChannel(event.target.value as AssistantChannel)}
            >
              {CHANNELS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="عنوان محصول" htmlFor="assistant-title">
            <input
              id="assistant-title"
              className={inputClass}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              required
            />
          </Field>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="جنس پارچه" htmlFor="assistant-fabric">
              <input
                id="assistant-fabric"
                className={inputClass}
                value={fabricType}
                onChange={(event) => setFabricType(event.target.value)}
                maxLength={60}
                required
              />
            </Field>
            <Field label="فصل" htmlFor="assistant-season">
              <input
                id="assistant-season"
                className={inputClass}
                value={season}
                onChange={(event) => setSeason(event.target.value)}
                maxLength={40}
                required
              />
            </Field>
          </div>

          <Field label="یادداشت فروشنده (اختیاری)" htmlFor="assistant-notes">
            <textarea
              id="assistant-notes"
              className={inputClass}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={4}
              maxLength={1000}
            />
          </Field>

          <Field label="لحن" htmlFor="assistant-tone">
            <select
              id="assistant-tone"
              className={inputClass}
              value={tone}
              onChange={(event) => setTone(event.target.value as typeof tone)}
            >
              {TONES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </Field>

          <button type="submit" className={buttonClass.primary} disabled={busy}>
            {busy ? 'در حال ساخت پیشنهاد…' : 'ساخت پیشنهاد'}
          </button>
          <p className="text-cp-caption text-ink-muted">
            پیشنهاد در حالت dry-run ساخته می‌شود؛ نه ذخیره می‌شود و نه منتشر. بازبینی انسانی الزامی است.
          </p>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="پیشنهاد هوش مصنوعی"
          description="خروجی فقط برای بازبینی است و هیچ نوشتنی در پایگاه داده انجام نمی‌شود."
        />
        <div className="grid gap-3 p-4">
          {result === null ? (
            <p className="text-cp-body text-ink-muted">هنوز پیشنهادی ساخته نشده است.</p>
          ) : !result.ok ? (
            <Banner tone="warning" title="پیشنهادی ساخته نشد">
              <span className="cp-code">{result.code}</span> — {result.message}
            </Banner>
          ) : (
            <>
              <p className="text-cp-caption text-ink-muted">
                ارائه‌دهنده: <span className="cp-code">{result.provider}</span>
                {result.model ? (
                  <>
                    {' '}· مدل: <span className="cp-code">{result.model}</span>
                  </>
                ) : null}
                {' '}· حالت: dry-run
              </p>
              {result.channel === 'seo_copy' ? (
                <>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">توضیح متا</h3>
                    <p className="text-cp-body text-ink">{text(proposal?.meta_description_fa)}</p>
                  </section>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">متن صفحه</h3>
                    <p className="text-cp-body text-ink whitespace-pre-wrap">{text(proposal?.web_copy_fa)}</p>
                  </section>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">کلیدواژه‌ها</h3>
                    <p className="text-cp-body text-ink">{list(proposal?.seo_keywords).join('، ')}</p>
                  </section>
                </>
              ) : result.channel === 'instagram_caption' ? (
                <>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">کپشن</h3>
                    <p className="text-cp-body text-ink whitespace-pre-wrap">{text(proposal?.caption_fa)}</p>
                  </section>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">متن جایگزین تصویر</h3>
                    <p className="text-cp-body text-ink">{text(proposal?.alt_text)}</p>
                  </section>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">هشتگ‌ها</h3>
                    <p className="text-cp-body text-ink">{list(proposal?.hashtags).join(' ')}</p>
                  </section>
                </>
              ) : (
                <>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">اطلاعیه</h3>
                    <p className="text-cp-body text-ink whitespace-pre-wrap">
                      {text(proposal?.announcement_fa)}
                    </p>
                  </section>
                  <section>
                    <h3 className="text-cp-label font-semibold text-ink">هشتگ‌ها</h3>
                    <p className="text-cp-body text-ink">{list(proposal?.hashtags).join(' ')}</p>
                  </section>
                  {text(proposal?.cta_fa) ? (
                    <section>
                      <h3 className="text-cp-label font-semibold text-ink">فراخوان</h3>
                      <p className="text-cp-body text-ink">{text(proposal?.cta_fa)}</p>
                    </section>
                  ) : null}
                </>
              )}
              {result.warnings.length > 0 ? (
                <Banner tone="warning" title="هشدار موتور">
                  {result.warnings.join(' · ')}
                </Banner>
              ) : null}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
