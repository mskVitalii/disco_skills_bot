from tortoise import BaseDBAsyncClient


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
