import io
import json
from pathlib import Path

import mplfinance as mpf
import pandas as pd
import yfinance as yf
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_indices():
    with open(REPO_ROOT / "indices.json", "r") as f:
        return json.load(f)


def _jk_ticker(code):
    return code if code.endswith(".JK") else f"{code}.JK"


MAX_SCORE = 14
FIBONACCI_MAX_SCORE = 8
BREAKOUT_MAX_SCORE = 6

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


def score_fibonacci_retracement(df, index_df=None):
    """Pre-filter for the Fibonacci Specialist strategy: looks for a pullback
    into the 61.8-78.6% retracement zone of a recent, structurally significant
    swing, with a same-day reversal proxy and volume confirmation. This is a
    single-swing read (highest point in the lookback with a valid prior low),
    not a full ZigZag/pivot analysis — good enough for a cheap pre-filter,
    the AI does the real structural read on the shortlist."""
    if len(df) < 40:
        return None

    lookback = df.iloc[-60:]
    high_idx = lookback["High"].idxmax()
    pos_of_high = lookback.index.get_loc(high_idx)
    if pos_of_high < 3 or pos_of_high >= len(lookback) - 3:
        return None

    swing_high = lookback.loc[high_idx, "High"]
    swing_low = lookback.iloc[:pos_of_high]["Low"].min()
    if pd.isna(swing_low) or swing_low <= 0:
        return None

    leg_size = (swing_high - swing_low) / swing_low
    if leg_size < 0.08:
        return None

    denom = swing_high - swing_low
    if denom <= 0:
        return None

    window = df.iloc[-21:-1]
    avg_volume = window["Volume"].mean()
    range_low = window["Low"].min()
    range_high = window["High"].max()
    if avg_volume == 0 or range_high == range_low:
        return None

    today = df.iloc[-1]
    retrace_ratio = (swing_high - today["Close"]) / denom
    vol_ratio = today["Volume"] / avg_volume
    price_position = (today["Close"] - range_low) / (range_high - range_low)

    today_range = today["High"] - today["Low"]
    close_pos_today = (today["Close"] - today["Low"]) / today_range if today_range else 0.5

    score = 0
    signals = []
    if 0.618 <= retrace_ratio <= 0.786:
        score += 4
        signals.append(
            f"Price sits in the 61.8-78.6% Fibonacci retracement zone of the recent swing ({retrace_ratio:.0%} retraced)"
        )
    elif 0.5 <= retrace_ratio < 0.618 or 0.786 < retrace_ratio <= 0.886:
        score += 2
        signals.append(f"Price is near the golden Fibonacci zone ({retrace_ratio:.0%} retraced)")

    if close_pos_today > 0.5:
        score += 2
        signals.append("Closed in the upper half of today's range (possible reversal confirmation)")

    if vol_ratio > 1.3:
        score += 2
        signals.append(f"Volume {vol_ratio:.1f}x the 20-day average on the reversal day")

    return {
        "score": score,
        "signals": signals,
        "vol_ratio": round(float(vol_ratio), 2),
        "price_position": round(float(price_position), 2),
        "last_close": round(float(today["Close"]), 2),
    }


def score_breakout_swing(df, index_df=None):
    """Pre-filter for the Ryan Filbert Swing Method strategy: moving-average
    trend alignment plus exactly one of his three canonical entry types
    (buy on breakout / support / reversal), checked in priority order since
    his framework treats them as one applicable classification, not
    stackable signals."""
    window = df.iloc[-21:-1]
    if len(window) < 20:
        return None
    avg_volume = window["Volume"].mean()
    range_low = window["Low"].min()
    range_high = window["High"].max()
    if avg_volume == 0 or range_high == range_low:
        return None

    today = df.iloc[-1]
    vol_ratio = today["Volume"] / avg_volume
    price_position = (today["Close"] - range_low) / (range_high - range_low)

    sma_short = df["Close"].iloc[-6:-1].mean() if len(df) >= 6 else None
    sma_medium = window["Close"].mean()
    sma_long = df["Close"].iloc[-51:-1].mean() if len(df) >= 51 else None

    score = 0
    signals = []

    if sma_short is not None and sma_long is not None and sma_short > sma_medium > sma_long:
        score += 2
        signals.append("Moving averages aligned in an uptrend (short > medium > long)")

    today_range = today["High"] - today["Low"]
    close_pos_today = (today["Close"] - today["Low"]) / today_range if today_range else 0.5

    breakout = False
    if len(df) >= 61:
        prior_high = df["High"].iloc[-61:-1].max()
        breakout = today["Close"] > prior_high and vol_ratio > 1.5

    support_bounce = (
        sma_medium > 0
        and abs(today["Close"] - sma_medium) / sma_medium < 0.025
        and sma_long is not None
        and sma_medium > sma_long
    )

    reversal = False
    if len(df) >= 11:
        recent_low10 = df["Low"].iloc[-11:-1].min()
        reversal = today["Low"] <= recent_low10 and close_pos_today > 0.5 and vol_ratio > 1.2

    if breakout:
        score += 4
        signals.append(f"Buy on Breakout: closed above the prior 60-day high on {vol_ratio:.1f}x volume")
    elif support_bounce:
        score += 3
        signals.append("Buy on Support: pullback to the 20-day moving average within an uptrend")
    elif reversal:
        score += 3
        signals.append(f"Buy on Reversal: bounced off a fresh 10-day low with volume ({vol_ratio:.1f}x average)")

    return {
        "score": score,
        "signals": signals,
        "vol_ratio": round(float(vol_ratio), 2),
        "price_position": round(float(price_position), 2),
        "last_close": round(float(today["Close"]), 2),
    }


STRATEGY_SCORERS = {
    "Wyckoff Standard": (score_stock, MAX_SCORE),
    "Wyckoff Aggressive": (score_stock, MAX_SCORE),
    "Technical Fibonacci Wyckoff Master": (score_stock, MAX_SCORE),
    "Fibonacci Specialist": (score_fibonacci_retracement, FIBONACCI_MAX_SCORE),
    "Ryan Filbert Swing Method": (score_breakout_swing, BREAKOUT_MAX_SCORE),
}


def get_scorer(strategy_name):
    return STRATEGY_SCORERS.get(strategy_name, (score_stock, MAX_SCORE))


def warn_unmapped_strategies(prompt_names):
    """A new strategy added to prompts.json without a matching entry here
    degrades gracefully (falls back to the generic Wyckoff filter via
    get_scorer), but a silent rename/typo of an *existing* mapped strategy
    would too — this makes that visible in the logs instead of silent."""
    missing = set(prompt_names) - set(STRATEGY_SCORERS)
    if missing:
        print(
            f"WARNING: strategies {sorted(missing)} have no dedicated scorer; "
            f"falling back to the generic Wyckoff filter for them."
        )


def shortlist(data, top_n=8, index_df=None, scorer=score_stock):
    scored = []
    for ticker, df in data.items():
        result = scorer(df, index_df=index_df)
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
