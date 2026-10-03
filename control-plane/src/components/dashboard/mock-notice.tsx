import { FlaskConical, PlugZap } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import type { Provenance } from '@/types/telemetry';

/**
 * Provenance notice.
 *
 * The dashboard renders deterministic samples, so it says so before any number
 * is read. A mocked green is not a verified green — presenting mock data
 * without this label would violate the fail-closed rule (D-171 §2.2).
 *
 * The wording follows the snapshot's own provenance: in the `all-unknown`
 * scenario nothing is even sampled, so the notice must not claim that mock
 * values exist.
 */
export function MockNotice({
  scenario,
  provenance,
}: {
  scenario: string;
  provenance: Provenance;
}) {
  if (provenance === 'unavailable') {
    return (
      <div
        className="flex flex-wrap items-center gap-3 rounded-[--radius-cp] border border-danger bg-surface p-3"
        role="note"
      >
        <ToneBadge tone="danger" label="بدون داده" code="NO_DATA" Icon={PlugZap} />
        <p className="text-cp-label text-ink">
          هیچ سرویسی متصل نیست و هیچ اندازه‌گیری‌ای انجام نشده است؛ همه‌ی
          وضعیت‌ها <strong>نامشخص (UNKNOWN)</strong> هستند — نه صفر، نه موفق.
          سناریو: <span className="font-mono text-cp-caption">{scenario}</span>
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-wrap items-center gap-3 rounded-[--radius-cp] border border-warning bg-surface p-3"
      role="note"
    >
      <ToneBadge tone="warning" label="داده‌ی نمونه" code="MOCK" Icon={FlaskConical} />
      <p className="text-cp-label text-ink">
        هیچ سرویسی متصل نیست؛ مقادیر این صفحه نمونه‌ی قطعی هستند و{' '}
        <strong>شاهد</strong> محسوب نمی‌شوند. سناریو:{' '}
        <span className="font-mono text-cp-caption">{scenario}</span> — اتصال
        زنده در فاز سیم‌کشی زنده (Live Wiring) انجام می‌شود.
      </p>
    </div>
  );
}