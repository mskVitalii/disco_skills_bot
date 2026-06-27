from tortoise import fields
from tortoise.models import Model


class User(Model):
    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True)
    username = fields.CharField(max_length=255, null=True)
    first_name = fields.CharField(max_length=255, default="")
    chat_id = fields.BigIntField()
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    skill_levels: fields.ReverseRelation["UserSkillLevel"]
    dialogs: fields.ReverseRelation["Dialog"]  # type: ignore[name-defined]

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return f"User({self.telegram_id}, @{self.username})"


class UserSkillLevel(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="skill_levels")
    skill_name = fields.CharField(max_length=100)
    level = fields.IntField(default=3)

    class Meta:
        table = "user_skill_levels"
        unique_together = [["user", "skill_name"]]

    def __str__(self) -> str:
        return f"{self.skill_name}={self.level}"
