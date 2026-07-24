import io
import json

import mplfinance as mpf
import yfinance as yf
from PIL import Image


def load_indices():
    with open("indices.json", "r") as f:
        return json.load(f)


def _jk_ticker(code):
    return code if code.endswith(".JK") else f"{code}.JK"


MAX_SCORE = 8


def fetch_ohlcv(tickers, period="6mo"):
    """Fetch OHLCV per ticker from Yahoo Finance. Skips tickers with no/short history."""
    data = {}
    for code in tickers:
        try:
            df = yf.Ticker(_jk_ticker(code)).history(period=period)
        except Exception:
            continue
        if df is None or df.empty or len(df) < 25:
            continue
        data[code] = df
    return data


def score_stock(df):
    """Lightweight Wyckoff-flavored pre-filter: volume vs average, position in
    recent range, and a simple spring pattern (low undercuts support, close
    reclaims it). This is a cheap quantitative shortlist step, not a real
    Wyckoff phase read — the AI strategy prompt does that on the shortlist."""
    window = df.iloc[-21:-1]
    if len(window) < 20:
        return None

    today = df.iloc[-1]
    avg_volume = window["Volume"].mean()
    range_low = window["Low"].min()
    range_high = window["High"].max()
    sma20 = window["Close"].mean()

    if avg_volume == 0 or range_high == range_low:
        return None

    vol_ratio = today["Volume"] / avg_volume
    price_position = (today["Close"] - range_low) / (range_high - range_low)
    spring = today["Low"] < range_low and today["Close"] > range_low

    score = 0
    signals = []
    if vol_ratio > 1.5:
        score += 2
        signals.append(f"Volume {vol_ratio:.1f}x the 20-day average")
    if price_position < 0.35:
        score += 2
        signals.append("Price in the lower area of the 20-day range (potential accumulation)")
    if today["Close"] > sma20:
        score += 1
        signals.append("Close above the 20-day average")
    if spring:
        score += 3
        signals.append("Spring pattern: low undercut support, then closed back above it")

    return {
        "score": score,
        "signals": signals,
        "vol_ratio": round(float(vol_ratio), 2),
        "price_position": round(float(price_position), 2),
        "last_close": round(float(today["Close"]), 2),
    }


def shortlist(data, top_n=8):
    scored = []
    for ticker, df in data.items():
        result = score_stock(df)
        if result is None or result["score"] <= 0:
            continue
        result["ticker"] = ticker
        scored.append(result)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def render_chart(df, ticker):
    plot_df = df.tail(60)
    buf = io.BytesIO()
    mpf.plot(
        plot_df,
        type="candle",
        volume=True,
        style="yahoo",
        title=ticker,
        savefig=dict(fname=buf, format="png", dpi=120),
    )
    buf.seek(0)
    return Image.open(buf)
