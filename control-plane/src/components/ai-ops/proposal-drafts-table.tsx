import { PROPOSAL_STATE_META } from '@/components/ai-ops/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import type { AiProposalDraft } from '@/types/ai-ops';

/**
 * AI proposal drafts and their D-060/D-064 lifecycle (D-171 §5.5).
 *
 * READ-ONLY BY CONSTRUCTION: the canonical lifecycle advances only through a
 * HUMAN `decide()` call on the durable proposal — there is no auto-advance path
 * anywhere in `ai_proposal_lifecycle.py` — so this table renders the states and
 * offers no decision affordance at all. Deciding a proposal stays with the HITL
 * queue (`/hitl-queue`) and the canonical engine (D-050/D-064/D-168).
 */
function ProposalRow({ proposal }: { proposal: AiProposalDraft }) {
  const meta = PROPOSAL_STATE_META[proposal.state];

  return (
    <tr className="border-b border-edge last:border-b-0">
      <th scope="row" className="px-3 py-2 text-start align-top">
        <span className="block font-medium text-ink">{proposal.titleFa}</span>
        <span className="block font-mono text-cp-caption text-ink-muted" dir="ltr">
          {proposal.id}
        </span>
      </th>
      <td className="px-3 py-2 text-start align-top font-mono text-cp-caption text-ink-muted" dir="ltr">
        {proposal.routeId}
      </td>
      <td className="px-3 py-2 text-start align-top">
        <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
      </td>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink-muted">
        <time dateTime={proposal.submittedAtUtc}>{formatTimeUtc(proposal.submittedAtUtc)}</time> UTC
      </td>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink-muted">
        {proposal.decidedAtUtc === null ? (
          'در انتظار تصمیم'
        ) : (
          <>
            <time dateTime={proposal.decidedAtUtc}>{formatTimeUtc(proposal.decidedAtUtc)}</time> UTC
          </>
        )}
      </td>
      <td className="px-3 py-2 text-start align-top font-mono text-cp-caption text-ink-muted" dir="ltr">
        {proposal.lastMutation}
      </td>
    </tr>
  );
}

export function ProposalDraftsTable({ proposals }: { proposals: AiProposalDraft[] }) {
  if (proposals.length === 0) {
    return (
      <div className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3">
        <p className="font-mono text-cp-caption text-ink-muted" dir="ltr">
          PROPOSALS: NONE_READ
        </p>
        <p className="mt-1 text-cp-caption text-ink-muted">
          هیچ پیش‌نویسی خوانده نشده است؛ نبودِ پیش‌نویس با «صفر پیش‌نویس» یکی نیست و هیچ شمارشی جعل
          نمی‌شود (fail-closed).
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-cp-label">
        <caption className="sr-only">
          پیش‌نویس‌های هوش مصنوعی و وضعیت چرخهٔ عمر آن‌ها؛ این جدول فقط‌خواندنی است و هیچ کنش
          تصمیم‌گیری ندارد
        </caption>
        <thead>
          <tr className="border-b border-edge-strong text-cp-caption text-ink-muted">
            <th scope="col" className="px-3 py-2 text-start">
              پیش‌نویس
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              مسیر
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              وضعیت
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              ثبت
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              تصمیم
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              آخرین تغییر
            </th>
          </tr>
        </thead>
        <tbody>
          {proposals.map((proposal) => (
            <ProposalRow key={proposal.id} proposal={proposal} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
