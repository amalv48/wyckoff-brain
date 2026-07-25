import base64
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import bleach
import markdown as md_lib
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

import journal_store
import providers
import screener

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Railway restarts the container on every deploy, so process start time is a
# reliable, human-readable stand-in for "when was this deployed" — Railway
# doesn't expose a deploy timestamp env var, only a commit SHA, which is
# harder to eyeball at a glance.
_STARTED_AT = datetime.now(journal_store.JAKARTA_TZ)

app = FastAPI(title="PITA — Wyckoff Tape Reader API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ALLOWED_MD_TAGS = [
    "p", "br", "hr", "strong", "b", "em", "i", "u",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "blockquote", "code", "pre", "span",
]

# Structured trading-plan fields requested alongside the Markdown narrative.
# Written in standard JSON Schema (nullable fields as a ["type", "null"]
# union) — providers.call_gemini() adapts this to Gemini's older dialect.
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["SETUP", "NO_SETUP"],
            "description": "SETUP if the strategy's rules produce a valid trade plan, otherwise NO_SETUP.",
        },
        "phase": {
            "type": "string",
            "description": "Short Wyckoff phase / structure label, e.g. 'Phase C - Spring'. Empty string if NO_SETUP.",
        },
        "entry_low": {"type": ["number", "null"], "description": "Lower bound of the entry price range."},
        "entry_high": {"type": ["number", "null"], "description": "Upper bound of the entry price range."},
        "stop_loss": {"type": ["number", "null"]},
        "target": {"type": ["number", "null"]},
        "rrr": {"type": ["number", "null"], "description": "Reward-to-risk ratio, e.g. 2.5 for 1:2.5."},
        "risk_pct": {"type": ["number", "null"], "description": "Position risk as a percent of equity, e.g. 1.5."},
        "action": {
            "anyOf": [
                {"type": "string", "enum": ["BUY", "HOLD", "SELL"]},
                {"type": "null"},
            ],
            "description": (
                "Recommended next action. Use null if verdict is NO_SETUP "
                "and no existing position is described (no recommendation "
                "to give). Use BUY if verdict is SETUP and no existing "
                "position is described. If an existing position IS "
                "described in the context, choose BUY (add to it) / HOLD "
                "(keep it unchanged) / SELL (exit some or all of it) based "
                "on this strategy's technical read of the position (has "
                "the stop been violated, has the target been reached, is "
                "the thesis still intact?) — not on the unrealized P/L "
                "alone, and independent of the verdict field, which only "
                "describes fresh-entry validity."
            ),
        },
        "narrative_markdown": {
            "type": "string",
            "description": (
                "Only the phase/structure analysis and reasoning, as short, "
                "concise, straightforward Markdown bullet points (not long "
                "paragraphs), in normal sentence case (no all-caps). Do NOT "
                "include a summary table, and do NOT restate the verdict, "
                "entry range, stop loss, target, RRR, or risk percentage "
                "here — those already appear in the fields above and are "
                "shown separately in the UI."
            ),
        },
    },
    "required": [
        "verdict", "phase", "entry_low", "entry_high", "stop_loss",
        "target", "rrr", "risk_pct", "action", "narrative_markdown",
    ],
    "additionalProperties": False,
}


def _fix_double_escaped_newlines(text):
    """Defensive cleanup: some models occasionally double-escape newlines
    inside a JSON string value (writing the literal two characters \\n
    instead of a real line break), which survives json.loads() as literal
    backslash-n text and renders as garbage. Collapse it back to real
    newlines if it slipped through."""
    if "\\n" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    return text


def call_structured(provider, model_id, prompt, image=None):
    """Call the model with ANALYSIS_SCHEMA and return (narrative_text, plan_dict).
    Falls back to a plain narrative-only call (plan=None) if structured output
    fails or the model returns something unparseable, so a schema hiccup never
    breaks the existing Markdown-only experience."""
    raw = providers.call_model(provider, model_id, prompt, image=image, response_schema=ANALYSIS_SCHEMA)
    try:
        parsed = json.loads(raw)
        narrative = _fix_double_escaped_newlines(parsed.get("narrative_markdown") or raw)
        plan = {k: parsed.get(k) for k in (
            "verdict", "phase", "entry_low", "entry_high",
            "stop_loss", "target", "rrr", "risk_pct", "action",
        )}
        return narrative, plan
    except (json.JSONDecodeError, AttributeError):
        return _fix_double_escaped_newlines(raw), None


def add_notional_pnl(plan, equity):
    """Every strategy prompt already defines risk_pct as the NET (post-fee)
    loss at the stop, as a percent of equity, and rrr as the NET reward:risk
    ratio — so the Rupiah amounts fall straight out of those two numbers,
    no extra AI round-trip or position-sizing math needed."""
    if plan is None:
        return plan
    risk_pct = plan.get("risk_pct")
    rrr = plan.get("rrr")
    loss_at_stop_rp = round(equity * risk_pct / 100, 2) if risk_pct is not None else None
    plan["loss_at_stop_rp"] = loss_at_stop_rp
    plan["profit_at_target_rp"] = (
        round(loss_at_stop_rp * rrr, 2) if loss_at_stop_rp is not None and rrr is not None else None
    )
    return plan


# Must match the fee percentages stated in every prompts.json strategy
# ("Buy fee 0.15 percent, sell fee 0.25 percent").
BUY_FEE_PCT = 0.0015
SELL_FEE_PCT = 0.0025
# IDX board lot size: 100 shares per lot, uniform across all listed stocks,
# in effect since 6 January 2014 (previously 500). No fractional-lot buying
# on the regular market.
IDX_SHARES_PER_LOT = 100


def add_lot_sizing(plan, equity):
    """How many lots to buy, sized from the risk budget already computed in
    add_notional_pnl (loss_at_stop_rp), using the worst-case entry price
    (entry_high, per every strategy's own 'use the upper bound' rule) and
    capped by what the equity can actually afford — risk-based sizing can
    otherwise imply spending more than the account has, e.g. a high-priced
    stock with a tight percentage stop."""
    if plan is None:
        return plan
    entry = plan.get("entry_high")
    stop = plan.get("stop_loss")
    loss_at_stop_rp = plan.get("loss_at_stop_rp")
    plan["lots"] = None
    plan["shares"] = None
    if entry is None or stop is None or loss_at_stop_rp is None or entry <= stop:
        return plan

    net_loss_per_share = entry * (1 + BUY_FEE_PCT) - stop * (1 - SELL_FEE_PCT)
    if net_loss_per_share <= 0:
        return plan

    lots_by_risk = loss_at_stop_rp / (net_loss_per_share * IDX_SHARES_PER_LOT)
    cost_per_lot = entry * (1 + BUY_FEE_PCT) * IDX_SHARES_PER_LOT
    lots_by_capital = equity / cost_per_lot if cost_per_lot > 0 else 0

    lots = int(min(lots_by_risk, lots_by_capital))
    plan["lots"] = lots
    plan["shares"] = lots * IDX_SHARES_PER_LOT
    return plan


def compute_position_pnl(lots, avg_price, current_price):
    """Unrealized P/L for a position the user already holds, net of the same
    buy/sell fees used everywhere else — computed in Python from a real
    fetched price, never left to the AI to estimate off a chart."""
    if not lots or not avg_price or current_price is None:
        return None
    shares = lots * IDX_SHARES_PER_LOT
    cost_basis = shares * avg_price * (1 + BUY_FEE_PCT)
    current_value = shares * current_price * (1 - SELL_FEE_PCT)
    pnl_rp = round(current_value - cost_basis, 2)
    return {
        "shares": shares,
        "cost_basis_rp": round(cost_basis, 2),
        "current_value_rp": round(current_value, 2),
        "pnl_rp": pnl_rp,
        "pnl_pct": round(pnl_rp / cost_basis * 100, 2) if cost_basis else None,
    }


def build_position_context(ticker, lots, avg_price, current_price, position_pnl):
    """Appended after the strategy prompt is formatted, only when a position
    is described — keeps position-awareness in one place instead of editing
    all 5 prompts.json strategies."""
    if not lots or not avg_price or position_pnl is None:
        return ""
    return (
        f"\n\nEXISTING POSITION CONTEXT:\n"
        f"The user currently holds {lots} lot ({position_pnl['shares']} shares) of "
        f"{ticker or 'this stock'} at an average price of {format_equity(avg_price)}. "
        f"Current price is {format_equity(current_price)}. Unrealized P/L, net of "
        f"buy/sell fees, is {format_equity(position_pnl['pnl_rp'])} ({position_pnl['pnl_pct']}%).\n\n"
        f"ADDITIONAL TASK: Recommend a next action for this existing position — "
        f"BUY, HOLD, or SELL — per the action field's rules, based on this "
        f"strategy's technical structure, not the unrealized P/L alone."
    )


def format_equity(value):
    """The prompts are in English but the equity is always Indonesian Rupiah —
    a bare number reads as USD to the model, so spell out the currency."""
    return f"Rp {value:,.0f}"


def render_markdown(text):
    """AI analysis text is Markdown; convert to sanitized HTML for display."""
    html = md_lib.markdown(text, extensions=["tables", "nl2br", "sane_lists"])
    return bleach.clean(html, tags=_ALLOWED_MD_TAGS, attributes={}, strip=True)


def _load_json(name, default):
    path = REPO_ROOT / name
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return default


def _img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


screener.warn_unmapped_strategies(_load_json("prompts.json", {}).keys())


# --- Config endpoints ---

@app.get("/api/version")
def get_version():
    """deployed_at is this process's start time — Railway restarts the
    container on every deploy, so it doubles as a human-readable deploy
    timestamp, easier to eyeball than a commit SHA. branch/environment are
    injected automatically by Railway (https://docs.railway.com/variables/reference)."""
    return {
        "deployed_at": _STARTED_AT.strftime("%Y-%m-%d %H:%M") + " WIB",
        "branch": os.environ.get("RAILWAY_GIT_BRANCH", ""),
        "environment": os.environ.get("RAILWAY_ENVIRONMENT_NAME", ""),
    }


@app.get("/api/models")
def get_models():
    return _load_json("models.json", {})


@app.get("/api/indices")
def get_indices():
    indices = screener.load_indices()
    names = [k for k in indices.keys() if not k.startswith("_")]
    return {"names": names, "tickers": {k: indices[k] for k in names}}


@app.get("/api/prompts")
def get_prompts():
    prompts = _load_json("prompts.json", {})
    return {"names": list(prompts.keys())}


# --- Screener ---

class ScreenRequest(BaseModel):
    index: str
    custom_tickers: Optional[list[str]] = None
    top_n: int = 4
    provider: str
    model_id: str
    prompt: str
    equity: float


@app.post("/api/screen")
def run_screen(req: ScreenRequest):
    indices = screener.load_indices()
    if req.index == "Custom":
        tickers = req.custom_tickers or []
    else:
        tickers = indices.get(req.index, [])
    if not tickers:
        raise HTTPException(400, "No tickers to screen")

    prompts = _load_json("prompts.json", {})
    if req.prompt not in prompts:
        raise HTTPException(400, f"Unknown prompt strategy: {req.prompt}")
    raw_prompt = prompts[req.prompt]
    scorer, max_score = screener.get_scorer(req.prompt)

    data = screener.fetch_ohlcv(tickers)
    index_df = screener.fetch_index_reference()
    candidates = screener.shortlist(data, top_n=req.top_n, index_df=index_df, scorer=scorer)

    results = []
    for cand in candidates:
        ticker = cand["ticker"]
        df = data[ticker]
        chart_img = screener.render_chart(df, ticker)
        context_note = (
            f"This is an automated screening result for {ticker}. "
            f"No prior manual analysis is available. Detected quantitative "
            f"signals: {'; '.join(cand['signals'])}. "
            f"Last close price: {cand['last_close']}."
        )
        prompt = raw_prompt.format(last_analisa=context_note, equity=format_equity(req.equity))
        plan = None
        try:
            analysis, plan = call_structured(req.provider, req.model_id, prompt, image=chart_img)
            plan = add_notional_pnl(plan, req.equity)
            plan = add_lot_sizing(plan, req.equity)
        except Exception as e:
            analysis = f"Analysis failed: {e}"

        results.append(
            {
                "ticker": ticker,
                "score": cand["score"],
                "signals": cand["signals"],
                "vol_ratio": cand["vol_ratio"],
                "price_position": cand["price_position"],
                "last_close": cand["last_close"],
                "chart_b64": _img_to_b64(chart_img),
                "analysis": analysis,
                "analysis_html": render_markdown(analysis),
                "plan": plan,
            }
        )

    return {
        "requested": len(tickers),
        "fetched": len(data),
        "max_score": max_score,
        "candidates": results,
    }


# --- Manual chart analysis ---

@app.post("/api/analyze")
async def analyze_manual(
    file: Optional[UploadFile] = File(None),
    provider: str = Form(...),
    model_id: str = Form(...),
    prompt: str = Form(...),
    equity: float = Form(...),
    ticker: Optional[str] = Form(None),
    lots: Optional[int] = Form(None),
    avg_price: Optional[float] = Form(None),
):
    prompts = _load_json("prompts.json", {})
    if prompt not in prompts:
        raise HTTPException(400, f"Unknown prompt strategy: {prompt}")
    raw_prompt = prompts[prompt]

    if not file and not ticker:
        raise HTTPException(400, "Provide either a chart file or a ticker")

    current_price = None
    if file is not None:
        img_bytes = await file.read()
        img = Image.open(io.BytesIO(img_bytes))
        if ticker:
            data = screener.fetch_ohlcv([ticker])
            if ticker in data:
                current_price = float(data[ticker]["Close"].iloc[-1])
    else:
        data = screener.fetch_ohlcv([ticker])
        if ticker not in data:
            raise HTTPException(400, f"Could not fetch data for ticker {ticker}")
        df = data[ticker]
        img = screener.render_chart(df, ticker)
        current_price = float(df["Close"].iloc[-1])

    if (lots or avg_price) and current_price is None:
        raise HTTPException(400, "A ticker is required to calculate P/L against your position")

    entries = journal_store.load()
    last_entries = [e for e in entries if ticker and e.get("ticker") == ticker]
    last_analisa = last_entries[-1]["analysis"] if last_entries else "No prior analysis available."

    position_pnl = compute_position_pnl(lots, avg_price, current_price)
    final_prompt = raw_prompt.format(last_analisa=last_analisa, equity=format_equity(equity))
    final_prompt += build_position_context(ticker, lots, avg_price, current_price, position_pnl)

    try:
        analysis, plan = call_structured(provider, model_id, final_prompt, image=img)
        plan = add_notional_pnl(plan, equity)
        plan = add_lot_sizing(plan, equity)
    except Exception as e:
        raise HTTPException(502, f"Analysis failed: {e}")

    entry = {
        "model": f"{provider}/{model_id}",
        "strategy": prompt,
        "ticker": ticker or None,
        "analysis": analysis,
    }
    saved = journal_store.append(entry)
    return {
        "analysis": analysis,
        "analysis_html": render_markdown(analysis),
        "journal_id": saved["id"],
        "plan": plan,
        "position_pnl": position_pnl,
    }


# --- Journal ---

@app.get("/api/journal")
def get_journal():
    return journal_store.load()


class JournalEntryRequest(BaseModel):
    ticker: Optional[str] = None
    model: str
    strategy: str
    analysis: str


@app.post("/api/journal")
def add_journal_entry(req: JournalEntryRequest):
    entry = {
        "model": req.model,
        "strategy": req.strategy,
        "ticker": req.ticker,
        "analysis": req.analysis,
    }
    saved = journal_store.append(entry)
    return {"journal_id": saved["id"], "entry": saved}


class TradeUpdateRequest(BaseModel):
    status: str
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    qty: Optional[int] = None
    notes: str = ""


@app.patch("/api/journal/{entry_id}")
def update_journal_trade(entry_id: int, req: TradeUpdateRequest):
    try:
        return journal_store.update_trade(entry_id, req.model_dump())
    except LookupError:
        raise HTTPException(404, "Journal entry not found")


@app.delete("/api/journal/{entry_id}")
def delete_journal_entry(entry_id: int):
    try:
        journal_store.archive(entry_id)
    except LookupError:
        raise HTTPException(404, "Journal entry not found")
    except journal_store.SchemaNotReadyError as e:
        raise HTTPException(503, str(e))
    return {"ok": True}


# --- Static frontend ---
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
