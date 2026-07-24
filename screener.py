import io
import json

import mplfinance as mpf
import pandas as pd
import yfinance as yf
from PIL import Image


def load_indices():
    with open("indices.json", "r") as f:
        return json.load(f)


def _jk_ticker(code):
    return code if code.endswith(".JK") else f"{code}.JK"


MAX_SCORE = 14

IHSG_TICKER = "^JKSE"


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


def fetch_index_reference(period="6mo"):
    """Fetch IHSG (Jakarta Composite Index) history, used as a relative-strength
    benchmark. Returns None on failure so callers can degrade gracefully."""
    try:
        df = yf.Ticker(IHSG_TICKER).history(period=period)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def _rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _mfi(df, period=14):
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    raw_flow = typical_price * df["Volume"]
    direction = typical_price.diff()
    pos_flow = raw_flow.where(direction > 0, 0.0).rolling(period).sum()
    neg_flow = raw_flow.where(direction < 0, 0.0).rolling(period).sum()
    money_ratio = pos_flow / neg_flow
    return 100 - (100 / (1 + money_ratio))


def _ad_line(df):
    """Accumulation/Distribution line: a cumulative running total of buying vs.
    selling pressure inferred from where each day closes within its own
    high-low range, weighted by volume. Rising A/D while price is flat or
    falling is a classic 'quiet accumulation' divergence."""
    price_range = (df["High"] - df["Low"]).replace(0, float("nan"))
    money_flow_mult = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / price_range
    money_flow_mult = money_flow_mult.fillna(0)
    return (money_flow_mult * df["Volume"]).cumsum()


def score_stock(df, index_df=None):
    """Lightweight Wyckoff-flavored pre-filter, computed entirely from OHLCV
    data (no manual chart reading, no external data source beyond Yahoo
    Finance). This is a cheap quantitative shortlist step, not a real Wyckoff
    phase read — the AI strategy prompt does that on the shortlist.

    index_df (optional): IHSG history, used only for the relative-strength
    signal. Pass None to skip that signal (e.g. if the index fetch failed)."""
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

    rsi = _rsi(df["Close"]).iloc[-1]
    mfi = _mfi(df).iloc[-1]
    ad = _ad_line(df)

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
    if pd.notna(rsi) and rsi < 35:
        score += 1
        signals.append(f"RSI {rsi:.0f} (oversold)")
    if pd.notna(mfi) and mfi < 20:
        score += 2
        signals.append(f"MFI {mfi:.0f} (oversold on a volume-weighted basis)")
    if len(ad) >= 21:
        ad_change = ad.iloc[-1] - ad.iloc[-21]
        price_change = today["Close"] - df["Close"].iloc[-21]
        if ad_change > 0 and price_change <= 0:
            score += 2
            signals.append(
                "Bullish volume divergence: Accumulation/Distribution line rising while price is flat or down"
            )
    if index_df is not None and len(index_df) >= 21 and len(df) >= 21:
        stock_return = today["Close"] / df["Close"].iloc[-21] - 1
        index_return = index_df["Close"].iloc[-1] / index_df["Close"].iloc[-21] - 1
        if stock_return > index_return:
            score += 1
            signals.append("Outperforming the IHSG over the past 20 days")

    return {
        "score": score,
        "signals": signals,
        "vol_ratio": round(float(vol_ratio), 2),
        "price_position": round(float(price_position), 2),
        "last_close": round(float(today["Close"]), 2),
    }


def shortlist(data, top_n=8, index_df=None):
    scored = []
    for ticker, df in data.items():
        result = score_stock(df, index_df=index_df)
        if result is None or result["score"] <= 0:
            continue
        result["ticker"] = ticker
        scored.append(result)
    scored.sort(key=lambda x: (-x["score"], x["ticker"]))
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
