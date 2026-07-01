from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "raw_messages" (
            "id" BIGSERIAL NOT NULL PRIMARY KEY,
            "telegram_id" BIGINT NOT NULL,
            "chat_id" BIGINT NOT NULL,
            "username" VARCHAR(255),
            "message_id" BIGINT,
            "message_type" VARCHAR(20) NOT NULL,
            "text" TEXT,
            "business_connection_id" VARCHAR(255),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_raw_messages_telegram_id" ON "raw_messages" ("telegram_id");
        CREATE INDEX IF NOT EXISTS "idx_raw_messages_chat_id" ON "raw_messages" ("chat_id");
        CREATE INDEX IF NOT EXISTS "idx_raw_messages_created_at" ON "raw_messages" ("created_at");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "raw_messages";"""


MODELS_STATE = (
    "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"
    "A2omKkA="
)
