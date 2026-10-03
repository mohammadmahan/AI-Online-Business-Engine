import type { Metadata } from 'next';

import { PageShell } from '@/components/page-shell';

export const metadata: Metadata = {
  title: 'صف تأیید انسانی',
};

export default function Page() {
  return <PageShell href="/hitl-queue" />;
}
