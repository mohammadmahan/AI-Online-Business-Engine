import type { Metadata } from 'next';

import { AssistantConsole } from '@/components/admin/assistant-console';
import { PageHeader } from '@/components/ui/primitives';

export const metadata: Metadata = { title: 'دستیار هوش مصنوعی' };
export const dynamic = 'force-dynamic';

/**
 * D-172 §4.1 — merchant-facing AI copy assistant.
 *
 * The page has no database read. The server action behind it contacts only the
 * loopback Python bridge, which runs the canonical fashion engine against local
 * Ollama in dry-run mode. A missing bridge/model is a refusal, never a fake
 * proposal.
 */
export default function AssistantPage() {
  return (
    <>
      <PageHeader
        title="دستیار هوش مصنوعی"
        description="پیشنهاد متن محصول با مدل محلی؛ فقط برای بازبینی، بدون ذخیره یا انتشار خودکار."
      />
      <AssistantConsole />
    </>
  );
}
