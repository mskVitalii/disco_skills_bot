from tortoise import fields
from tortoise.models import Model


class SkillInvocationStat(Model):
    """Tracks how often each skill is invoked per user."""
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="skill_stats")
    skill_name = fields.CharField(max_length=100)
    count = fields.IntField(default=0)

    class Meta:
        table = "skill_invocation_stats"
        unique_together = [["user", "skill_name"]]

    def __str__(self) -> str:
        return f"{self.skill_name}={self.count}"


class UserMajorIdea(Model):
    """Stores major thematic ideas extracted from user's conversations."""
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="major_ideas")
    idea = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_major_ideas"

    def __str__(self) -> str:
        return f"Idea({self.idea[:50]})"
