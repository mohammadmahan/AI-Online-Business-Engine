import type { Metadata } from 'next';

import { BusinessStatusCard } from '@/components/business/business-status-card';
import { EmergencyActionsCard } from '@/components/dashboard/emergency-actions';
import { HealthGrid, HealthSummary } from '@/components/dashboard/health-grid';
import { KpiGrid } from '@/components/dashboard/kpi-grid';
import { MockNotice } from '@/components/dashboard/mock-notice';
import { PendingApprovalsCard } from '@/components/dashboard/pending-approvals';
import { SystemEventsCard } from '@/components/dashboard/system-events';
import { PageHeader } from '@/components/page-shell';
import { Card } from '@/components/ui/card';
import { TechnicalOnly } from '@/components/ui/view-gate';
import { dashboardBusinessCard } from '@/lib/business-summary';
import { createMockDashboardSource, activeScenario } from '@/lib/mock/dashboard-data';
import { summarize } from '@/lib/telemetry';
import { formatTimeUtc } from '@/lib/format';

export const metadata: Metadata = {
  title: 'نمای فرماندهی',
};

/**
 * Executive overview (D-171 §5.1, Phase 27.3).
 *
 * Renders entirely from a `DashboardDataSource`. Today that source is the
 * deterministic mock provider — the only implementation in this phase — so the
 * page is honest about provenance: a MOCK notice is rendered before the first
 * number, and no service can display PASS without evidence.
 */
export default async function Page() {
  const source = createMockDashboardSource(activeScenario());
  const snapshot = await source.load();
  const summary = summarize(snapshot.services);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/dashboard"
        meta={
          // Snapshot provenance/scenario is a console asset (Phase 27.13).
          <TechnicalOnly surface="dashboard-page-meta">
            <p className="mt-1 text-cp-caption text-ink-muted">
              تصویر لحظه‌ای:{' '}
              <time dateTime={snapshot.generatedAt} className="tabular-nums">
                {formatTimeUtc(snapshot.generatedAt)}
              </time>{' '}
              UTC · منبع: <span className="font-mono">{snapshot.provenance}</span>
            </p>
          </TechnicalOnly>
        }
      />

      <BusinessStatusCard model={dashboardBusinessCard(snapshot)} />

      <TechnicalOnly surface="dashboard-mock-notice">
        <MockNotice scenario={snapshot.scenario} provenance={snapshot.provenance} />
      </TechnicalOnly>

      <TechnicalOnly surface="dashboard-health">
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-cp-heading font-semibold text-ink">
              سلامت و اتصال سرویس‌ها
            </h2>
            <HealthSummary summary={summary} />
          </div>
          <HealthGrid services={snapshot.services} />
        </Card>
      </TechnicalOnly>

      <section aria-label="شاخص‌های کلیدی" className="flex flex-col gap-3">
        <h2 className="text-cp-heading font-semibold text-ink">شاخص‌های کلیدی</h2>
        <KpiGrid kpis={snapshot.kpis} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2 [[data-view-mode=business]_&]:lg:grid-cols-1">
        <Card>
          <PendingApprovalsCard
            approvals={snapshot.pendingApprovals}
            total={snapshot.pendingApprovalsTotal}
          />
        </Card>
        {/* The D-121 ledger stream (event kinds + trace ids) is a console asset. */}
        <TechnicalOnly surface="dashboard-ledger-events">
          <Card>
            <SystemEventsCard events={snapshot.events} />
          </Card>
        </TechnicalOnly>
      </div>

      <TechnicalOnly surface="dashboard-emergency-actions">
        <Card>
          <EmergencyActionsCard actions={snapshot.emergencyActions} />
        </Card>
      </TechnicalOnly>
    </div>
  );
}
