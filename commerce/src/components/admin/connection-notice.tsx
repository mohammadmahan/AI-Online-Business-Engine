import { Banner } from '@/components/ui/primitives';
import { DB_NOT_CONFIGURED_MESSAGE } from '@/server/db-context';

/**
 * D-172 §2 — fail-closed connection notice (D-171 §2.2).
 *
 * Every admin page renders this instead of an empty table when the canonical
 * database is not configured: an empty grid reads as "you have no products",
 * which is a false statement, while "nothing is connected" is the truth. It is
 * also the reason no page ever falls back to invented sample data.
 */
export function ConnectionMissing({ what }: { what: string }) {
  return (
    <Banner
      tone="warning"
      title={`${what} نمایش داده نمی‌شود — اتصال پایگاهِ دادهٔ مرجع تنظیم نشده است`}
    >
      {DB_NOT_CONFIGURED_MESSAGE}
    </Banner>
  );
}
