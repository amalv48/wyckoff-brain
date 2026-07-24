-- Soft-delete support for journal entries: archived rows are hidden from the
-- default journal view but never physically deleted, so trade history stays
-- intact for later review.
alter table journal
  add column if not exists archived boolean not null default false;

create index if not exists journal_archived_idx on journal (archived);
