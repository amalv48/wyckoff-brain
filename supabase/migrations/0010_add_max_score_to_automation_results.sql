-- Screener shows "score/max" (e.g. 9/14) so the number is legible on its
-- own — a bare score means nothing without knowing the strategy's max.
-- Different strategies have different max scores (score_stock=14,
-- Fibonacci=8, breakout=6), so this has to be captured per row, not
-- hardcoded client-side. Purely additive.
-- Rollback: alter table automation_results drop column max_score;
alter table automation_results
  add column if not exists max_score numeric;
