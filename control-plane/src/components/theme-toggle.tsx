'use client';

import { Moon, Sun } from 'lucide-react';

import { toggleTheme, useTheme } from '@/lib/theme';
import { cn } from '@/lib/utils';

/**
 * Theme toggle. The accessible name states the resulting action; the icon is
 * decorative because the text label carries the meaning.
 */
export function ThemeToggle() {
  const theme = useTheme();
  const next = theme === 'light' ? 'تاریک' : 'روشن';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`تغییر پوسته به حالت ${next}`}
      className={cn(
        'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
        'border border-edge-strong bg-surface px-3 py-2',
        'text-cp-label text-ink transition-colors hover:bg-surface-muted',
      )}
    >
      {theme === 'light' ? (
        <Moon aria-hidden="true" className="size-4" />
      ) : (
        <Sun aria-hidden="true" className="size-4" />
      )}
      <span className="hidden sm:inline">{next}</span>
    </button>
  );
}
