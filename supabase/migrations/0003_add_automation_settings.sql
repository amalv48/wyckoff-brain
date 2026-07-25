-- Settings for the automated (scheduled) screening feature. Single-row
-- table (id is always 1) — this is a personal tool, one set of automation
-- settings, not per-user. Purely additive: does not touch the journal
-- table at all, so it can be dropped independently with zero impact on
-- journal data if this feature is ever unwanted.
create table if not exists automation_settings (
  id int primary key default 1,
  enabled boolean not null default false,
  hours_wib int[] not null default '{}',
  index_name text not null default 'LQ45',
  custom_tickers text[] not null default '{}',
  strategies text[] not null default '{}',
  provider text not null default 'Claude',
  model_id text not null default 'claude-sonnet-5',
  equity numeric not null default 10000000,
  top_n int not null default 4,
  last_run_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint automation_settings_single_row check (id = 1)
);

insert into automation_settings (id) values (1) on conflict (id) do nothing;
