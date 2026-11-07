import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminLoginForm } from '@/components/admin/admin-login-form';
import { Banner, Card, PageHeader } from '@/components/ui/primitives';
import { adminAuthProblemMessage, readAdminAuthState } from '@/server/auth/admin-auth';
import { getAdminSession } from '@/server/auth/admin-request';

/**
 * D-172 Phase 4 — the panel's only public screen.
 *
 * It renders the form ONLY when the guard is configured; otherwise it states the
 * configuration problem and renders nothing that could accept a password. An
 * already-signed-in operator is sent straight on, so the login screen is never a
 * second, confusing place to be.
 */

export const metadata: Metadata = { title: 'ورود به پنل' };
export const dynamic = 'force-dynamic';

export default async function AdminLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const session = await getAdminSession();
  if (session !== null) {
    redirect('/admin');
  }

  const state = readAdminAuthState();
  const { next } = await searchParams;

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4">
      <PageHeader
        title="ورود به پنل مدیریت"
        description="این پنل تک‌کاربره است؛ نام کاربری و گذرواژهٔ مدیر فروشگاه را وارد کنید."
      />

      {state.configured ? (
        <Card>
          <AdminLoginForm next={next} />
        </Card>
      ) : (
        <Banner tone="danger" title="ورود تنظیم نشده است">
          {adminAuthProblemMessage(state.problem)}
          <span className="mt-2 block text-cp-caption">
            در فایل <span className="cp-code">commerce/.env</span> سه متغیر{' '}
            <span className="cp-code">ADMIN_USERNAME</span>،{' '}
            <span className="cp-code">ADMIN_PASSWORD_HASH</span> و{' '}
            <span className="cp-code">ADMIN_SESSION_SECRET</span> را تنظیم کنید (نمونه در{' '}
            <span className="cp-code">.env.example</span>). هش گذرواژه با{' '}
            <span className="cp-code">npm run admin:hash</span> ساخته می‌شود.
          </span>
        </Banner>
      )}
    </div>
  );
}
