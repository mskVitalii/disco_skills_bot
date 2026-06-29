from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> None:
    await db.execute_script("""
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
        );
    """)


async def downgrade(db: BaseDBAsyncClient) -> None:
    await db.execute_script("""
        DROP TABLE IF EXISTS "user_major_ideas";
        DROP TABLE IF EXISTS "skill_invocation_stats";
    """)
