import type { Metadata, Viewport } from 'next';
import { Vazirmatn } from 'next/font/google';

import { Header } from '@/components/header';
import { Sidebar } from '@/components/sidebar';
import {
  VIEW_MODE_BOOTSTRAP,
  ViewModeProvider,
} from '@/lib/context/view-mode-context';
import { activeHitlScenario, mockQueue } from '@/lib/mock/hitl-data';
import { THEME_BOOTSTRAP } from '@/lib/theme';

import './globals.css';

/**
 * Vazirmatn is the D-171 typographic hierarchy (§3.1).
 *
 * `next/font` downloads and SELF-HOSTS the font at build time, so the running
 * control plane makes zero external network calls for typography — unlike the
 * legacy `dashboard/` snapshot, which links a CDN. `display: 'swap'` is the
 * required `font-display: swap`; the declared stack in `globals.css` keeps
 * `system-ui` as the fallback so text always renders.
 */
const vazirmatn = Vazirmatn({
  subsets: ['arabic', 'latin'],
  display: 'swap',
  variable: '--font-vazirmatn',
});

export const metadata: Metadata = {
  title: {
    default: 'صفحهٔ کنترل یکپارچه — D-171',
    template: '%s · صفحهٔ کنترل',
  },
  description:
    'داشبورد عملیاتی یکپارچه برای موتور کسب‌وکار (D-171). فقط‌خواندنی، fail-closed و بدون اعتبارنامه.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Zoom is never disabled (D-171 §3 / "disable zoom" anti-pattern).
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  /**
   * Pending human reviews, for the shell's sidebar badge (Phase 27.10). It is
   * read from the SAME deterministic source `/hitl-queue` renders — the count
   * is computed synchronously at render time, so no second data layer, no
   * client fetch and no credential is introduced, and the badge can never
   * disagree with the queue it points at. A queue that yields no readable
   * count renders no badge rather than a reassuring zero.
   */
  const hitlPending = mockQueue(activeHitlScenario()).summary.byStatus.PENDING_REVIEW;

  return (
    // RTL is the default for the entire control plane (D-171 §3.1).
    <html
      lang="fa"
      dir="rtl"
      data-theme="light"
      data-view-mode="business"
      className={vazirmatn.variable}
      suppressHydrationWarning
    >
      <head>
        {/* Applies the stored/system theme before first paint (no flash). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        {/* Applies the stored view mode (default: business) before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: VIEW_MODE_BOOTSTRAP }} />
      </head>
      <body className="min-h-dvh">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:start-2 focus:z-50 focus:rounded-[--radius-cp] focus:bg-primary focus:px-4 focus:py-2 focus:text-surface"
        >
          پرش به محتوای اصلی
        </a>
        <ViewModeProvider>
          <div className="flex min-h-dvh flex-col">
            <Header />
            <div className="flex flex-1 flex-col md:flex-row">
              <aside className="md:w-64 md:shrink-0">
                <Sidebar hitlPending={hitlPending} />
              </aside>
              <main id="main-content" tabIndex={-1} className="flex-1 p-4 sm:p-6">
                {children}
              </main>
            </div>
          </div>
        </ViewModeProvider>
      </body>
    </html>
  );
}
