-- Dedup automated setups per (ticker, strategy, WIB trading day): the
-- scheduler polls every 5 minutes and can legitimately re-detect the same
-- setup across multiple hour-slots in one day (e.g. 12:00 and 16:00 WIB
-- both flag the same stock) — that should refresh one row, not pile up
-- near-duplicates. trade_date is a generated column so it stays in sync
-- with ticked_at automatically; the unique index lets the backend upsert
-- on (ticker, strategy, trade_date) instead of always inserting.
-- Purely additive/structural — no data loss. Rollback:
--   drop index if exists automation_results_ticker_strategy_day_idx;
--   alter table automation_results drop column trade_date;
-- Collapse any pre-existing same-day duplicates (rows inserted before this
-- migration existed) down to the latest one per (ticker, strategy, day)
-- before the unique index can be created.
delete from automation_results a
using automation_results b
where a.ticker = b.ticker
  and a.strategy = b.strategy
  and (a.ticked_at at time zone 'Asia/Jakarta')::date = (b.ticked_at at time zone 'Asia/Jakarta')::date
  and a.ticked_at < b.ticked_at;

alter table automation_results
  add column if not exists trade_date date
  generated always as ((ticked_at at time zone 'Asia/Jakarta')::date) stored;

create unique index if not exists automation_results_ticker_strategy_day_idx
  on automation_results (ticker, strategy, trade_date);
