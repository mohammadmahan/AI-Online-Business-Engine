'use client';

import { useState } from 'react';

import { buttonClass, inputClass, Field, Banner } from '@/components/ui/primitives';
import { loginAction } from '@/server/actions/admin-auth';

/**
 * D-172 Phase 4 — the sign-in form.
 *
 * The password is never kept in component state after the request: it is cleared
 * on failure so a shoulder-surfed screen or a retained render cannot replay it.
 * Success navigates from the server action's `redirect`, so this component has
 * no "next" logic of its own.
 */
export function AdminLoginForm({ next }: { next?: string }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await loginAction({ username, password, next });
      if (!result.ok) {
        setError(result.message);
        setPassword('');
      }
    } catch {
      // A server action that redirected throws a control-flow signal in some
      // runtimes; a real failure still has to be visible rather than silent.
      setError('ورود انجام نشد؛ دوباره تلاش کنید.');
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
      {error === null ? null : (
        <Banner tone="danger" title="ورود انجام نشد">
          {error}
        </Banner>
      )}

      <Field label="نام کاربری" htmlFor="admin-username" required>
        <input
          id="admin-username"
          name="username"
          className={inputClass}
          dir="ltr"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
      </Field>

      <Field label="گذرواژه" htmlFor="admin-password" required>
        <input
          id="admin-password"
          name="password"
          type="password"
          className={inputClass}
          dir="ltr"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={buttonClass.primary} disabled={busy}>
          {busy ? 'در حال بررسی…' : 'ورود'}
        </button>
        <span className="text-cp-caption text-ink-muted">
          نشست پس از ۸ ساعت منقضی می‌شود.
        </span>
      </div>
    </form>
  );
}
