'use client';

import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'cp-theme';

/**
 * Theme as an EXTERNAL STORE rather than component state.
 *
 * The source of truth is `document.documentElement.dataset.theme`, which a
 * tiny inline script sets before first paint (see `layout.tsx`) so the correct
 * theme is applied without a flash. React subscribes to it with
 * `useSyncExternalStore`, so there is no setState-in-effect and no hydration
 * mismatch — during hydration the server snapshot (`light`) is used.
 */
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

/** Current theme, read from the DOM attribute the pre-paint script set. */
export function getSnapshot(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

/** Server / hydration snapshot — always `light`, matching the initial markup. */
export function getServerSnapshot(): Theme {
  return 'light';
}

/** Apply a theme. A storage failure never breaks the toggle. */
export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* storage unavailable — the DOM attribute still applies the theme */
  }
  emit();
}

export function toggleTheme(): void {
  setTheme(getSnapshot() === 'light' ? 'dark' : 'light');
}

/**
 * The pre-paint bootstrap, serialized into a `<script>` in the document head.
 * Runs before first paint so the theme is correct immediately.
 */
export const THEME_BOOTSTRAP = `(function(){try{var k='${STORAGE_KEY}';var s=null;try{s=localStorage.getItem(k)}catch(e){}var t=(s==='light'||s==='dark')?s:(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='light';}})();`;

/** Subscribe-based hook for components that need the current theme. */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
