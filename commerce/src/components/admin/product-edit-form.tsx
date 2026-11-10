'use client';

import Link from 'next/link';
import { useState } from 'react';

import type { ProductUpdatePayload } from '@/contracts/catalog';
import {
  PRODUCT_STATUSES,
  PRODUCT_STATUS_LABELS,
  type MerchantProductStatus,
} from '@/lib/product-status';
import { updateProductAction } from '@/server/actions/products';
import { Banner, Card, CardHeader, Field, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.1 — the ADMIN EDIT form for an existing product.
 *
 * One product row, one server action. It deliberately omits variants, SKUs,
 * stock and photos: those have their own workflows (`/admin/inventory`,
 * `/admin/products/[id]/images`) and this page links to them instead of
 * duplicating them. Variants, inventory, media and orders are therefore preserved
 * by construction rather than by remembering not to touch them.
 *
 * On a refusal the submitted values stay in place (state is never reset) and the
 * server's Persian field messages are rendered next to their inputs with
 * `aria-invalid` / `aria-describedby`.
 */

export interface ProductEditInitialValues {
  id: string;
  categoryId: string;
  title: string;
  slug: string;
  basePrice: number;
  discountPrice: number | null;
  descriptionRaw: string;
  fabricType: string;
  season: string;
  careInstructions: string | null;
  status: MerchantProductStatus;
}

export interface ProductEditCategoryOption {
  id: string;
  name: string;
}

type Issue = { field: string; message: string };

type Result =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string; issues: Issue[] };

export function ProductEditForm({
  product,
  categories,
}: {
  product: ProductEditInitialValues;
  categories: ProductEditCategoryOption[];
}) {
  const [title, setTitle] = useState(product.title);
  const [slug, setSlug] = useState(product.slug);
  const [categoryId, setCategoryId] = useState(product.categoryId);
  const [basePrice, setBasePrice] = useState<number | ''>(product.basePrice);
  const [discountPrice, setDiscountPrice] = useState<number | ''>(product.discountPrice ?? '');
  const [descriptionRaw, setDescriptionRaw] = useState(product.descriptionRaw);
  const [fabricType, setFabricType] = useState(product.fabricType);
  const [season, setSeason] = useState(product.season);
  const [careInstructions, setCareInstructions] = useState(product.careInstructions ?? '');
  const [status, setStatus] = useState<MerchantProductStatus>(product.status);
  const [result, setResult] = useState<Result>({ kind: 'idle' });

  const busy = result.kind === 'busy';
  const issues = result.kind === 'error' ? result.issues : [];
  const issueFor = (field: string): string | undefined =>
    issues.find((entry) => entry.field === field)?.message;

  /** Any edit clears the previous refusal so a fixed field stops shouting. */
  function resetOnEdit() {
    if (result.kind === 'error') {
      setResult({ kind: 'idle' });
    }
  }

  async function submit() {
    if (busy) {
      return;
    }
    setResult({ kind: 'busy' });

    const payload: ProductUpdatePayload = {
      categoryId,
      title,
      slug,
      basePrice: basePrice === '' ? 0 : basePrice,
      discountPrice: discountPrice === '' ? null : discountPrice,
      descriptionRaw,
      fabricType,
      season,
      careInstructions: careInstructions.trim() === '' ? null : careInstructions,
      status,
    };

    let response;
    try {
      response = await updateProductAction({ productId: product.id, product: payload });
    } catch {
      setResult({
        kind: 'error',
        message: 'ذخیرهٔ تغییرات انجام نشد؛ ارتباط با سرور برقرار نشد. دوباره تلاش کنید.',
        issues: [],
      });
      return;
    }

    if (response.ok) {
      setResult({ kind: 'ok' });
      return;
    }
    setResult({
      kind: 'error',
      message: response.message,
      issues: response.issues ?? (response.field ? [{ field: response.field, message: response.message }] : []),
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title="ویرایش اطلاعات محصول"
          description="فیلدهای ستاره‌دار الزامی‌اند. قیمت‌ها به تومان و عدد صحیح ذخیره می‌شوند. ویرایش این فرم، تنوع‌ها، موجودی و تصویرها را تغییر نمی‌دهد."
        />

        {issues.length > 0 || result.kind === 'error' ? (
          <div className="mb-4">
            <Banner tone="danger" title="تغییرات ذخیره نشد">
              {result.kind === 'error' ? result.message : null}
            </Banner>
          </div>
        ) : null}
        {result.kind === 'ok' ? (
          <div className="mb-4">
            <Banner tone="success" title="تغییرات ذخیره شد">
              مقادیر جدید همین حالا در فهرست محصولات اعمال شده‌اند.
            </Banner>
          </div>
        ) : null}

        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <fieldset disabled={busy} className="grid gap-4 md:grid-cols-2">
            <Field label="عنوان محصول" htmlFor="edit-title" required error={issueFor('title')} errorId="edit-title-error">
              <input
                id="edit-title"
                className={inputClass}
                value={title}
                aria-invalid={issueFor('title') ? true : undefined}
                aria-describedby={issueFor('title') ? 'edit-title-error' : undefined}
                onChange={(event) => {
                  setTitle(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="نشانی محصول (slug)"
              htmlFor="edit-slug"
              required
              hint="حروف کوچک لاتین، عدد و خط تیره"
              error={issueFor('slug')}
              errorId="edit-slug-error"
            >
              <input
                id="edit-slug"
                className={inputClass}
                dir="ltr"
                value={slug}
                aria-invalid={issueFor('slug') ? true : undefined}
                aria-describedby={issueFor('slug') ? 'edit-slug-error' : undefined}
                onChange={(event) => {
                  setSlug(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="دسته"
              htmlFor="edit-category"
              required
              error={issueFor('categoryId')}
              errorId="edit-category-error"
            >
              <select
                id="edit-category"
                className={inputClass}
                value={categoryId}
                aria-invalid={issueFor('categoryId') ? true : undefined}
                aria-describedby={issueFor('categoryId') ? 'edit-category-error' : undefined}
                onChange={(event) => {
                  setCategoryId(event.target.value);
                  resetOnEdit();
                }}
              >
                {categories.length === 0 ? <option value="">دسته‌ای ثبت نشده است</option> : null}
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label="وضعیت انتشار"
              htmlFor="edit-status"
              required
              error={issueFor('status')}
              errorId="edit-status-error"
            >
              <select
                id="edit-status"
                className={inputClass}
                value={status}
                aria-invalid={issueFor('status') ? true : undefined}
                aria-describedby={issueFor('status') ? 'edit-status-error' : undefined}
                onChange={(event) => {
                  if (PRODUCT_STATUSES.includes(event.target.value as MerchantProductStatus)) {
                    setStatus(event.target.value as MerchantProductStatus);
                    resetOnEdit();
                  }
                }}
              >
                {PRODUCT_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {PRODUCT_STATUS_LABELS[value]} ({value})
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label="قیمت پایه (تومان)"
              htmlFor="edit-base-price"
              required
              error={issueFor('basePrice')}
              errorId="edit-base-price-error"
            >
              <input
                id="edit-base-price"
                type="number"
                min={0}
                step={1}
                className={inputClass}
                value={basePrice}
                aria-invalid={issueFor('basePrice') ? true : undefined}
                aria-describedby={issueFor('basePrice') ? 'edit-base-price-error' : undefined}
                onChange={(event) => {
                  setBasePrice(event.target.value === '' ? '' : Number(event.target.value));
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="قیمت تخفیف‌دار (تومان)"
              htmlFor="edit-discount-price"
              hint="اختیاری؛ نمی‌تواند از قیمت پایه بیشتر باشد"
              error={issueFor('discountPrice')}
              errorId="edit-discount-price-error"
            >
              <input
                id="edit-discount-price"
                type="number"
                min={0}
                step={1}
                className={inputClass}
                value={discountPrice}
                aria-invalid={issueFor('discountPrice') ? true : undefined}
                aria-describedby={issueFor('discountPrice') ? 'edit-discount-price-error' : undefined}
                onChange={(event) => {
                  setDiscountPrice(event.target.value === '' ? '' : Number(event.target.value));
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="نوع پارچه"
              htmlFor="edit-fabric"
              required
              error={issueFor('fabricType')}
              errorId="edit-fabric-error"
            >
              <input
                id="edit-fabric"
                className={inputClass}
                value={fabricType}
                aria-invalid={issueFor('fabricType') ? true : undefined}
                aria-describedby={issueFor('fabricType') ? 'edit-fabric-error' : undefined}
                onChange={(event) => {
                  setFabricType(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="فصل"
              htmlFor="edit-season"
              required
              error={issueFor('season')}
              errorId="edit-season-error"
            >
              <input
                id="edit-season"
                className={inputClass}
                value={season}
                aria-invalid={issueFor('season') ? true : undefined}
                aria-describedby={issueFor('season') ? 'edit-season-error' : undefined}
                onChange={(event) => {
                  setSeason(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="توضیح خام (ورودی موتور هوش مصنوعی)"
              htmlFor="edit-raw"
              required
              hint="اگر این متن تغییر کند، بدنهٔ HTML توضیح از نو ساخته می‌شود."
              error={issueFor('descriptionRaw')}
              errorId="edit-raw-error"
            >
              <textarea
                id="edit-raw"
                rows={4}
                className={inputClass}
                value={descriptionRaw}
                aria-invalid={issueFor('descriptionRaw') ? true : undefined}
                aria-describedby={issueFor('descriptionRaw') ? 'edit-raw-error' : undefined}
                onChange={(event) => {
                  setDescriptionRaw(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>

            <Field
              label="راهنمای نگهداری"
              htmlFor="edit-care"
              hint="اختیاری"
              error={issueFor('careInstructions')}
              errorId="edit-care-error"
            >
              <input
                id="edit-care"
                className={inputClass}
                value={careInstructions}
                aria-invalid={issueFor('careInstructions') ? true : undefined}
                aria-describedby={issueFor('careInstructions') ? 'edit-care-error' : undefined}
                onChange={(event) => {
                  setCareInstructions(event.target.value);
                  resetOnEdit();
                }}
              />
            </Field>
          </fieldset>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="submit" className={buttonClass.primary} disabled={busy}>
              {busy ? 'در حال ذخیره…' : 'ذخیرهٔ تغییرات'}
            </button>
            <Link className={buttonClass.neutral} href="/admin">
              بازگشت به فهرست
            </Link>
            <Link className={buttonClass.neutral} href={`/admin/products/${product.id}/images`}>
              تصویرهای محصول
            </Link>
            <Link className={buttonClass.neutral} href="/admin/inventory">
              موجودی و قیمت تنوع‌ها
            </Link>
          </div>
        </form>
      </Card>
    </div>
  );
}
