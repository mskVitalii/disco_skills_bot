from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = False


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE EXTENSION IF NOT EXISTS vector;
        ALTER TABLE dialog_nodes ADD COLUMN IF NOT EXISTS embedding vector(1536);
        CREATE INDEX IF NOT EXISTS dialog_nodes_embedding_idx
            ON dialog_nodes USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS dialog_nodes_embedding_idx;
        ALTER TABLE dialog_nodes DROP COLUMN IF EXISTS embedding;
    """
