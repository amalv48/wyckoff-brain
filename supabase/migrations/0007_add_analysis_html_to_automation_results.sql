-- Screener/Manual Analysis both render the AI's narrative as bullet-point
-- HTML (rendered server-side via render_markdown()) rather than raw
-- markdown text. automation_results only stored the raw markdown, so the
-- Automation tab showed it as an unformatted blob instead of bullets.
-- Purely additive. Rollback: alter table automation_results drop column analysis_html;
alter table automation_results
  add column if not exists analysis_html text;
