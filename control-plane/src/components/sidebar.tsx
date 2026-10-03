'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Boxes,
  BrainCircuit,
  LayoutDashboard,
  ListChecks,
  Receipt,
  Settings,
  Workflow,
} from 'lucide-react';

import { ROUTES, type RouteSpec } from '@/lib/routes';
import { cn } from '@/lib/utils';

const ICONS: Record<RouteSpec['href'], typeof LayoutDashboard> = {
  '/dashboard': LayoutDashboard,
  '/hitl-queue': ListChecks,
  '/inventory': Boxes,
  '/automations': Workflow,
  '/ai-engine': BrainCircuit,
  '/orders': Receipt,
  '/settings': Settings,
};

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="ناوبری اصلی"
      className="flex h-full flex-col gap-1 border-e border-edge bg-surface p-3"
    >
      <p className="mb-2 px-2 text-cp-caption font-medium text-ink-muted">
        صفحه‌ی کنترل
      </p>
      <ul className="flex flex-col gap-1">
        {ROUTES.map((route) => {
          const Icon = ICONS[route.href];
          const active = pathname === route.href;
          return (
            <li key={route.href}>
              <Link
                href={route.href}
                aria-current={active ? 'page' : undefined}
                title={route.description}
                className={cn(
                  'cp-target flex items-center gap-3 rounded-[--radius-cp]',
                  'px-3 py-2 text-cp-label font-medium transition-colors',
                  active
                    ? 'bg-primary text-surface'
                    : 'text-ink hover:bg-surface-muted',
                )}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                <span className="flex-1">{route.title}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
