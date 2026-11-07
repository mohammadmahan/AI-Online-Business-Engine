'use client';

import Link from 'next/link';
import { useState } from 'react';

import {
  Banner,
  Card,
  CardHeader,
  Field,
  Table,
  Td,
  Th,
  buttonClass,
  inputClass,
} from '@/components/ui/primitives';
import type { CategoryAdminRow } from '@/server/repository';
import { formatCountFa, formatDateFa } from '@/lib/format';
import { cn } from '@/lib/utils';
import { createCategoryAction } from '@/server/actions/categories';

/**
 * D-172 §1.1 — category management UI.
 *
 * Creation only, on purpose: a rename changes storefront copy and a delete is
 * blocked by the products that reference the category (FK RESTRICT), so neither
 * is offered without an owner decision. The product count is shown for exactly
 * that reason — it answers "why can't I remove this?" before it is asked.
 */

type Result =
  | { kind: 'idle' }
  | { kind: 'ok'; name: string; slug: string }
  | { kind: 'error'; message: string; field?: string };

export function CategoryManager({ categories }: { categories: CategoryAdminRow[] }) {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [result, setResult] = useState<Result>({ kind: 'idle' });
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) {
      return;
    }
    setBusy(true);
    setResult({ kind: 'idle' });
    try {
      const response = await createCategoryAction({
        name,
        slug,
        description: description === '' ? null : description,
      });
      if (response.ok) {
        setResult({ kind: 'ok', name: response.data.name, slug: response.data.slug });
        setName('');
        setSlug('');
        setDescription('');
        return;
      }
      setResult({ kind: 'error', message: response.message, field: response.field });
    } catch {
      setResult({ kind: 'error', message: 'ثبت دسته انجام نشد؛ دوباره تلاش کنید.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {result.kind === 'ok' ? (
        <Banner tone="success" title="دسته ثبت شد">
          دستهٔ «{result.name}» با نشانی <span className="cp-code">{result.slug}</span> ساخته شد و
          اکنون در فرم افزودن محصول قابل انتخاب است.
        </Banner>
      ) : null}
      {result.kind === 'error' ? (
        <Banner tone="danger" title="ثبت دسته انجام نشد">
          {result.message}
          {result.field ? <span className="cp-code"> [{result.field}]</span> : null}
        </Banner>
      ) : null}

      <Card>
        <CardHeader
          title="دستهٔ جدید"
          description="نام فارسی برای فروشگاه، نشانی لاتین برای آدرس صفحه."
        />
        <form className="grid gap-4 md:grid-cols-2" onSubmit={(event) => void submit(event)}>
          <Field label="نام دسته" htmlFor="category-name" required hint="مثال: مانتو کتانی">
            <input
              id="category-name"
              className={inputClass}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field
            label="نشانی (slug)"
            htmlFor="category-slug"
            required
            hint="فقط حروف کوچک لاتین، عدد و خط تیره — مثال: manto-ketani"
          >
            <input
              id="category-slug"
              className={cn(inputClass, 'cp-code')}
              dir="ltr"
              value={slug}
              onChange={(event) => setSlug(event.target.value.toLowerCase())}
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="توضیح" htmlFor="category-description" hint="اختیاری — تا ۲۰۰۰ نویسه">
              <textarea
                id="category-description"
                className={inputClass}
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </div>
          <div className="md:col-span-2">
            <button type="submit" className={buttonClass.primary} disabled={busy}>
              {busy ? 'در حال ثبت…' : 'ثبت دسته'}
            </button>
          </div>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="دسته‌های موجود"
          description="تعداد محصولات هر دسته؛ دستهٔ دارای محصول قابل حذف نیست."
          action={
            <Link className={buttonClass.neutral} href="/admin/products/new">
              افزودن محصول
            </Link>
          }
        />
        {categories.length === 0 ? (
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            هنوز دسته‌ای ثبت نشده است. فرم بالا را پر کنید تا فرم افزودن محصول فعال شود.
          </p>
        ) : (
          <Table
            caption="فهرست دسته‌بندی‌ها"
            head={
              <tr>
                <Th>نام</Th>
                <Th>نشانی</Th>
                <Th>توضیح</Th>
                <Th>محصولات</Th>
                <Th>تاریخ ساخت</Th>
              </tr>
            }
          >
            {categories.map((category) => (
              <tr key={category.id}>
                <Td>{category.name}</Td>
                <Td>
                  <span className="cp-code">{category.slug}</span>
                </Td>
                <Td>{category.description === null ? '—' : category.description}</Td>
                <Td>{formatCountFa(category.productCount)}</Td>
                <Td>{formatDateFa(category.createdAt)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
