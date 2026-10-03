import { KillSwitchPlaceholder } from '@/components/kill-switch';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  SystemStatus,
  getDependencyStates,
  getEnvironment,
} from '@/components/system-status';
import { ThemeToggle } from '@/components/theme-toggle';

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
            موتور کسب‌وکار — صفحه‌ی کنترل یکپارچه
          </p>
          <StatusBadge
            state={environment.state}
            detail={`محیط: ${environment.name}`}
          />
        </div>
        <div className="flex items-center gap-2">
          <KillSwitchPlaceholder />
          <ThemeToggle />
        </div>
      </div>
      <div className="border-t border-edge px-4 py-2">
        <SystemStatus dependencies={dependencies} />
      </div>
    </header>
  );
}
