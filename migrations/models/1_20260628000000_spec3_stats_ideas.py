from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "skill_invocation_stats" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "skill_name" VARCHAR(100) NOT NULL,
            "count" INT NOT NULL DEFAULT 0,
            "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_skill_invo_user_id_skill_name" UNIQUE ("user_id", "skill_name")
        );

        CREATE TABLE IF NOT EXISTS "user_major_ideas" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "idea" TEXT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
        );"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "user_major_ideas";
        DROP TABLE IF EXISTS "skill_invocation_stats";"""


MODELS_STATE = (
    "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"
    "qS7jLHbd0h/+l/+x9HZw=="
)
