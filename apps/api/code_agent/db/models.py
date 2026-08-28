from __future__ import annotations

from tortoise import fields
from tortoise.models import Model

from code_agent.config import settings


class Workspace(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=200)
    root_path = fields.CharField(max_length=2048)
    ignore_globs = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_opened_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "workspaces"


class Conversation(Model):
    id = fields.UUIDField(pk=True)
    workspace = fields.ForeignKeyField("models.Workspace", related_name="conversations")
    title = fields.CharField(max_length=300, default="New chat")
    mode = fields.CharField(max_length=20, default="agent")
    model_id = fields.CharField(max_length=64, null=True)
    active_run_id = fields.CharField(max_length=64, null=True)
    archived = fields.BooleanField(default=False)
    summary = fields.TextField(null=True)
    summary_covers_sort_key = fields.IntField(default=0)
    summary_updated_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "conversations"
        indexes = (("workspace_id", "updated_at"),)


class Message(Model):
    id = fields.UUIDField(pk=True)
    conversation = fields.ForeignKeyField("models.Conversation", related_name="messages")
    role = fields.CharField(max_length=20)
    blocks = fields.JSONField(default=list)
    run_id = fields.CharField(max_length=64, null=True)
    sort_key = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"
        indexes = (("conversation_id", "sort_key"),)


class Run(Model):
    id = fields.UUIDField(pk=True)
    conversation = fields.ForeignKeyField("models.Conversation", related_name="runs")
    status = fields.CharField(max_length=32, default="queued")
    mode = fields.CharField(max_length=20, default="agent")
    model_snapshot = fields.JSONField(default=dict)
    error_code = fields.CharField(max_length=80, null=True)
    error_message = fields.TextField(null=True)
    usage_json = fields.JSONField(default=dict)
    last_event_id = fields.CharField(max_length=64, null=True)
    last_seq = fields.IntField(default=0)
    graph_thread_id = fields.CharField(max_length=128, null=True)
    started_at = fields.DatetimeField(auto_now_add=True)
    ended_at = fields.DatetimeField(null=True)

    class Meta:
        table = "runs"
        indexes = (("status",),)


class RunEvent(Model):
    id = fields.UUIDField(pk=True)
    run = fields.ForeignKeyField("models.Run", related_name="events")
    event_id = fields.CharField(max_length=64, unique=True)
    seq = fields.IntField()
    type = fields.CharField(max_length=64)
    payload = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "run_events"
        indexes = (("run_id", "seq"),)


class LlmProvider(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=120)
    kind = fields.CharField(max_length=40, default="openai_compat")
    base_url = fields.CharField(max_length=500, default="https://api.openai.com/v1")
    api_key_encrypted = fields.TextField(default="")
    extra_headers = fields.JSONField(default=dict)
    enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "llm_providers"


class LlmModel(Model):
    id = fields.UUIDField(pk=True)
    provider = fields.ForeignKeyField("models.LlmProvider", related_name="models")
    model_id = fields.CharField(max_length=200)
    display_name = fields.CharField(max_length=200)
    context_window = fields.IntField(default=128000)
    supports_tools = fields.BooleanField(default=True)
    supports_vision = fields.BooleanField(default=False)
    is_default = fields.BooleanField(default=False)
    enabled = fields.BooleanField(default=True)
    capabilities_json = fields.JSONField(default=dict)
    params_json = fields.JSONField(default=dict)
    pricing_json = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "llm_models"


class SkillRecord(Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=64)
    source = fields.CharField(max_length=40)
    path = fields.CharField(max_length=2048)
    description = fields.CharField(max_length=1024, default="")
    enabled = fields.BooleanField(default=True)
    checksum = fields.CharField(max_length=64, default="")
    invalid_reason = fields.CharField(max_length=300, null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "skills"
        unique_together = (("name", "source"),)


class Setting(Model):
    key = fields.CharField(max_length=120, pk=True)
    value_json = fields.JSONField()

    class Meta:
        table = "settings"


class TerminalSession(Model):
    id = fields.UUIDField(pk=True)
    workspace = fields.ForeignKeyField("models.Workspace", related_name="terminals")
    title = fields.CharField(max_length=80, default="Terminal")
    cwd = fields.CharField(max_length=2048)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "terminals"


class PluginState(Model):
    id = fields.UUIDField(pk=True)
    plugin_id = fields.CharField(max_length=120, unique=True)
    enabled = fields.BooleanField(default=True)
    config_json = fields.JSONField(default=dict)

    class Meta:
        table = "plugin_states"


class WorkspaceMemory(Model):
    id = fields.UUIDField(pk=True)
    workspace = fields.ForeignKeyField("models.Workspace", related_name="memories")
    kind = fields.CharField(max_length=40)
    subject = fields.CharField(max_length=200)
    content = fields.JSONField(default=dict)
    tags = fields.JSONField(default=list)
    source = fields.JSONField(default=dict)
    confidence = fields.FloatField(default=1.0)
    superseded_by = fields.UUIDField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "workspace_memories"
        indexes = (("workspace_id", "kind"), ("workspace_id", "subject"))


TORTOISE_ORM = {
    "connections": {"default": settings.db_url},
    "apps": {
        "models": {
            "models": ["code_agent.db.models"],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}
