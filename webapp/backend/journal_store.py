import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JOURNAL_PATH = REPO_ROOT / "journal.json"

EMPTY_TRADE = {
    "status": "Planned",
    "entry_price": None,
    "exit_price": None,
    "qty": None,
    "notes": "",
    "pnl": None,
}


def load():
    if JOURNAL_PATH.exists():
        with open(JOURNAL_PATH, "r") as f:
            return json.load(f)
    return []


def save(entries):
    with open(JOURNAL_PATH, "w") as f:
        json.dump(entries, f, indent=4)


def append(entry):
    entries = load()
    entry.setdefault("trade", dict(EMPTY_TRADE))
    entries.append(entry)
    save(entries)
    return entries


def update_trade(index, trade_fields):
    entries = load()
    if index < 0 or index >= len(entries):
        raise IndexError("journal entry index out of range")
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
    entries[index]["trade"] = trade
    save(entries)
    return entries[index]
