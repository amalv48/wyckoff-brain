import os
from datetime import datetime, timedelta, timezone

from supabase import create_client

_client = None

# User-facing settings fields (what the frontend reads/writes). last_run_at
# is separate internal bookkeeping for hour-bucket dedup, never exposed.
DEFAULTS = {
    "enabled": False,
    "hours_wib": [],
    "days_wib": [0, 1, 2, 3, 4],  # Monday-Friday
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


def _is_missing_days_column(exc):
    message = str(exc)
    return "days_wib" in message and ("does not exist" in message or "42703" in message)


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
        # Check the column-specific error before the generic table check —
        # a "column days_wib of relation automation_settings does not
        # exist" message contains both "automation_settings" and "does not
        # exist", so it would otherwise false-match _is_missing_table and
        # point the user at the wrong migration.
        if _is_missing_days_column(e):
            raise SchemaNotReadyError(
                "The days_wib column doesn't exist yet — run "
                "supabase/migrations/0005_add_days_to_automation_settings.sql first."
            ) from e
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


PLAN_FIELDS = [
    "phase", "entry_low", "entry_high", "stop_loss", "target", "rrr",
    "risk_pct", "action", "lots", "shares", "loss_at_stop_rp", "profit_at_target_rp",
]


def _is_missing_results_table(exc):
    message = str(exc)
    return "automation_results" in message and ("does not exist" in message or "42P01" in message)


def _is_missing_dedup_constraint(exc):
    # Raised by upsert(on_conflict=...) if migration 0006 (trade_date +
    # its unique index) hasn't been applied yet — same "not ready" case as
    # a missing table, just a different failure mode.
    message = str(exc)
    return "42P10" in message or "no unique or exclusion constraint" in message


RESULTS_RETENTION_DAYS = 60
JAKARTA_OFFSET = timedelta(hours=7)  # WIB, fixed offset, no DST


def save_results(index_name, results_by_strategy):
    """Persist every SETUP candidate from one tick so the app can show them
    later, independent of whether the push notification / its CCR session
    is ever opened. results_by_strategy is {strategy: [candidate, ...]},
    already filtered to SETUP-only by the caller. No-ops silently if the
    migration hasn't been applied yet — a missing results table should
    never break the tick itself.

    Upserts on (ticker, strategy, trade_date) rather than always inserting:
    the scheduler polls every few minutes and can legitimately re-detect
    the same setup across multiple hour-slots in one day, which would
    otherwise pile up near-duplicate rows for the same call. Each poll
    that still sees the setup just refreshes that one row (latest score/
    plan/narrative, latest ticked_at) instead of adding another."""
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for strategy, candidates in results_by_strategy.items():
        for cand in candidates:
            plan = cand.get("plan") or {}
            row = {
                "ticked_at": now,
                "strategy": strategy,
                "index_name": index_name,
                "ticker": cand["ticker"],
                "score": cand.get("score"),
                "last_close": cand.get("last_close"),
                "narrative_markdown": cand.get("analysis"),
                **{k: plan.get(k) for k in PLAN_FIELDS},
            }
            rows.append(row)
    if not rows:
        return
    try:
        _get_client().table("automation_results").upsert(
            rows, on_conflict="ticker,strategy,trade_date"
        ).execute()
        _prune_old_results()
    except Exception as e:
        if not (_is_missing_results_table(e) or _is_missing_dedup_constraint(e)):
            raise


def _prune_old_results():
    """Keep the table bounded — automated setups older than the retention
    window aren't useful as a 'recent setups' feed and would otherwise
    grow forever. Runs after every save; cheap no-op most days since
    there's rarely anything that old to delete."""
    cutoff = ((datetime.now(timezone.utc) + JAKARTA_OFFSET).date() - timedelta(days=RESULTS_RETENTION_DAYS)).isoformat()
    _get_client().table("automation_results").delete().lt("trade_date", cutoff).execute()


def load_recent_results(limit=20):
    """Most recent persisted SETUP results, newest first. Returns an empty
    list if the migration hasn't been applied yet."""
    try:
        res = (
            _get_client()
            .table("automation_results")
            .select("*")
            .order("ticked_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        if _is_missing_results_table(e):
            return []
        raise
    return res.data
