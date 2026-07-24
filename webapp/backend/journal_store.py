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


def _get_client():
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


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
    }


def load():
    res = _get_client().table("journal").select("*").order("id").execute()
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
