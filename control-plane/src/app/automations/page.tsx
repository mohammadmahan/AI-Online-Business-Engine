import type { Metadata } from 'next';

import { PageShell } from '@/components/page-shell';

export const metadata: Metadata = {
  title: 'اتوماسیون‌ها',
};

export default function Page() {
  return <PageShell href="/automations" />;
}
