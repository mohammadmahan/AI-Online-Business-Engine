import type { Metadata } from 'next';

import { PageShell } from '@/components/page-shell';

export const metadata: Metadata = {
  title: 'موتور هوش مصنوعی',
};

export default function Page() {
  return <PageShell href="/ai-engine" />;
}
