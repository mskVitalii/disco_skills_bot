from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = False

MODELS_STATE = (
    "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"
    "n/lHZw=="
)


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
