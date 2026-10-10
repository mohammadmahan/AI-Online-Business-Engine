import { Activity, Brain, Coins, FlaskConical, ListChecks, PlugZap, ShieldOff } from 'lucide-react';
import type { Metadata } from 'next';

import { AgentRoutesTable } from '@/components/ai-ops/agent-routes-table';
import { AiOpsControls } from '@/components/ai-ops/ai-ops-controls';
import { MemoryLayerPanel } from '@/components/ai-ops/memory-layer-panel';
import { ProposalDraftsTable } from '@/components/ai-ops/proposal-drafts-table';
import { TokenCostTable } from '@/components/ai-ops/token-cost-table';
import { BusinessStatusCard } from '@/components/business/business-status-card';
import { PageHeader } from '@/components/page-shell';
import { Card, CardHeader } from '@/components/ui/card';
import { ToneBadge } from '@/components/ui/tone-badge';
import { TechnicalOnly, VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { aiEngineBusinessCard } from '@/lib/business-summary';
import { formatTimeUtc } from '@/lib/format';
import { getAiOpsSource } from '@/lib/mock/ai-ops-data';

export const metadata: Metadata = {
  title: 'موتور هوش مصنوعی',
};

/**
 * The service seam is read per request; only the deterministic mock exists, so
 * a default build statically prerenders byte-identically (the build-time guard
 * runs on it). No LIVE branch is wired: no canonical read-only surface for
 * agent observability, token analytics or proposals exists, and the
 * shared-memory layer itself is PLANNED behind the D-045 owner gate (D-142).
 */
export const runtime = 'nodejs';

/**
 * AI Ops & Shared Memory Hub (D-171 §4 Phase 5, §5.5 `/ai-engine`).
 *
 * READ-ONLY BY CONSTRUCTION. The page renders observations only: no provider
 * call originates from it, it holds no credential, it mints no token, it
 * advances no proposal and it opens no memory connection — every control is
 * disabled with its own stated reason (D-171 §5.5/§6, D-026/D-027/D-142).
 *
 * Fail-closed throughout: the shared-memory layer is `NOT_CONNECTED` with NO
 * namespaces and NO counts while D-142 is unconnected (never a fabricated
 * zero), an unmeasured route renders `—` everywhere, an unpriced
 * (provider, model) pair is refused rather than given an invented price, and a
 * NO_DATA source outranks every component reading. The build-time guard
 * (`assertAiOpsConsistency`) makes each of those rules structural.
 */
export default async function Page() {
  const source = await getAiOpsSource();
  const snapshot = await source.load();
  const unavailable = snapshot.provenance === 'unavailable';
  const live = snapshot.sourceMode === 'LIVE';
  const memory = snapshot.memory;
  const summary = snapshot.summary;
  const cheapest = snapshot.cost.find((row) => row.routeId === 'generate_caption');
  const sampleCost = cheapest?.costMicroUsd ?? null;

  const noticeBorder = unavailable ? 'border-danger' : live ? 'border-success' : 'border-warning';

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/ai-engine"
        meta={
          // Mode, provenance and machine readings are console assets.
          <TechnicalOnly surface="ai-engine-page-meta">
            <p className="mt-1 text-cp-caption text-ink-muted">
              تصویر لحظه‌ای:{' '}
              <time dateTime={snapshot.generatedAt} className="tabular-nums">
                {formatTimeUtc(snapshot.generatedAt)}
              </time>{' '}
              UTC · حالت: <span className="font-mono">{snapshot.sourceMode}</span> · منبع:{' '}
              <span className="font-mono">{snapshot.provenance}</span> · لایهٔ حافظه:{' '}
              <span className="font-mono">{memory.state}</span> · بدترین فشار بودجه:{' '}
              <span className="font-mono">{summary.worstBudgetPressure}</span>{' '}
              <span
                data-view-gate="technical"
                data-surface="page-phase-ref"
                className={`font-mono text-cp-caption opacity-80 ${VIEW_GATE_CLASS.technical}`}
              >
                · فعال‌سازی در Phase 27.7
              </span>
            </p>
          </TechnicalOnly>
        }
      />

      <BusinessStatusCard model={aiEngineBusinessCard(snapshot)} />

      <TechnicalOnly surface="ai-engine-notice">
        <div
          className={`flex flex-wrap items-center gap-3 rounded-[--radius-cp] border ${noticeBorder} bg-surface p-3`}
          role="note"
        >
          {live ? (
            <ToneBadge tone="success" label="کاوش زنده" code="LIVE" Icon={Activity} />
          ) : (
            <ToneBadge tone="warning" label="دادهٔ نمونه" code="MOCK" Icon={FlaskConical} />
          )}
          {unavailable ? (
            <ToneBadge tone="danger" label="بدون داده" code="NO_DATA" Icon={PlugZap} />
          ) : null}
          <p className="text-cp-label text-ink">
            {unavailable ? (
              <>
                هیچ خوانشی از موتور هوش مصنوعی تولید نشد؛ مسیرها <strong>بدون خوانش</strong> و لایهٔ
                حافظه <strong>نامشخص (UNKNOWN)</strong> می‌ماند — نه صفر، نه سالم.
              </>
            ) : (
              <>
                آمار دستیارها از <strong>دادهٔ نمونهٔ قطعی</strong> خوانده شده است و حافظهٔ مشترک هنوز{' '}
                <strong>وصل نشده (NOT_CONNECTED)</strong> است؛ وضعیت‌ها فقط نمایش داده می‌شوند و هیچ
                فراخوانی ارائه‌دهنده‌ای از این صفحه انجام نمی‌شود (D-142/D-045).
              </>
            )}{' '}
            سناریو: <span className="font-mono text-cp-caption">{snapshot.scenario}</span>
          </p>
        </div>
      </TechnicalOnly>

      <TechnicalOnly surface="ai-engine-memory">
        <Card>
          <CardHeader
            title="حافظهٔ مشترک دستیارها"
            description="وضعیت لایهٔ حافظه (D-142)، نام‌فضاها و شمارش برداری؛ تا عبور از گیت مالک هیچ اتصالی برقرار نمی‌شود و هیچ شمارشی جعل نمی‌گردد."
            action={<Brain aria-hidden="true" className="size-5 text-ink-muted" />}
          />
          <MemoryLayerPanel memory={memory} />
        </Card>
      </TechnicalOnly>

      <TechnicalOnly surface="ai-engine-routes">
        <Card>
          <CardHeader
            title="مشاهده‌پذیری مسیرهای اجرا"
            description="سه مسیر canonical با تعداد اجرا، موفق/ناموفق، نرخ موفقیت، تأخیر p95 و مراحل ثبت‌شدهٔ ai.observe.v1؛ مسیر خوانده‌نشده هیچ عددی نشان نمی‌دهد."
          />
          <AgentRoutesTable routes={snapshot.routes} />
        </Card>
      </TechnicalOnly>

      <TechnicalOnly surface="ai-engine-cost">
        <Card>
          <CardHeader
            title="مصرف و هزینه"
            description="مصرف توکن هر مسیر در برابر سقف پنجرهٔ روزانه (D-127) و سقف هر اجرا (D-063)؛ نسبت مصرف از آستانهٔ ۰٫۸ هشدار می‌گیرد و هزینه فقط از جدول تعرفهٔ canonical محاسبه می‌شود."
            action={<Coins aria-hidden="true" className="size-5 text-ink-muted" />}
          />
          <TokenCostTable cost={snapshot.cost} />
          <p className="mt-3 text-cp-caption text-ink-muted">
            ارائه‌دهندهٔ فعال «Mock» است و جدول تعرفهٔ canonical تنها همین ارائه‌دهنده را قیمت‌گذاری
            می‌کند؛ بنابراین هزینهٔ ثبت‌شده صفر است و هیچ قیمتی برای جفت ارائه‌دهنده/مدل خارج از جدول
            ساخته نمی‌شود
            {sampleCost === null ? '' : ' (نمونهٔ خوانده‌شده: 0.000000 USD)'}.
          </p>
        </Card>
      </TechnicalOnly>

      <TechnicalOnly surface="ai-engine-proposals">
        <Card>
          <CardHeader
            title="پیش‌نویس‌های هوش مصنوعی"
            description="پیش‌نویس‌ها و وضعیت چرخهٔ عمر D-064 (PROPOSED → IN_REVIEW → تصمیم انسانی)؛ این جدول فقط‌خواندنی است و تصمیم‌گیری جای دیگری انجام می‌شود."
            action={<ListChecks aria-hidden="true" className="size-5 text-ink-muted" />}
          />
          <ProposalDraftsTable proposals={snapshot.proposals} />
        </Card>
      </TechnicalOnly>

      <TechnicalOnly surface="ai-engine-controls">
        <Card>
          <CardHeader
            title="کنترل‌های مسدود"
            description="هر کنشی که از مرز فقط‌خواندنی عبور می‌کرد، غیرفعال است و دلیل خودش را می‌گوید: نه فراخوانی ارائه‌دهنده، نه خواندن حافظه، نه برقراری اتصال."
            action={<ShieldOff aria-hidden="true" className="size-5 text-ink-muted" />}
          />
          <AiOpsControls controls={snapshot.controls} providerGate={snapshot.providerGate} />
        </Card>
      </TechnicalOnly>
    </div>
  );
}
