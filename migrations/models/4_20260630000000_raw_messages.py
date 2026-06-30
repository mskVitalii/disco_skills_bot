from tortoise import BaseDBAsyncClient


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
        CREATE INDEX IF NOT EXISTS "idx_raw_messages_created_at" ON "raw_messages" ("created_at");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "raw_messages";
    """
