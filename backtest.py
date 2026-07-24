"""Backtest the quant pre-filter (screener.score_stock) against forward returns.

Walks each trading day in a ticker's history, computes score_stock() using
only data available through that day's close, then measures forward
returns 5/10/20 trading days later. Reports mean/median forward return and
hit-rate (% positive), bucketed by score, so we can see whether days the
filter scores highly actually outperform days it scores low or zero.

Usage:
    python backtest.py --self-test                  # offline correctness checks, no network
    python backtest.py --index LQ45 --period 2y      # live run, needs yfinance/network access

The --self-test path needs no network and specifically checks for
lookahead bias: it confirms that mutating a ticker's data *after* day i
never changes the score computed for day i.
"""

import argparse

import numpy as np
import pandas as pd

import screener

HORIZONS = (5, 10, 20)


def _truncate_index_df(index_df, as_of_date):
    if index_df is None:
        return None
    truncated = index_df[index_df.index <= as_of_date]
    return truncated if len(truncated) else None


def walk_forward_scores(df, index_df=None, min_lookback=25, horizons=HORIZONS):
    """Replay score_stock() day-by-day over df's history. At day i, only
    df.iloc[:i+1] (and the correspondingly date-truncated index_df) is
    passed to score_stock — nothing beyond that day exists to the scorer,
    so there's no way for it to see the future.

    Returns a list of dicts: date, score, signals, and forward returns for
    each horizon (None where there isn't enough future data yet).
    """
    max_horizon = max(horizons)
    records = []
    for i in range(min_lookback, len(df)):
        as_of_date = df.index[i]
        window_df = df.iloc[: i + 1]
        window_index_df = _truncate_index_df(index_df, as_of_date)

        result = screener.score_stock(window_df, index_df=window_index_df)
        if result is None:
            continue

        today_close = df["Close"].iloc[i]
        record = {
            "date": as_of_date,
            "score": result["score"],
            "signals": result["signals"],
        }
        for h in horizons:
            future_i = i + h
            if future_i < len(df):
                record[f"fwd_{h}"] = df["Close"].iloc[future_i] / today_close - 1
            else:
                record[f"fwd_{h}"] = None
        records.append(record)
    return records


def run_backtest(tickers, period="2y"):
    data = screener.fetch_ohlcv(tickers, period=period)
    index_df = screener.fetch_index_reference(period=period)

    rows = []
    for ticker, df in data.items():
        for rec in walk_forward_scores(df, index_df=index_df):
            rec["ticker"] = ticker
            rows.append(rec)
    return pd.DataFrame(rows)


def summarize(results_df, horizons=HORIZONS):
    """Bucket by score (0 = filtered out entirely, then ranges) and report
    mean/median forward return + hit rate per bucket per horizon."""
    if results_df.empty:
        print("No results to summarize.")
        return

    bins = [-0.5, 0.5, 3.5, 6.5, 9.5, 99]
    labels = ["0 (no signal)", "1-3 (weak)", "4-6 (moderate)", "7-9 (strong)", "10+ (very strong)"]
    results_df = results_df.copy()
    results_df["bucket"] = pd.cut(results_df["score"], bins=bins, labels=labels)

    for h in horizons:
        col = f"fwd_{h}"
        sub = results_df.dropna(subset=[col])
        print(f"\n=== Forward return, {h} trading days ===")
        grouped = sub.groupby("bucket", observed=True)[col].agg(
            n="count", mean="mean", median="median", win_rate=lambda s: (s > 0).mean()
        )
        grouped["mean"] = (grouped["mean"] * 100).round(2)
        grouped["median"] = (grouped["median"] * 100).round(2)
        grouped["win_rate"] = (grouped["win_rate"] * 100).round(1)
        print(grouped.rename(columns={"mean": "mean %", "median": "median %", "win_rate": "win rate %"}))

    baseline = results_df[f"fwd_{HORIZONS[0]}"].mean()
    print(f"\nAll-days baseline mean {HORIZONS[0]}d return: {baseline * 100:.2f}%" if pd.notna(baseline) else "")


# --------------------------------------------------------------------------
# Offline self-test: no network, validates the walk-forward harness itself
# rather than the live data. Run with `python backtest.py --self-test`.
# --------------------------------------------------------------------------

def _make_synthetic_df(n=120, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    close = 1000 + np.cumsum(rng.normal(0, 8, size=n))
    close = np.maximum(close, 50)
    high = close + rng.uniform(1, 10, size=n)
    low = close - rng.uniform(1, 10, size=n)
    open_ = close + rng.normal(0, 3, size=n)
    volume = rng.uniform(1e6, 5e6, size=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates
    )


def self_test():
    df = _make_synthetic_df()
    index_df = _make_synthetic_df(seed=99)

    print("[1/3] Walk-forward runs without error on synthetic data...")
    records = walk_forward_scores(df, index_df=index_df)
    assert records, "expected at least one scored day"
    print(f"      OK — {len(records)} days scored")

    print("[2/3] Forward-return arithmetic matches a manual spot check...")
    sample = next(r for r in records if r["fwd_5"] is not None)
    i = df.index.get_loc(sample["date"])
    expected = df["Close"].iloc[i + 5] / df["Close"].iloc[i] - 1
    assert abs(sample["fwd_5"] - expected) < 1e-9, "forward return math mismatch"
    print("      OK")

    print("[3/3] No lookahead bias — mutating the future doesn't change past scores...")
    i = 60
    as_of_date = df.index[i]
    score_before = screener.score_stock(
        df.iloc[: i + 1], index_df=_truncate_index_df(index_df, as_of_date)
    )["score"]

    mutated = df.copy()
    mutated.iloc[i + 1 :, mutated.columns.get_indexer(["Close", "High", "Low", "Volume"])] *= 5.0
    score_after_mutation = screener.score_stock(
        mutated.iloc[: i + 1], index_df=_truncate_index_df(index_df, as_of_date)
    )["score"]
    assert score_before == score_after_mutation, (
        f"lookahead bias detected: score changed from {score_before} to "
        f"{score_after_mutation} after mutating only future rows"
    )

    all_records_before = walk_forward_scores(df, index_df=index_df)
    all_records_after = walk_forward_scores(mutated, index_df=index_df)
    for before, after in zip(all_records_before, all_records_after):
        if before["date"] <= df.index[i]:
            assert before["score"] == after["score"], (
                f"lookahead bias in walk_forward_scores at {before['date']}: "
                f"{before['score']} -> {after['score']}"
            )
    print("      OK — scores for day i are unaffected by data after day i")

    print("\nAll self-tests passed. The harness itself is sound; it still needs a")
    print("real run against LQ45/IDX30 history (network access to Yahoo Finance)")
    print("to produce an actual finding about the current scoring weights.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="Run offline correctness checks, no network.")
    parser.add_argument("--index", default="LQ45", help="Index name from indices.json, or 'Custom'.")
    parser.add_argument("--tickers", nargs="*", default=None, help="Explicit ticker list (with --index Custom).")
    parser.add_argument("--period", default="2y", help="yfinance period, e.g. 1y, 2y.")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    indices = screener.load_indices()
    tickers = args.tickers if args.index == "Custom" else indices.get(args.index, [])
    if not tickers:
        parser.error(f"No tickers found for index '{args.index}'")

    print(f"Fetching {len(tickers)} tickers, period={args.period}...")
    results_df = run_backtest(tickers, period=args.period)
    print(f"Scored {len(results_df)} ticker-days across {results_df['ticker'].nunique()} tickers.")
    summarize(results_df)


if __name__ == "__main__":
    main()
