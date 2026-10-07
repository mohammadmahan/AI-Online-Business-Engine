'use client';

import {
  createContext,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

/**
 * D-171 §2.3 — dual-view architecture (Phase 27.9).
 *
 * ONE panel, TWO distinct views. `business` (نمای مدیریت فروشگاه) is the
 * DEFAULT; `technical` (کنسول زیرساخت و عیب‌یابی) is the secondary view. This
 * module owns PRESENTATION STATE ONLY — it never touches a data source, a live
 * probe seam, the sidecar client, or the D-121 ledger (D-171 constraints).
 *
 * The source of truth is `document.documentElement.dataset.viewMode`, which a
 * tiny inline script sets before first paint (see `VIEW_MODE_BOOTSTRAP`), so
 * the correct view applies with no flash and no hydration mismatch. React
 * subscribes with `useSyncExternalStore`; the server/hydration snapshot is
 * `business` — exactly the D-171 default — so the server markup is stable.
 *
 * Fail-closed: a missing, empty, unreadable, or unrecognised preference always
 * resolves to `business`; storage errors never throw and never change the
 * active view.
 */

/** The two legal view tokens. A closed vocabulary — nothing else is valid. */
export type ViewMode = 'business' | 'technical';

/** localStorage key (exact name fixed by the Phase 27.9 directive). */
export const VIEW_MODE_STORAGE_KEY = 'control_plane_view_mode';

/** Fail-closed default: any missing/invalid/blocked signal resolves here. */
export const DEFAULT_VIEW_MODE: ViewMode = 'business';

/** Type guard over the closed vocabulary. */
export function isViewMode(value: unknown): value is ViewMode {
  return value === 'business' || value === 'technical';
}

const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** Subscribe to view changes (same tab via `emit`, other tabs via `storage`). */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

/** Current view, read from the DOM attribute the pre-paint script set. */
export function getViewModeSnapshot(): ViewMode {
  const value = document.documentElement.dataset.viewMode;
  return isViewMode(value) ? value : DEFAULT_VIEW_MODE;
}

/** Server / hydration snapshot — the D-171 default, matching the first markup. */
export function getViewModeServerSnapshot(): ViewMode {
  return DEFAULT_VIEW_MODE;
}

/**
 * Apply a view. A storage failure (private mode, storage disabled, quota)
 * never breaks the switch: the DOM attribute still applies the view, and a
 * later read simply falls back to the default rather than throwing.
 */
export function setViewMode(mode: ViewMode): void {
  document.documentElement.dataset.viewMode = mode;
  try {
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
  } catch {
    /* storage unavailable — the DOM attribute still applies the view */
  }
  emit();
}

/** Flip between the two views. */
export function toggleViewMode(): void {
  setViewMode(getViewModeSnapshot() === 'business' ? 'technical' : 'business');
}

/** The surface `useViewMode()` exposes. */
export interface ViewModeApi {
  mode: ViewMode;
  setMode: (mode: ViewMode) => void;
  toggleMode: () => void;
}

const ViewModeContext = createContext<ViewModeApi | null>(null);

/** Store-backed API; used by the provider and as the no-provider fallback. */
function useViewModeStore(): ViewModeApi {
  const mode = useSyncExternalStore(
    subscribe,
    getViewModeSnapshot,
    getViewModeServerSnapshot,
  );
  return useMemo(
    () => ({ mode, setMode: setViewMode, toggleMode: toggleViewMode }),
    [mode],
  );
}

/**
 * View scope for the shell. The store is global, so this boundary is thin: it
 * declares the view scope explicitly and gives `useViewMode()` a mounting
 * point without adding any per-instance state.
 */
export function ViewModeProvider({ children }: { children: ReactNode }) {
  const api = useViewModeStore();
  return (
    <ViewModeContext.Provider value={api}>{children}</ViewModeContext.Provider>
  );
}

/**
 * Read the active view and change it. Works inside `ViewModeProvider`; outside
 * a provider it reads the same global store directly, so a component can never
 * crash for want of the boundary.
 */
export function useViewMode(): ViewModeApi {
  const provided = useContext(ViewModeContext);
  const store = useViewModeStore();
  return provided ?? store;
}

/**
 * Pre-paint bootstrap, serialized into a `<script>` in the document head next
 * to the theme bootstrap (same pattern as `THEME_BOOTSTRAP`). It validates the
 * stored token against the closed vocabulary and defaults to `business` on ANY
 * failure (fail-closed), then writes the DOM attribute so the correct view is
 * in effect before first paint.
 */
export const VIEW_MODE_BOOTSTRAP = `(function(){try{var k='${VIEW_MODE_STORAGE_KEY}';var s=null;try{s=localStorage.getItem(k)}catch(e){}var m=(s==='business'||s==='technical')?s:'business';document.documentElement.dataset.viewMode=m;}catch(e){document.documentElement.dataset.viewMode='business';}})();`;
