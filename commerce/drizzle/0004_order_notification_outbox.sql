CREATE TYPE "commerce"."notification_channel" AS ENUM('SMS');--> statement-breakpoint
CREATE TYPE "commerce"."notification_status" AS ENUM('PENDING', 'SENDING', 'SENT', 'FAILED');--> statement-breakpoint
CREATE TABLE "commerce"."notification_outbox" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid NOT NULL,
	"kind" varchar(64) NOT NULL,
	"channel" "commerce"."notification_channel" NOT NULL,
	"status" "commerce"."notification_status" DEFAULT 'PENDING' NOT NULL,
	"payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"attempts" integer DEFAULT 0 NOT NULL,
	"last_error" varchar(64),
	"provider_message_id" varchar(128),
	"next_attempt_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"sent_at" timestamp with time zone,
	CONSTRAINT "notification_outbox_attempts_non_negative" CHECK ("commerce"."notification_outbox"."attempts" >= 0),
	CONSTRAINT "notification_outbox_kind_known" CHECK ("commerce"."notification_outbox"."kind" = 'order.confirmed'),
	CONSTRAINT "notification_outbox_delivery_consistent" CHECK (("commerce"."notification_outbox"."status" = 'SENT') = ("commerce"."notification_outbox"."sent_at" is not null)),
	CONSTRAINT "notification_outbox_payload_is_object" CHECK (jsonb_typeof("commerce"."notification_outbox"."payload") = 'object')
);
--> statement-breakpoint
ALTER TABLE "commerce"."notification_outbox" ADD CONSTRAINT "notification_outbox_order_id_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "commerce"."orders"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "notification_outbox_unique" ON "commerce"."notification_outbox" USING btree ("order_id","kind","channel");--> statement-breakpoint
CREATE INDEX "notification_outbox_due_idx" ON "commerce"."notification_outbox" USING btree ("status","next_attempt_at");