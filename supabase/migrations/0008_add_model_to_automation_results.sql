-- Needed to let a saved automation result be added to the journal (which
-- records which model produced an analysis) — automation_results never
-- captured provider/model_id even though automation_settings knows both
-- at tick time. Purely additive.
-- Rollback: alter table automation_results drop column provider, drop column model_id;
alter table automation_results
  add column if not exists provider text,
  add column if not exists model_id text;
