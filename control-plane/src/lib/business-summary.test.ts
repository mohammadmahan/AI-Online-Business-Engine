/**
 * D-171 §2.2 / §2.3 / §10 — native `node:test` coverage for the pure
 * Business-summary module: the render-time jargon guard and the fail-closed
 * status ladders of all five cards.
 *
 * These are the rules the owner asked to be PROVEN rather than asserted:
 *   - permitted business vocabulary (notably `SKU`, owner ruling 2026-10-07) is
 *     accepted on a card, while every console-only term — including the V-01…
 *     V-10 gate ids — is rejected;
 *   - a card can never be green without a LIVE reading, unavailable data always
 *     reads «بدون داده», and a NO_DATA source outranks every component state
 *     (the ordering defect the guard caught on the live `/automations` route);
 *   - the ladders are deterministic: the same input always yields the same
 *     status, so a page cannot drift between renders.
 *
 * Fixtures carry only the fields the module reads; the cast is deliberate and
 * keeps the tests independent of unrelated view-model fields.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  assertBusinessCard,
  automationsBusinessCard,
  dashboardBusinessCard,
  hitlBusinessCard,
  inventoryBusinessCard,
  ordersBusinessCard,
  type BusinessCardModel,
} from '@/lib/business-summary';
import type { CommerceSnapshot, RevenueSummary } from '@/types/commerce';
import type { DashboardSnapshot } from '@/types/dashboard';
import type { HitlQueueSnapshot, ResolutionStatus } from '@/types/hitl';
import type { InventorySnapshot, InventorySummary } from '@/types/inventory';
import type {
  Provenance,
  ServiceHealth,
  TelemetryOverview,
  TelemetrySnapshot,
} from '@/types/telemetry';

/** Build only the fields under test; the module reads nothing else. */
const partial = <T>(value: Record<string, unknown>): T => value as unknown as T;

function card(overrides: Partial<BusinessCardModel> = {}): BusinessCardModel {
  return {
    id: 'test',
    title: 'عنوان کارت',
    headline: 'خلاصهٔ وضعیت فروشگاه.',
    status: { tone: 'neutral', label: 'نامشخص', code: 'UNKNOWN' },
    provenance: { tone: 'warning', label: 'دادهٔ نمونه', code: 'MOCK' },
    metrics: [{ label: 'شمارش', value: '۰', tip: 'توضیح شمارش.' }],
    drillDown: { label: 'مشاهدهٔ جزئیات', tip: 'توضیح جزئیات.' },
    ...overrides,
  };
}

function service(state: ServiceHealth['state'], id: ServiceHealth['id'] = 'postgres'): ServiceHealth {
  return {
    id,
    title: 'سرویس',
    code: 'SERVICE',
    state,
    provenance: 'mock',
    detail: 'توضیح سرویس.',
    metrics: [],
    lastMeasuredAt: null,
  };
}

function dashboard(states: ServiceHealth['state'][], provenance: Provenance, ordersValue = '148'): DashboardSnapshot {
  return partial<DashboardSnapshot>({
    generatedAt: '2026-10-07T09:30:00.000Z',
    scenario: 'test',
    provenance,
    services: states.map((state, index) => service(state, index % 2 === 0 ? 'postgres' : 'n8n')),
    kpis: [
      {
        id: 'orders_revenue',
        title: 'سفارش‌ها و درآمد امروز',
        code: 'ORDERS_REVENUE',
        value: ordersValue,
        trend: null,
        goodWhen: 'up',
        state: 'ok',
        detail: 'توضیح.',
        provenance,
      },
    ],
    pendingApprovals: [],
    pendingApprovalsTotal: 3,
    events: [],
    emergencyActions: [],
  });
}

function overview(overrides: Partial<TelemetryOverview> = {}): TelemetryOverview {
  return {
    containersHealthy: 0,
    containersDegraded: 0,
    containersDown: 0,
    containersUnknown: 0,
    gatesPass: 0,
    gatesBlocked: 0,
    gatesEvaluating: 0,
    gatesBypassPrevented: 0,
    worstContainer: 'HEALTHY',
    worstQueuePressure: 'OK',
    ...overrides,
  };
}

function automations(
  provenance: Provenance,
  sourceMode: TelemetrySnapshot['sourceMode'],
  summary: Partial<TelemetryOverview>,
): TelemetrySnapshot {
  return partial<TelemetrySnapshot>({
    generatedAt: '2026-10-07T09:30:00.000Z',
    scenario: 'test',
    provenance,
    sourceMode,
    summary: overview(summary),
  });
}

function byStatus(overrides: Partial<Record<ResolutionStatus, number>> = {}): Record<ResolutionStatus, number> {
  return {
    PENDING_REVIEW: 0,
    CLAIMED: 0,
    APPROVED: 0,
    REJECTED: 0,
    MODIFIED: 0,
    ESCALATED: 0,
    EXPIRED: 0,
    ...overrides,
  };
}

function hitl(
  provenance: HitlQueueSnapshot['provenance'],
  statuses: Partial<Record<ResolutionStatus, number>>,
  hasCriticalPending = false,
): HitlQueueSnapshot {
  return partial<HitlQueueSnapshot>({
    generatedAt: '2026-10-07T09:30:00.000Z',
    scenario: 'test',
    provenance,
    summary: { total: 0, bySeverity: {}, byStatus: byStatus(statuses), hasCriticalPending },
  });
}

function revenue(overrides: Partial<RevenueSummary> = {}): RevenueSummary {
  return {
    dailyGmvToman: 0,
    weeklyGmvToman: 0,
    aovToman: 0,
    pendingSettlementToman: 0,
    failedPaymentCount: 0,
    completedOrderCount: 0,
    pendingProcessingCount: 0,
    paidOrderCount: 0,
    ...overrides,
  };
}

function orders(provenance: Provenance, summary: Partial<RevenueSummary>, lastUpdates: string[] = []): CommerceSnapshot {
  return partial<CommerceSnapshot>({
    generatedAt: '2026-10-07T09:30:00.000Z',
    scenario: 'test',
    provenance,
    orders: lastUpdates.map((lastUpdateUtc) => ({ lastUpdateUtc })),
    summary: revenue(summary),
  });
}

function invSummary(overrides: Partial<InventorySummary> = {}): InventorySummary {
  return {
    totalSkus: 0,
    lowStockCount: 0,
    outOfStockCount: 0,
    driftCount: 0,
    pendingSyncCount: 0,
    syncErrorCount: 0,
    totalStockUnits: 0,
    ...overrides,
  };
}

function inventory(provenance: Provenance, summary: Partial<InventorySummary>): InventorySnapshot {
  return partial<InventorySnapshot>({
    generatedAt: '2026-10-07T09:30:00.000Z',
    scenario: 'test',
    provenance,
    summary: invSummary(summary),
  });
}

/** Every card the plane renders is proven: green requires a LIVE reading. */
function assertNotGreenWithoutLive(model: BusinessCardModel): void {
  assert.notEqual(model.status.tone, 'success');
  assert.notEqual(model.status.code, 'OK');
}

describe('assertBusinessCard — permitted business vocabulary', () => {
  it('accepts SKU on a card (owner ruling 2026-10-07: canonical commerce term)', () => {
    const model = card({ headline: 'کاهش ۳۸٪ قیمت پیشنهادی برای ۴ SKU.' });
    assert.equal(assertBusinessCard(model), model);
  });

  it('accepts SKU in a metric label and value', () => {
    const model = card({ metrics: [{ label: 'کل SKUها', value: '۱۴', tip: 'شمارش کالاها.' }] });
    assert.equal(assertBusinessCard(model), model);
  });

  it('accepts the mandated English status codes beside a Persian label', () => {
    const model = card({ status: { tone: 'warning', label: 'نیازمند بررسی', code: 'REVIEW' } });
    assert.equal(assertBusinessCard(model), model);
  });

  it('accepts «بدون داده» only when the data really is unavailable', () => {
    const unavailable: Pick<BusinessCardModel, 'status' | 'provenance'> = {
      status: { tone: 'danger', label: 'بدون داده', code: 'NO_DATA' },
      provenance: { tone: 'danger', label: 'بدون داده', code: 'NO_DATA' },
    };
    assert.ok(assertBusinessCard(card(unavailable)));
    // …and never lets an unavailable source claim a reviewable state.
    assert.throws(
      () => assertBusinessCard(card({ ...unavailable, status: { tone: 'warning', label: 'نیازمند بررسی', code: 'REVIEW' } })),
      /unavailable data must be reported/,
    );
  });
});

describe('assertBusinessCard — rejects console-only vocabulary', () => {
  const consoleOnlyTerms = [
    'سایدکار',
    'پروب',
    'کانتینر',
    'تلمتری',
    'لجر',
    'latency',
    'HTTP',
    'D-121',
    'sidecar',
    'V-01',
    'V-10',
  ];

  for (const term of consoleOnlyTerms) {
    it(`rejects "${term}"`, () => {
      assert.throws(
        () => assertBusinessCard(card({ headline: `وضعیت ${term} فروشگاه.` })),
        /fail-closed violation/,
      );
    });
  }

  it('names the offending term in the failure, so the defect is diagnosable', () => {
    assert.throws(
      () => assertBusinessCard(card({ title: 'پروب سایدکار' })),
      (error: Error) => error.message.includes('operational jargon') && error.message.includes('پروب'),
    );
  });
});

describe('assertBusinessCard — structural fail-closed rules', () => {
  it('rejects an empty string anywhere on the card', () => {
    assert.throws(() => assertBusinessCard(card({ headline: '   ' })), /empty string/);
  });

  it('rejects a card with no metric', () => {
    assert.throws(() => assertBusinessCard(card({ metrics: [] })), /no metric/);
  });

  it('rejects a green status without a live reading (D-171 §2.2)', () => {
    assert.throws(
      () => assertBusinessCard(card({ status: { tone: 'success', label: 'عادی', code: 'OK' } })),
      /green status without a live reading/,
    );
  });

  it('accepts a green status when the reading is live', () => {
    const model = card({
      status: { tone: 'success', label: 'عادی', code: 'OK' },
      provenance: { tone: 'success', label: 'خوانش زنده', code: 'LIVE' },
    });
    assert.equal(assertBusinessCard(model), model);
  });

  it('rejects unavailable data reported as anything other than «بدون داده»', () => {
    assert.throws(
      () =>
        assertBusinessCard(
          card({
            provenance: { tone: 'danger', label: 'بدون داده', code: 'NO_DATA' },
            status: { tone: 'warning', label: 'نیازمند بررسی', code: 'REVIEW' },
          }),
        ),
      /unavailable data must be reported/,
    );
  });
});

describe('dashboardBusinessCard — executive ladder', () => {
  it('reports «بدون داده» when no source is connected, even if services look healthy', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'ok'], 'unavailable'));
    assert.equal(model.status.code, 'NO_DATA');
    assert.equal(model.provenance.code, 'NO_DATA');
    assert.match(model.headline, /بدون داده/);
    assertNotGreenWithoutLive(model);
  });

  it('never claims a healthy store on mock data', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'ok'], 'mock'));
    assert.equal(model.status.code, 'UNKNOWN');
    assert.match(model.headline, /نامشخص|نیازمند بررسی/);
    assertNotGreenWithoutLive(model);
  });

  it('reports ACTION when the worst service is degraded', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'degraded'], 'mock'));
    assert.equal(model.status.code, 'ACTION');
  });

  it('reports REVIEW when the worst service is unavailable', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'unavailable'], 'mock'));
    assert.equal(model.status.code, 'REVIEW');
  });

  it('reports UNKNOWN when the worst service state is unknown', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'unknown'], 'mock'));
    assert.equal(model.status.code, 'UNKNOWN');
  });

  it('is green only on a live, fully healthy reading', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'ok'], 'live'));
    assert.equal(model.status.code, 'OK');
    assert.equal(model.status.tone, 'success');
    assert.equal(model.provenance.code, 'LIVE');
  });

  it('renders counts in Persian digits and derives "sections needing review"', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'degraded', 'unknown'], 'mock'));
    const labels = model.metrics.map((metric) => metric.label);
    assert.deepEqual(labels, [
      'سفارش‌های امروز',
      'کارهای در انتظار تصمیم شما',
      'بخش‌های آمادهٔ فروشگاه',
      'بخش‌های نیازمند بررسی',
    ]);
    assert.equal(model.metrics[1]?.value, '۳');
    assert.equal(model.metrics[2]?.value, '۱ از ۳');
    assert.equal(model.metrics[3]?.value, '۲');
  });

  it('never lets several failures hide behind a healthy majority', () => {
    const model = dashboardBusinessCard(dashboard(['ok', 'ok', 'ok', 'degraded'], 'mock'));
    assert.equal(model.status.code, 'ACTION');
    assert.equal(model.metrics[3]?.value, '۱');
  });
});

describe('automationsBusinessCard — automation ladder', () => {
  it('reports «بدون داده» when no probe produced a reading', () => {
    const model = automationsBusinessCard(automations('unavailable', 'LIVE', { containersHealthy: 5 }));
    assert.equal(model.status.code, 'NO_DATA');
    assert.equal(model.provenance.code, 'NO_DATA');
    assert.match(model.headline, /بدون داده/);
    assertNotGreenWithoutLive(model);
  });

  it('reports ACTION when a container is down', () => {
    const model = automationsBusinessCard(
      automations('mock', 'MOCK', { worstContainer: 'DOWN', containersDown: 1 }),
    );
    assert.equal(model.status.code, 'ACTION');
  });

  it('reports REVIEW when a container is degraded and UNKNOWN when unknown', () => {
    assert.equal(
      automationsBusinessCard(automations('mock', 'MOCK', { worstContainer: 'DEGRADED' })).status.code,
      'REVIEW',
    );
    assert.equal(
      automationsBusinessCard(automations('mock', 'MOCK', { worstContainer: 'UNKNOWN' })).status.code,
      'UNKNOWN',
    );
  });

  it('never claims a healthy automation fleet from the mock source', () => {
    const model = automationsBusinessCard(
      automations('mock', 'MOCK', { containersHealthy: 5, gatesPass: 9, worstContainer: 'HEALTHY' }),
    );
    assert.equal(model.status.code, 'UNKNOWN');
    assertNotGreenWithoutLive(model);
  });

  it('is green only on a live source with every gate settled', () => {
    const clean = automationsBusinessCard(
      automations('live', 'LIVE', { containersHealthy: 5, gatesPass: 10, worstContainer: 'HEALTHY' }),
    );
    assert.equal(clean.status.code, 'OK');
    assert.equal(clean.metrics[2]?.value, '۱۰');

    const waiting = automationsBusinessCard(
      automations('live', 'LIVE', { containersHealthy: 5, gatesBlocked: 1, worstContainer: 'HEALTHY' }),
    );
    assert.equal(waiting.status.code, 'UNKNOWN');
    assertNotGreenWithoutLive(waiting);
  });

  it('counts robots needing review and gates awaiting evidence', () => {
    const model = automationsBusinessCard(
      automations('mock', 'MOCK', {
        containersHealthy: 2,
        containersDegraded: 1,
        containersDown: 1,
        containersUnknown: 1,
        gatesBlocked: 1,
        gatesEvaluating: 1,
      }),
    );
    assert.equal(model.metrics[0]?.value, '۲');
    assert.equal(model.metrics[1]?.value, '۳');
    assert.equal(model.metrics[3]?.value, '۲');
  });
});

describe('hitlBusinessCard — human review ladder', () => {
  it('reports «بدون داده» when the queue is not connected', () => {
    const model = hitlBusinessCard(hitl('unavailable', { PENDING_REVIEW: 3 }, true));
    assert.equal(model.status.code, 'NO_DATA');
    assertNotGreenWithoutLive(model);
  });

  it('reports ACTION when a critical item is waiting', () => {
    const model = hitlBusinessCard(hitl('mock', { PENDING_REVIEW: 3 }, true));
    assert.equal(model.status.code, 'ACTION');
    assert.match(model.headline, /فوری/);
  });

  it('reports REVIEW when items are waiting but none is critical', () => {
    const model = hitlBusinessCard(hitl('mock', { PENDING_REVIEW: 2 }, false));
    assert.equal(model.status.code, 'REVIEW');
    assert.equal(model.metrics[0]?.value, '۲');
  });

  it('states plainly when nothing is waiting', () => {
    const mockModel = hitlBusinessCard(hitl('mock', {}, false));
    assert.match(mockModel.headline, /هیچ کاری در انتظار تصمیم شما نیست/);
    assert.equal(mockModel.status.code, 'UNKNOWN');
  });

  it('is green only on a live, empty queue', () => {
    const model = hitlBusinessCard(hitl('live', {}, false));
    assert.equal(model.status.code, 'OK');
    assert.equal(model.provenance.code, 'LIVE');
  });

  it('sums decided and expired items independently', () => {
    const model = hitlBusinessCard(
      hitl('live', { APPROVED: 2, REJECTED: 1, MODIFIED: 1, EXPIRED: 4, CLAIMED: 3 }),
    );
    assert.equal(model.metrics[1]?.value, '۳');
    assert.equal(model.metrics[2]?.value, '۴');
    assert.equal(model.metrics[3]?.value, '۴');
  });
});

describe('ordersBusinessCard — commerce ladder', () => {
  it('reports «بدون داده» when the order book is not connected', () => {
    const model = ordersBusinessCard(orders('unavailable', { failedPaymentCount: 2 }));
    assert.equal(model.status.code, 'NO_DATA');
    assert.match(model.headline, /بدون داده/);
    assertNotGreenWithoutLive(model);
  });

  it('reports ACTION when a payment failed', () => {
    const model = ordersBusinessCard(orders('mock', { failedPaymentCount: 2 }));
    assert.equal(model.status.code, 'ACTION');
    assert.match(model.headline, /۲ پرداخت ناموفق/);
  });

  it('reports PROCESSING while orders are being prepared', () => {
    const model = ordersBusinessCard(orders('mock', { pendingProcessingCount: 4, completedOrderCount: 3 }));
    assert.equal(model.status.code, 'PROCESSING');
    assert.equal(model.metrics[0]?.value, '۴');
    assert.equal(model.metrics[1]?.value, '۳');
  });

  it('states that no order is waiting rather than implying success on mock data', () => {
    const model = ordersBusinessCard(orders('mock', {}));
    assert.equal(model.status.code, 'UNKNOWN');
    assert.match(model.headline, /بر پایهٔ دادهٔ نمونه/);
    assertNotGreenWithoutLive(model);
  });

  it('is green only on a live order book with nothing outstanding', () => {
    const model = ordersBusinessCard(orders('live', {}));
    assert.equal(model.status.code, 'OK');
    assert.equal(model.provenance.code, 'LIVE');
  });

  it('reports the newest order update and «نامشخص» when there is none', () => {
    const empty = ordersBusinessCard(orders('mock', {}));
    assert.equal(empty.metrics[3]?.value, 'نامشخص');

    const filled = ordersBusinessCard(
      orders('mock', {}, ['2026-10-07T08:00:00.000Z', '2026-10-07T09:30:00.000Z']),
    );
    assert.equal(filled.metrics[3]?.value, '09:30 UTC');
  });
});

describe('inventoryBusinessCard — stock ladder', () => {
  it('reports «بدون داده» when no catalogue source is connected', () => {
    const model = inventoryBusinessCard(inventory('unavailable', { outOfStockCount: 1 }));
    assert.equal(model.status.code, 'NO_DATA');
    assert.match(model.headline, /بدون داده/);
    assertNotGreenWithoutLive(model);
  });

  it('reports ACTION when stock is out, drifting or failing to sync', () => {
    assert.equal(inventoryBusinessCard(inventory('mock', { outOfStockCount: 1 })).status.code, 'ACTION');
    assert.equal(inventoryBusinessCard(inventory('mock', { driftCount: 1 })).status.code, 'ACTION');
    assert.equal(inventoryBusinessCard(inventory('mock', { syncErrorCount: 1 })).status.code, 'ACTION');
  });

  it('reports REVIEW when stock is only low or a sync is pending', () => {
    assert.equal(inventoryBusinessCard(inventory('mock', { lowStockCount: 3 })).status.code, 'REVIEW');
    assert.equal(inventoryBusinessCard(inventory('mock', { pendingSyncCount: 2 })).status.code, 'REVIEW');
  });

  it('never calls the catalogue healthy on mock data', () => {
    const model = inventoryBusinessCard(inventory('mock', { totalSkus: 14 }));
    assert.equal(model.status.code, 'UNKNOWN');
    assert.match(model.headline, /بر پایهٔ دادهٔ نمونه/);
    assertNotGreenWithoutLive(model);
  });

  it('is green only on a live, fully reconciled catalogue', () => {
    const model = inventoryBusinessCard(inventory('live', { totalSkus: 14, totalStockUnits: 120 }));
    assert.equal(model.status.code, 'OK');
    assert.equal(model.provenance.code, 'LIVE');
  });

  it('states the shortage in plain Persian and counts drifted and pending syncs', () => {
    const model = inventoryBusinessCard(
      inventory('mock', { outOfStockCount: 1, lowStockCount: 3, driftCount: 2, pendingSyncCount: 1, syncErrorCount: 1 }),
    );
    assert.match(model.headline, /۱ کالا تمام شده و ۳ کالا رو به اتمام است/);
    assert.equal(model.metrics[2]?.value, '۲');
    assert.equal(model.metrics[3]?.value, '۲');
  });
});

describe('fail-closed invariant across every card', () => {
  const builders: Array<[string, () => BusinessCardModel]> = [
    ['dashboard', () => dashboardBusinessCard(dashboard(['ok', 'ok'], 'mock'))],
    ['automations', () => automationsBusinessCard(automations('mock', 'MOCK', { containersHealthy: 5 }))],
    ['hitl', () => hitlBusinessCard(hitl('mock', {}, false))],
    ['orders', () => ordersBusinessCard(orders('mock', {}))],
    ['inventory', () => inventoryBusinessCard(inventory('mock', { totalSkus: 14 }))],
  ];

  for (const [name, build] of builders) {
    it(`${name}: mock data is never green and always carries a metric`, () => {
      const model = build();
      assertNotGreenWithoutLive(model);
      assert.ok(model.metrics.length > 0, 'a card without a metric must not render');
      assert.ok(model.headline.trim().length > 0, 'a card without a headline must not render');
    });

    it(`${name}: the guard accepts its own output (no self-contradiction)`, () => {
      const model = build();
      assert.equal(assertBusinessCard(model), model);
    });
  }
});
