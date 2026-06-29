from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "telegram_id" BIGINT NOT NULL UNIQUE,
    "username" VARCHAR(255),
    "first_name" VARCHAR(255) NOT NULL DEFAULT '',
    "chat_id" BIGINT NOT NULL,
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "user_skill_levels" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "skill_name" VARCHAR(100) NOT NULL,
    "level" INT NOT NULL DEFAULT 3,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_user_skill__user_id_fd25e8" UNIQUE ("user_id", "skill_name")
);
CREATE TABLE IF NOT EXISTS "dialogs" (
    "id" UUID NOT NULL PRIMARY KEY,
    "title" VARCHAR(500),
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "dialog_nodes" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "user_message" TEXT NOT NULL,
    "skill_responses" JSONB NOT NULL,
    "response_options" JSONB NOT NULL,
    "telegram_message_id" BIGINT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "dialog_id" UUID NOT NULL REFERENCES "dialogs" ("id") ON DELETE CASCADE,
    "parent_id" INT REFERENCES "dialog_nodes" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztmulv4jgUwP8VlE8dia1ajrazWq3E1Rl2Wli1sDuaqopMYoJV4zCJ0xaN+N/Xdk7n4i"
    "jhWPEFwbNfbP/87HeQX8rU1CG2z4c2tJTfS78UAqaQfZHk5ZICZrNQygUUjLDo6LAeQgJG"
    "NrWARplwDLANmUiHtmahGUUmYVLiYMyFpsY6ImKEIoegnw5UqWlAOhETeXpmYkR0+A5t/+"
    "fsRR0jiHVpnkjnYwu5SuczIesSeis68tFGqmZiZ0rCzrM5nZgk6I0I5VIDEmgBCvnjqeXw"
    "6fPZecv0V+TONOziTjGio8MxcDCNLHdFBppJOD82G1ss0OCj/Fa5rF3XbqpXtRvWRcwkkF"
    "wv3OWFa3cVBYHeQFmIdkCB20NgDLlRiKFhgamaBrCJjEyGMcXlMH10B0Dzc6VSrV5XLqpX"
    "N/Xa9XX95iLAmmzK49vsfuGIWQeTmbx7EHzmIWN+NMT3BODWBFjpeKM6MbZsQSuw9cgFaP"
    "0uIdvwdG4J7hS8qxgSg064fdbrOeD+aTy0vjYezlivTzK+ntdUcdtkkmNk2VRdl6WstRHN"
    "hKWuglNRDhqmNgF07WMfUdrOkd+BXe7l0CNbZU4QvaZYatM0MQQkwzdF9WKIR0yxKMbBTb"
    "sR4zxc/f4dn/TUtn9il18MXm943+w8nF0K42WdEM1gqlmQr1oFNAm1zVoomsIMs5U0Y1h1"
    "T/Xc/3KgdszWoPcJnnu7lcN80L3vPA4a939L4NuNQYe3VIR0HpOeXcUuj+AhpX+7g68l/r"
    "P0o9/rCIKmTQ1LjBj2G/xQ+JyAQ02VmG8q0CMu3Jf6YBY8lBu/RIISLhgB7eUNWLoqtYQW"
    "YL8gjNm9+OqFn7GD5WnffnuAGAi+yd2ORLSP/Gl3/GGHueML34x9abjzIRIdAWwaH6TRFg"
    "85MgrcYMyKmWVCyaZpZRqXAAIMMWs+Nh8p3TwyUiLZgPKTIzVuu9tNlJ7EIOIGFeOI2T6f"
    "0qdi06cI6zUCUllrdwHpNuP7y4uLFUJS1iszJBVtsoPH/lFa0RKD/ruLRav7NkY5r0wN4D"
    "N5RTSOLHr/ELREqCEzTAK8NS2IDPINzgXHLpsRIFraaY3Vxw6PX5b3ZGILvAWuIGoabHls"
    "UdCNwluNx1aj3VEW2eFZkX7YC0xS/G8YsmT73UhsdDhlyeGw217DsToO0s+5TjEFNeWPsU"
    "M0zqAkRuIftT8/ULnIOY3CJVTdPCOaQYjVLalTIorX8rGBwlFWz+oredd6jnetJ73rqSRx"
    "KkmcShJKdkniFFydgqtDC65CmoTR2EqZp8d+HBfPQks9ESiZYaaPbFmoqQabdDjx5qmOs7"
    "yOIw7oFNo2M5EkwQF8z7vzI3rHUsvJc9Sd7wPJR/sx5dl94/snyU/f9Xtf/O6R2Kl112/G"
    "wiS34sW884zNI+0W++ux38srlkmqMcpDwlb/pCONlksY2fS5sD90w1xp5CBMEbHP+YAFpU"
    "ucSf5OxKHHwiD+gPhO+CBVU0x1ra1I0z3txeZ7EbxD490gm7+EIz9go/BzDynvXv6YP2Vs"
    "/9OMzYvA1iu5SUrbrLzt1YcvLbSF1GbAgiT9PaDMa0fSOa7LpqhUVw+q0R9Mdo/xn/hyLN"
    "2VDlV6wps0wa2xWzG93b0JropPOl6b1wu0CcI6e9IOSwaHw7TQikEDWkibKCnVAq+lnFcp"
    "AGGfU43gwG74ck6N4BVatndUVv0TKqJyLJWBHbx4zI/GGhC97scJsJDXZNiINNVjZqfuEZ"
    "V9ZeyFRbtby83XeCV1++5l8R9w1DM/"
)
