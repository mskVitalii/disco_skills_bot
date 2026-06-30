from tortoise import fields
from tortoise.models import Model


class RawMessage(Model):
    id = fields.BigIntField(pk=True, generated=True)
    telegram_id = fields.BigIntField()
    chat_id = fields.BigIntField()
    username = fields.CharField(max_length=255, null=True)
    message_id = fields.BigIntField(null=True)
    message_type = fields.CharField(max_length=20)  # text, voice, video_note, business_text
    text = fields.TextField(null=True)
    business_connection_id = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "raw_messages"
        indexes = [["telegram_id"], ["chat_id"], ["created_at"]]
