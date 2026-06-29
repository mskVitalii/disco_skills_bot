from tortoise import BaseDBAsyncClient

MODELS_STATE = (
    "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"
    "xf/fErIl"
)

async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "dialogs" ADD COLUMN IF NOT EXISTS "chat_id" BIGINT;
        CREATE INDEX IF NOT EXISTS "idx_dialogs_chat_id" ON "dialogs" ("chat_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_dialogs_chat_id";
        ALTER TABLE "dialogs" DROP COLUMN IF EXISTS "chat_id";
    """
