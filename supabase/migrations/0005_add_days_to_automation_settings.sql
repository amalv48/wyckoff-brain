-- Lets automation be restricted to specific weekdays, not just hour-slots.
-- 0=Monday .. 4=Friday (IDX doesn't trade weekends, so only these 5 are
-- offered in the UI). Default matches today's implicit behavior (every
-- weekday) so existing configs keep working unchanged once this is applied.
-- Purely additive. Rollback: alter table automation_settings drop column days_wib;
alter table automation_settings
  add column if not exists days_wib int[] not null default '{0,1,2,3,4}';
