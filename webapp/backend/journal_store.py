import os
from datetime import datetime
from zoneinfo import ZoneInfo

from supabase import create_client

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

EMPTY_TRADE = {
    "status": "Planned",
    "entry_price": None,
    "exit_price": None,
    "qty": None,
    "notes": "",
    "pnl": None,
}

_client = None


class SchemaNotReadyError(Exception):
    """Raised when a query needs the `archived` column and the Supabase
    schema migration (supabase/migrations/0002_add_archived_to_journal.sql)
    hasn't been applied yet."""


def _get_client():
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def _is_missing_archived_column(exc):
    message = str(exc)
    return "archived" in message and ("does not exist" in message or "42703" in message)


def _format_date(created_at):
    if not created_at:
        return ""
    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return dt.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_entry(row):
    return {
        "id": row["id"],
        "date": _format_date(row.get("created_at")),
        "model": row["model"],
        "strategy": row["strategy"],
        "ticker": row.get("ticker"),
        "analysis": row["analysis"],
        "trade": row.get("trade") or dict(EMPTY_TRADE),
        "archived": row.get("archived", False),
    }


def load(include_archived=False):
    client = _get_client()
    if not include_archived:
        try:
            res = client.table("journal").select("*").eq("archived", False).order("id").execute()
            return [_row_to_entry(r) for r in res.data]
        except Exception as e:
            if not _is_missing_archived_column(e):
                raise
            # Migration not applied yet — degrade to showing everything
            # rather than breaking the journal view.
    res = client.table("journal").select("*").order("id").execute()
    return [_row_to_entry(r) for r in res.data]


def append(entry):
    row = {
        "model": entry["model"],
        "strategy": entry["strategy"],
        "ticker": entry.get("ticker"),
        "analysis": entry["analysis"],
        "trade": entry.get("trade", dict(EMPTY_TRADE)),
    }
    res = _get_client().table("journal").insert(row).execute()
    return _row_to_entry(res.data[0])


def update_trade(entry_id, trade_fields):
    trade = dict(EMPTY_TRADE)
    trade.update(trade_fields)
    if (
        trade["status"] == "Closed"
        and trade.get("entry_price")
        and trade.get("exit_price")
        and trade.get("qty")
    ):
        trade["pnl"] = round((trade["exit_price"] - trade["entry_price"]) * trade["qty"], 2)
    else:
        trade["pnl"] = None

    res = _get_client().table("journal").update({"trade": trade}).eq("id", entry_id).execute()
    if not res.data:
        raise LookupError(f"journal entry {entry_id} not found")
    return _row_to_entry(res.data[0])


def archive(entry_id):
    """Soft-delete: mark the entry archived instead of removing the row, so
    trade history is preserved for later review."""
    try:
        res = _get_client().table("journal").update({"archived": True}).eq("id", entry_id).execute()
    except Exception as e:
        if _is_missing_archived_column(e):
            raise SchemaNotReadyError(
                "The 'archived' column isn't on the journal table yet — "
                "run supabase/migrations/0002_add_archived_to_journal.sql first."
            ) from e
        raise
    if not res.data:
        raise LookupError(f"journal entry {entry_id} not found")
    return _row_to_entry(res.data[0])
