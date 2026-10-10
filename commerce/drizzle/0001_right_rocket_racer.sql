CREATE TYPE "commerce"."discount_type" AS ENUM('PERCENT', 'FIXED');--> statement-breakpoint
CREATE TABLE "commerce"."coupons" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"code" varchar(64) NOT NULL,
	"discount_type" "commerce"."discount_type" NOT NULL,
	"discount_value" bigint NOT NULL,
	"min_spend" bigint DEFAULT 0 NOT NULL,
	"expires_at" timestamp with time zone,
	"usage_limit" integer,
	"used_count" integer DEFAULT 0 NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"description" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "coupons_code_unique" UNIQUE("code"),
	CONSTRAINT "coupons_discount_value_positive" CHECK ("commerce"."coupons"."discount_value" > 0),
	CONSTRAINT "coupons_percent_within_range" CHECK ("commerce"."coupons"."discount_type" <> 'PERCENT' or "commerce"."coupons"."discount_value" <= 100),
	CONSTRAINT "coupons_min_spend_non_negative" CHECK ("commerce"."coupons"."min_spend" >= 0),
	CONSTRAINT "coupons_usage_limit_positive" CHECK ("commerce"."coupons"."usage_limit" is null or "commerce"."coupons"."usage_limit" > 0),
	CONSTRAINT "coupons_used_count_non_negative" CHECK ("commerce"."coupons"."used_count" >= 0)
);
--> statement-breakpoint
CREATE INDEX "coupons_is_active_idx" ON "commerce"."coupons" USING btree ("is_active");--> statement-breakpoint
CREATE INDEX "coupons_expires_at_idx" ON "commerce"."coupons" USING btree ("expires_at");