-- Broaden dedup from (ticker, strategy, trade_date) to (ticker, strategy):
-- the previous per-day key let the same setup re-appear as a "new" row
-- every time it was re-detected on a later calendar day, which reads as
-- duplication once more than one day has passed. The correct semantics
-- are "keep the latest run" per (ticker, strategy) — regardless of which
-- day, which index it was screened from, or which provider/model produced
-- it. A different strategy for the same ticker is still a separate row.
--
-- trade_date is kept as a column (still harmless/free, generated from
-- ticked_at) but dropped from the uniqueness key.
-- Rollback: recreate the old index on (ticker, strategy, trade_date).

-- Collapse any existing same-ticker+strategy duplicates across different
-- days down to the single latest row before the new index can be created.
delete from automation_results a
using automation_results b
where a.ticker = b.ticker
  and a.strategy = b.strategy
  and a.ticked_at < b.ticked_at;

drop index if exists automation_results_ticker_strategy_day_idx;

create unique index if not exists automation_results_ticker_strategy_idx
  on automation_results (ticker, strategy);
