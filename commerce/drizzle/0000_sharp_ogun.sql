CREATE SCHEMA "commerce";
--> statement-breakpoint
CREATE TYPE "commerce"."order_status" AS ENUM('PENDING', 'PAID', 'PROCESSING', 'SHIPPED', 'CANCELLED');--> statement-breakpoint
CREATE TYPE "commerce"."product_status" AS ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED');--> statement-breakpoint
CREATE TABLE "commerce"."categories" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(255) NOT NULL,
	"slug" varchar(255) NOT NULL,
	"parent_id" uuid,
	"description" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "categories_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "commerce"."customers" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"phone_number" varchar(32) NOT NULL,
	"full_name" varchar(255) NOT NULL,
	"address" text NOT NULL,
	"postal_code" varchar(16) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "customers_phone_number_unique" UNIQUE("phone_number")
);
--> statement-breakpoint
CREATE TABLE "commerce"."order_items" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid NOT NULL,
	"variant_id" uuid NOT NULL,
	"quantity" integer NOT NULL,
	"unit_price" bigint NOT NULL,
	CONSTRAINT "order_items_quantity_positive" CHECK ("commerce"."order_items"."quantity" > 0),
	CONSTRAINT "order_items_unit_price_non_negative" CHECK ("commerce"."order_items"."unit_price" >= 0)
);
--> statement-breakpoint
CREATE TABLE "commerce"."orders" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"customer_id" uuid NOT NULL,
	"total_amount" bigint NOT NULL,
	"discount_amount" bigint DEFAULT 0 NOT NULL,
	"shipping_amount" bigint DEFAULT 0 NOT NULL,
	"status" "commerce"."order_status" DEFAULT 'PENDING' NOT NULL,
	"payment_ref_id" varchar(255),
	"shipping_address" text NOT NULL,
	"tracking_code" varchar(120),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "orders_total_amount_non_negative" CHECK ("commerce"."orders"."total_amount" >= 0),
	CONSTRAINT "orders_discount_amount_non_negative" CHECK ("commerce"."orders"."discount_amount" >= 0),
	CONSTRAINT "orders_shipping_amount_non_negative" CHECK ("commerce"."orders"."shipping_amount" >= 0)
);
--> statement-breakpoint
CREATE TABLE "commerce"."product_images" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"product_id" uuid NOT NULL,
	"variant_id" uuid,
	"storage_path" text NOT NULL,
	"public_url" text NOT NULL,
	"display_order" integer DEFAULT 0 NOT NULL,
	"is_primary" boolean DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE TABLE "commerce"."product_variants" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"product_id" uuid NOT NULL,
	"sku" varchar(120) NOT NULL,
	"color_name" varchar(120) NOT NULL,
	"color_hex" varchar(32) NOT NULL,
	"size" varchar(64) NOT NULL,
	"stock_quantity" integer DEFAULT 0 NOT NULL,
	"price_override" bigint,
	"is_active" boolean DEFAULT true NOT NULL,
	CONSTRAINT "product_variants_sku_unique" UNIQUE("sku"),
	CONSTRAINT "product_variants_stock_non_negative" CHECK ("commerce"."product_variants"."stock_quantity" >= 0),
	CONSTRAINT "product_variants_price_override_non_negative" CHECK ("commerce"."product_variants"."price_override" is null or "commerce"."product_variants"."price_override" >= 0)
);
--> statement-breakpoint
CREATE TABLE "commerce"."products" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"category_id" uuid NOT NULL,
	"title" varchar(500) NOT NULL,
	"slug" varchar(500) NOT NULL,
	"base_price" bigint NOT NULL,
	"discount_price" bigint,
	"description_raw" text NOT NULL,
	"description_html" text NOT NULL,
	"fabric_type" varchar(120) NOT NULL,
	"season" varchar(120) NOT NULL,
	"care_instructions" text,
	"status" "commerce"."product_status" DEFAULT 'DRAFT' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "products_slug_unique" UNIQUE("slug"),
	CONSTRAINT "products_base_price_non_negative" CHECK ("commerce"."products"."base_price" >= 0),
	CONSTRAINT "products_discount_price_non_negative" CHECK ("commerce"."products"."discount_price" is null or "commerce"."products"."discount_price" >= 0)
);
--> statement-breakpoint
ALTER TABLE "commerce"."categories" ADD CONSTRAINT "categories_parent_id_categories_id_fk" FOREIGN KEY ("parent_id") REFERENCES "commerce"."categories"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."order_items" ADD CONSTRAINT "order_items_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "commerce"."orders"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."order_items" ADD CONSTRAINT "order_items_variant_id_product_variants_id_fk" FOREIGN KEY ("variant_id") REFERENCES "commerce"."product_variants"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."orders" ADD CONSTRAINT "orders_customer_id_customers_id_fk" FOREIGN KEY ("customer_id") REFERENCES "commerce"."customers"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."product_images" ADD CONSTRAINT "product_images_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "commerce"."products"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."product_images" ADD CONSTRAINT "product_images_variant_id_product_variants_id_fk" FOREIGN KEY ("variant_id") REFERENCES "commerce"."product_variants"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."product_variants" ADD CONSTRAINT "product_variants_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "commerce"."products"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "commerce"."products" ADD CONSTRAINT "products_category_id_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "commerce"."categories"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "categories_parent_id_idx" ON "commerce"."categories" USING btree ("parent_id");--> statement-breakpoint
CREATE INDEX "customers_phone_number_idx" ON "commerce"."customers" USING btree ("phone_number");--> statement-breakpoint
CREATE INDEX "order_items_order_id_idx" ON "commerce"."order_items" USING btree ("order_id");--> statement-breakpoint
CREATE INDEX "order_items_variant_id_idx" ON "commerce"."order_items" USING btree ("variant_id");--> statement-breakpoint
CREATE INDEX "orders_customer_id_idx" ON "commerce"."orders" USING btree ("customer_id");--> statement-breakpoint
CREATE INDEX "orders_status_idx" ON "commerce"."orders" USING btree ("status");--> statement-breakpoint
CREATE INDEX "product_images_product_id_idx" ON "commerce"."product_images" USING btree ("product_id");--> statement-breakpoint
CREATE INDEX "product_images_variant_id_idx" ON "commerce"."product_images" USING btree ("variant_id");--> statement-breakpoint
CREATE INDEX "product_variants_product_id_idx" ON "commerce"."product_variants" USING btree ("product_id");--> statement-breakpoint
CREATE UNIQUE INDEX "product_variants_matrix_unique" ON "commerce"."product_variants" USING btree ("product_id","size","color_name");--> statement-breakpoint
CREATE INDEX "products_category_id_idx" ON "commerce"."products" USING btree ("category_id");--> statement-breakpoint
CREATE INDEX "products_status_idx" ON "commerce"."products" USING btree ("status");