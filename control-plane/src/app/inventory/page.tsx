import type { Metadata } from 'next';

import { PageShell } from '@/components/page-shell';

export const metadata: Metadata = {
  title: 'موجودی و محصولات',
};

export default function Page() {
  return <PageShell href="/inventory" />;
}
