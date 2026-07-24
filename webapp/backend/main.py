import base64
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

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

app = FastAPI(title="PITA — Wyckoff Tape Reader API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# --- Config endpoints ---

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
    top_n: int = 8
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

    data = screener.fetch_ohlcv(tickers)
    candidates = screener.shortlist(data, top_n=req.top_n)

    results = []
    for cand in candidates:
        ticker = cand["ticker"]
        df = data[ticker]
        chart_img = screener.render_chart(df, ticker)
        context_note = (
            f"Ini hasil screening otomatis untuk saham {ticker}. "
            f"Belum ada analisa manual sebelumnya. Sinyal kuantitatif yang "
            f"terdeteksi: {'; '.join(cand['signals'])}. "
            f"Harga close terakhir: {cand['last_close']}."
        )
        prompt = raw_prompt.format(last_analisa=context_note, equity=req.equity)
        try:
            analysis = providers.call_model(req.provider, req.model_id, prompt, image=chart_img)
        except Exception as e:
            analysis = f"Analisa gagal: {e}"

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
            }
        )

    return {"requested": len(tickers), "fetched": len(data), "candidates": results}


# --- Manual chart analysis ---

@app.post("/api/analyze")
async def analyze_manual(
    file: UploadFile = File(...),
    provider: str = Form(...),
    model_id: str = Form(...),
    prompt: str = Form(...),
    equity: float = Form(...),
    ticker: Optional[str] = Form(None),
):
    prompts = _load_json("prompts.json", {})
    if prompt not in prompts:
        raise HTTPException(400, f"Unknown prompt strategy: {prompt}")
    raw_prompt = prompts[prompt]

    img_bytes = await file.read()
    img = Image.open(io.BytesIO(img_bytes))

    entries = journal_store.load()
    last_entries = [e for e in entries if ticker and e.get("ticker") == ticker]
    last_analisa = last_entries[-1]["analysis"] if last_entries else "Tidak ada data sebelumnya."

    final_prompt = raw_prompt.format(last_analisa=last_analisa, equity=equity)

    try:
        analysis = providers.call_model(provider, model_id, final_prompt, image=img)
    except Exception as e:
        raise HTTPException(502, f"Analisa gagal: {e}")

    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": f"{provider}/{model_id}",
        "strategy": prompt,
        "ticker": ticker or None,
        "analysis": analysis,
    }
    entries = journal_store.append(entry)
    return {"analysis": analysis, "journal_index": len(entries) - 1}


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
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": req.model,
        "strategy": req.strategy,
        "ticker": req.ticker,
        "analysis": req.analysis,
    }
    entries = journal_store.append(entry)
    return {"journal_index": len(entries) - 1, "entry": entries[-1]}


class TradeUpdateRequest(BaseModel):
    status: str
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    qty: Optional[int] = None
    notes: str = ""


@app.patch("/api/journal/{index}")
def update_journal_trade(index: int, req: TradeUpdateRequest):
    try:
        return journal_store.update_trade(index, req.model_dump())
    except IndexError:
        raise HTTPException(404, "Journal entry not found")


# --- Static frontend ---
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
