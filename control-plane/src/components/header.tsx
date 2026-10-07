import { KillSwitchPlaceholder } from '@/components/kill-switch';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  SystemStatus,
  getDependencyStates,
  getEnvironment,
} from '@/components/system-status';
import { ThemeToggle } from '@/components/theme-toggle';
import { TechnicalOnly } from '@/components/ui/view-gate';
import { ViewSwitcher } from '@/components/view-switcher';

export async function Header() {
  const [dependencies, environment] = await Promise.all([
    getDependencyStates(),
    Promise.resolve(getEnvironment()),
  ]);

  return (
    <header className="border-b border-edge bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-cp-label font-semibold text-ink">
            موتور کسب‌وکار — صفحهٔ کنترل یکپارچه
          </p>
          {/* Environment identity is infrastructure metadata (Phase 27.13). */}
          <TechnicalOnly surface="shell-environment">
            <StatusBadge
              state={environment.state}
              detail={`محیط: ${environment.name}`}
            />
          </TechnicalOnly>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ViewSwitcher />
          {/* The emergency stop and the dependency strip are console assets:
              the umbrella switch itself stays in both views by design. */}
          <TechnicalOnly surface="shell-kill-switch">
            <KillSwitchPlaceholder />
          </TechnicalOnly>
          <ThemeToggle />
        </div>
      </div>
      <TechnicalOnly surface="shell-dependencies">
        <div className="border-t border-edge px-4 py-2">
          <SystemStatus dependencies={dependencies} />
        </div>
      </TechnicalOnly>
    </header>
  );
}
