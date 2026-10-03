import { StatusBadge, type StatusState } from '@/components/ui/status-badge';

/**
 * Connection state for one dependency.
 *
 * Every field is nullable: a dependency whose state has not been measured is
 * `unknown`, never assumed healthy (D-171 §2.2).
 */
export interface DependencyState {
  id: 'postgres' | 'n8n' | 'redis';
  label: string;
  state: StatusState;
  /** Human-readable evidence or the reason it is unknown. */
  detail: string;
}

/**
 * The real probe is wired in Phase 27.3. Until then the banner reports the
 * honest state: nothing is connected, so every dependency is UNKNOWN.
 *
 * This function is the single seam a later phase replaces — it is async and
 * returns `DependencyState[]`, so the swap needs no component changes.
 */
export async function getDependencyStates(): Promise<DependencyState[]> {
  return [
    {
      id: 'postgres',
      label: 'PostgreSQL (SSOT)',
      state: 'unknown',
      detail: 'اتصال زنده هنوز برقرار نشده است',
    },
    {
      id: 'n8n',
      label: 'n8n',
      state: 'unknown',
      detail: 'وب‌هوک هنوز پیکربندی نشده است',
    },
    {
      id: 'redis',
      label: 'Redis',
      state: 'unknown',
      detail: 'صف هنوز بررسی نشده است',
    },
  ];
}

/** The environment the control plane is pointing at. */
export function getEnvironment(): { name: string; state: StatusState } {
  return { name: 'local', state: 'unknown' };
}

export function SystemStatus({ dependencies }: { dependencies: DependencyState[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="وضعیت اتصال سرویس‌ها">
      {dependencies.map((dep) => (
        <li key={dep.id}>
          <StatusBadge state={dep.state} detail={dep.label} />
        </li>
      ))}
    </ul>
  );
}
