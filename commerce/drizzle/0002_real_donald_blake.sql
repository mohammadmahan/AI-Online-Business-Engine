CREATE TYPE "commerce"."order_status_source" AS ENUM('STOREFRONT', 'MERCHANT_PANEL', 'PAYMENT_CALLBACK', 'SYSTEM');--> statement-breakpoint
CREATE TABLE "commerce"."order_status_history" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid NOT NULL,
	"from_status" "commerce"."order_status",
	"to_status" "commerce"."order_status" NOT NULL,
	"source" "commerce"."order_status_source" NOT NULL,
	"metadata" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "order_status_history_status_changes" CHECK ("commerce"."order_status_history"."from_status" is null or "commerce"."order_status_history"."from_status" <> "commerce"."order_status_history"."to_status"),
	CONSTRAINT "order_status_history_creation_has_no_origin" CHECK ("commerce"."order_status_history"."from_status" is not null or "commerce"."order_status_history"."to_status" = 'PENDING')
);
--> statement-breakpoint
ALTER TABLE "commerce"."order_status_history" ADD CONSTRAINT "order_status_history_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "commerce"."orders"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "order_status_history_order_id_idx" ON "commerce"."order_status_history" USING btree ("order_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "order_status_history_order_to_status_unique" ON "commerce"."order_status_history" USING btree ("order_id","to_status");