-- LOCAL DEMO CATALOG — disposable harness only (127.0.0.1:55432).
--
-- What this is: a small Persian fashion catalog (3 categories, 3 published
-- products, 15 variants) so the merchant panel and the storefront can be read
-- on a freshly migrated local database. It is NOT a migration, NOT fixture data
-- for any test suite, and NOT for staging or production.
--
-- How it runs: `npm run db:seed` (scripts/seed-catalog.mjs) validates its target
-- BEFORE connecting, refuses anything that is not loopback:55432, and runs this
-- file inside the transaction opened below — any failing statement aborts it and
-- leaves the catalog exactly as it was.
--
-- INSERT-ONLY, by conflict target: category slug, product slug and variant sku.
-- A second run inserts nothing and rewrites no existing price, stock level,
-- description or category. It also does NOT restore demo values a checkout or an
-- edit has changed — `db:reset` + `db:seed` is the way back to the pristine catalog.
--
-- Money is integer Iranian Toman (D-010). Images are deliberately absent: media
-- storage is still the open G-5 decision, so the catalog carries no
-- product_images rows at all rather than dead URLs.
--
-- Revert with: npm run db:reset (drops schema commerce, re-applies 0000-0004).

begin;

insert into commerce.categories (name, slug, description) values
  ('مانتو', 'manto', 'مانتوهای روزمره و مجلسی'),
  ('شومیز', 'shomiz', 'شومیز و بلوز زنانه'),
  ('دامن', 'daman', 'دامنهای میدی و بلند')
on conflict (slug) do nothing;

insert into commerce.products
  (category_id, title, slug, base_price, discount_price, description_raw, description_html,
   fabric_type, season, care_instructions, status)
select c.id,
       'مانتو کتان جلو بسته',
       'manto-katan-jelo-baste',
       1850000, 1690000,
       'مانتو کتان با یقه گرد و دکمههای مخفی جلو. برش راحت و آستین بلند، مناسب استفادهٔ روزمره.',
       '<p>مانتو کتان با یقهٔ گرد و دکمه‌های مخفی جلو. برش راحت و آستین بلند، مناسب استفادهٔ روزمره.</p>',
       'کتان', 'بهار و تابستان', 'شستشوی ملایم با آب سرد؛ خشک‌کردن در سایه.', 'PUBLISHED'
from commerce.categories c where c.slug = 'manto'
on conflict (slug) do nothing;

insert into commerce.products
  (category_id, title, slug, base_price, discount_price, description_raw, description_html,
   fabric_type, season, care_instructions, status)
select c.id,
       'شومیز ابریشمی یقه گرد',
       'shomiz-abrishami-yaghe-gard',
       1240000, null,
       'شومیز ابریشمی با یقهٔ گرد و برش آزاد. پارچهٔ سبک با درخشش ملایم، مناسب مهمانی و محیط کار.',
       '<p>شومیز ابریشمی با یقهٔ گرد و برش آزاد. پارچهٔ سبک با درخشش ملایم، مناسب مهمانی و محیط کار.</p>',
       'ابریشم', 'چهارفصل', 'شستشوی دستی یا خشک‌شویی؛ اتوی ملایم از پشت پارچه.', 'PUBLISHED'
from commerce.categories c where c.slug = 'shomiz'
on conflict (slug) do nothing;

insert into commerce.products
  (category_id, title, slug, base_price, discount_price, description_raw, description_html,
   fabric_type, season, care_instructions, status)
select c.id,
       'دامن پلیسه میدی',
       'daman-plisse-midi',
       980000, 890000,
       'دامن پلیسهٔ میدی با کمر کشی. پلیسهٔ ریز و ایستا که پس از شستشو باز نمی‌شود.',
       '<p>دامن پلیسهٔ میدی با کمر کشی. پلیسهٔ ریز و ایستا که پس از شستشو باز نمی‌شود.</p>',
       'پلی‌استر', 'پاییز و زمستان', 'شستشوی ماشینی در برنامهٔ ملایم؛ نیاز به اتو ندارد.', 'PUBLISHED'
from commerce.categories c where c.slug = 'daman'
on conflict (slug) do nothing;

insert into commerce.product_variants (product_id, sku, color_name, color_hex, size, stock_quantity)
select p.id, v.sku, v.color_name, v.color_hex, v.size, v.stock
from commerce.products p
cross join (values
  ('MNT-KTN-BLK-S', 'مشکی', '#111111', 'S', 4),
  ('MNT-KTN-BLK-M', 'مشکی', '#111111', 'M', 7),
  ('MNT-KTN-BLK-L', 'مشکی', '#111111', 'L', 2),
  ('MNT-KTN-CRM-S', 'کرم',  '#E8DCC8', 'S', 3),
  ('MNT-KTN-CRM-M', 'کرم',  '#E8DCC8', 'M', 5),
  ('MNT-KTN-CRM-L', 'کرم',  '#E8DCC8', 'L', 0)
) as v(sku, color_name, color_hex, size, stock)
where p.slug = 'manto-katan-jelo-baste'
on conflict (sku) do nothing;

insert into commerce.product_variants (product_id, sku, color_name, color_hex, size, stock_quantity)
select p.id, v.sku, v.color_name, v.color_hex, v.size, v.stock
from commerce.products p
cross join (values
  ('SHM-ABR-WHT-S', 'سفید', '#FAFAFA', 'S', 6),
  ('SHM-ABR-WHT-M', 'سفید', '#FAFAFA', 'M', 4),
  ('SHM-ABR-WHT-L', 'سفید', '#FAFAFA', 'L', 1),
  ('SHM-ABR-BLU-M', 'آبی',  '#2F4F6F', 'M', 3),
  ('SHM-ABR-BLU-L', 'آبی',  '#2F4F6F', 'L', 2)
) as v(sku, color_name, color_hex, size, stock)
where p.slug = 'shomiz-abrishami-yaghe-gard'
on conflict (sku) do nothing;

insert into commerce.product_variants (product_id, sku, color_name, color_hex, size, stock_quantity)
select p.id, v.sku, v.color_name, v.color_hex, v.size, v.stock
from commerce.products p
cross join (values
  ('DMN-PLS-OLV-M', 'زیتونی', '#6B705C', 'M', 8),
  ('DMN-PLS-OLV-L', 'زیتونی', '#6B705C', 'L', 5),
  ('DMN-PLS-BLK-M', 'مشکی',   '#111111', 'M', 9),
  ('DMN-PLS-BLK-L', 'مشکی',   '#111111', 'L', 6)
) as v(sku, color_name, color_hex, size, stock)
where p.slug = 'daman-plisse-midi'
on conflict (sku) do nothing;

commit;
