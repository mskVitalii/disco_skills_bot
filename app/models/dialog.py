import uuid
from tortoise import fields
from tortoise.models import Model


class Dialog(Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user = fields.ForeignKeyField("models.User", related_name="dialogs")
    title = fields.CharField(max_length=500, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    nodes: fields.ReverseRelation["DialogNode"]

    class Meta:
        table = "dialogs"

    def __str__(self) -> str:
        return f"Dialog({self.id}, {self.title or 'untitled'})"


class DialogNode(Model):
    id = fields.IntField(pk=True, generated=True)
    dialog = fields.ForeignKeyField("models.Dialog", related_name="nodes")
    user_message = fields.TextField()
    # JSON list of SkillResponse dicts
    skill_responses = fields.JSONField(default=list)
    # JSON list of response option strings
    response_options = fields.JSONField(default=list)
    # Telegram message ID of the bot's response (for editing)
    telegram_message_id = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    parent = fields.ForeignKeyField(
        "models.DialogNode", related_name="children", null=True
    )

    class Meta:
        table = "dialog_nodes"
