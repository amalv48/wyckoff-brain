-- Closes the plan-vs-actual loop: automated setups had a target/stop but
-- nothing ever checked whether price action afterward actually validated
-- the call. New columns track that resolution.
--
-- outcome defaults to 'open' so every existing row backfills cleanly.
-- Rollback: alter table automation_results drop column outcome,
--   drop column outcome_at, drop column outcome_price;
alter table automation_results
  add column if not exists outcome text not null default 'open',
  add column if not exists outcome_at timestamptz,
  add column if not exists outcome_price numeric;

alter table automation_results
  drop constraint if exists automation_results_outcome_check;
alter table automation_results
  add constraint automation_results_outcome_check
  check (outcome in ('open', 'target_hit', 'stop_hit'));
