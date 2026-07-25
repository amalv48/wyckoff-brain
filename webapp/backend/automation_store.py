import os
from datetime import datetime, timezone

from supabase import create_client

_client = None

# User-facing settings fields (what the frontend reads/writes). last_run_at
# is separate internal bookkeeping for hour-bucket dedup, never exposed.
DEFAULTS = {
    "enabled": False,
    "hours_wib": [],
    "index_name": "LQ45",
    "custom_tickers": [],
    "strategies": [],
    "provider": "Claude",
    "model_id": "claude-sonnet-5",
    "equity": 10000000,
    "top_n": 4,
}


class SchemaNotReadyError(Exception):
    """Raised when the automation_settings table doesn't exist yet — run
    supabase/migrations/0003_add_automation_settings.sql first."""


def _get_client():
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def _is_missing_table(exc):
    message = str(exc)
    return "automation_settings" in message and ("does not exist" in message or "42P01" in message)


def load():
    """Full current settings, including last_run_at. Returns defaults
    (enabled=False) if the table exists but is empty, or if the migration
    hasn't been applied yet — automation just stays inert rather than
    crashing the app."""
    try:
        res = _get_client().table("automation_settings").select("*").eq("id", 1).execute()
    except Exception as e:
        if _is_missing_table(e):
            raise SchemaNotReadyError(
                "The automation_settings table doesn't exist yet — run "
                "supabase/migrations/0003_add_automation_settings.sql first."
            ) from e
        raise
    if not res.data:
        return {**DEFAULTS, "last_run_at": None}
    row = res.data[0]
    return {**{k: row.get(k, v) for k, v in DEFAULTS.items()}, "last_run_at": row.get("last_run_at")}


def save(settings):
    """Upsert the user-facing fields only — never touches last_run_at."""
    payload = {k: settings[k] for k in DEFAULTS if k in settings}
    payload["id"] = 1
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        res = _get_client().table("automation_settings").upsert(payload).execute()
    except Exception as e:
        if _is_missing_table(e):
            raise SchemaNotReadyError(
                "The automation_settings table doesn't exist yet — run "
                "supabase/migrations/0003_add_automation_settings.sql first."
            ) from e
        raise
    row = res.data[0]
    return {k: row.get(k, v) for k, v in DEFAULTS.items()}


def mark_ticked():
    _get_client().table("automation_settings").update(
        {"last_run_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", 1).execute()
