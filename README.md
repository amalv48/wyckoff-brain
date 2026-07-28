# PITA · IDX

Wyckoff-style tape reading for Indonesian (IDX) stocks — AI-assisted
screening, manual chart analysis, a trade journal, and hourly automated
screening with push notifications, all backed by Supabase.

**Live app:** the FastAPI + vanilla JS app in `webapp/` is the deployed
target (Railway). The root `app.py` is the original Streamlit prototype —
kept in the repo as a fallback, but not what's live.

## Features

- **Screener** — runs one of five AI strategies (`Wyckoff Standard`,
  `Wyckoff Aggressive`, `Fibonacci Specialist`,
  `Technical Fibonacci Wyckoff Master`, `Ryan Filbert Swing Method`) across
  LQ45 (45 tickers), IDX30 (30 tickers), or a custom ticker list. A cheap
  quantitative pre-filter shortlists candidates before the AI call, so you're
  not paying for a full AI read on every ticker.
- **Manual Analysis** — analyze one ticker (auto-fetched chart) or an
  uploaded chart screenshot, optionally with your existing position (lots +
  average price) for unrealized P/L and a next-action recommendation.
- **Journal** — manually tracked trades (entry/exit/qty/status/P&L). Nothing
  saves here automatically — every result screen (Screener, Manual, and
  Automation) has an explicit **+ Journal** button.
- **Automation** — configurable hours/days/index/strategies that run
  in-process on the deployed server (see [Automation details](#automation-details)
  below), with push notifications and a persisted, deduplicated results
  feed that tracks whether each setup's target or stop actually got hit.

## Architecture

```
webapp/backend/   FastAPI app (main.py) — serves the API and the static frontend
webapp/frontend/  vanilla JS/HTML/CSS, no build step
supabase/migrations/  SQL migrations, applied manually via the Supabase SQL editor
Dockerfile        single image, deployed on Railway (auto-deploys from `main`)
app.py            legacy Streamlit prototype (not deployed)
```

Data lives in Supabase (Postgres): `journal`, `automation_settings`,
`automation_results`. There is no authentication anywhere in the app — it's
a single-user personal tool (CORS is wide open). Don't put anything in it
you wouldn't want publicly reachable if the URL leaked.

## Requirements / environment variables

Set these on whatever platform you deploy to (Railway/Fly.io service
variables) or in `webapp/backend/.env` for local dev (see
`webapp/backend/.env.example`).

| Variable | Required? | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Required if using Claude | AI analysis |
| `GEMINI_API_KEY` | Required if using Gemini | AI analysis |
| `SUPABASE_URL` | Required | Journal + automation persistence |
| `SUPABASE_SERVICE_ROLE_KEY` | Required | **service_role** secret key, not anon/publishable — the tables have RLS enabled with no anon/authenticated policies |
| `TELEGRAM_BOT_TOKEN` | Optional | Automation push notifications via Telegram |
| `TELEGRAM_CHAT_ID` | Optional | Automation push notifications via Telegram |
| `SLACK_WEBHOOK_URL` | Optional | Automation push notifications via Slack (Incoming Webhook URL) |

Without Supabase credentials, the app runs but the Journal and Automation
tabs report "unavailable" instead of crashing — everything else (Screener,
Manual Analysis) works standalone. Without Telegram/Slack configured,
automation still runs and results still land in the Automation tab, just
without a push.

### Setting up Telegram notifications

1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts →
   copy the token it gives you.
2. Message your new bot anything (e.g. "hi") so it has a conversation open.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser — find
   `"chat":{"id":...}` in the response, that's your chat ID.
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

### Setting up Slack notifications

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New
   App** → **From scratch** → pick your workspace.
2. **Incoming Webhooks** → toggle on → **Add New Webhook to Workspace** →
   pick a channel.
3. Copy the webhook URL (`https://hooks.slack.com/services/...`) into
   `SLACK_WEBHOOK_URL`.

## Database setup

Apply every file in `supabase/migrations/` **in order**, via the Supabase
SQL editor (Project → SQL Editor → paste → run):

| Migration | Adds |
|---|---|
| `0002_add_archived_to_journal.sql` | Soft-delete support for journal entries |
| `0003_add_automation_settings.sql` | `automation_settings` table |
| `0004_add_automation_results.sql` | `automation_results` table |
| `0005_add_days_to_automation_settings.sql` | Day-of-week filtering |
| `0006_dedup_automation_results.sql` | `trade_date` generated column + an initial per-day dedup index (later replaced by 0009's per-ticker+strategy index — still needed as a step, `trade_date` itself is still used) |
| `0007_add_analysis_html_to_automation_results.sql` | Rendered bullet-point narrative |
| `0008_add_model_to_automation_results.sql` | Which provider/model produced each result |
| `0009_dedup_automation_results_by_ticker_strategy.sql` | Correct dedup key: one row per (ticker, strategy), not per day |
| `0010_add_max_score_to_automation_results.sql` | Score denominator (e.g. "9/14") |
| `0011_add_outcome_to_automation_results.sql` | Plan-vs-actual outcome tracking |

Each migration is additive and independently rollback-able (see the comment
at the top of each `.sql` file for the exact rollback statement). The app
degrades gracefully with a clear "run this migration" error if you're
missing one — it won't crash outright.

## Local development

```sh
cd webapp/backend
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`. The frontend is served as static files by the
same FastAPI app — no separate build/dev server needed.

## Deployment

- **[RAILWAY.md](RAILWAY.md)** — primary path, point-and-click, recommended.
- **[DEPLOY.md](DEPLOY.md)** — Fly.io alternative, more manual/CLI-driven,
  more infra control.

Both deploy the same `Dockerfile` from the repo root. Railway auto-deploys
on every push to `main`.

## Automation details

The automation feature does **not** rely on any external cron service — the
deployed FastAPI process polls itself every 5 minutes (`AUTOMATION_POLL_SECONDS`
in `main.py`) and only actually screens during your configured hour/day
slots, deduplicated per hour so it can't double-fire. (An earlier design
used an external scheduler; it was abandoned because that scheduler ran in
a network-restricted environment that could never reach the deployed app —
see the git history if you're curious.)

Each tick:
1. Checks enabled/day/hour/IDX-public-holiday, skips if not due.
2. Runs the configured strategies against the configured index.
3. Persists every `SETUP`-verdict candidate to `automation_results`
   (deduplicated per ticker+strategy — re-detecting the same setup, on any
   day, refreshes the existing row rather than adding a new one).
4. Sends exactly one push notification per strategy with results, if
   Telegram/Slack are configured.
5. Once a day, re-checks every still-open result's ticker against daily
   price bars since it was detected: target reached → win, stop reached →
   loss, neither → stays open. Resolved outcomes are never pruned; only
   unresolved "open" results are capped at the latest 10.

**Known limitations, disclosed rather than silently ignored:**
- IDX holiday awareness covers Indonesian *national public holidays* only
  (via the `holidays` Python package) — it does not know about IDX-specific
  "cuti bersama" (collective leave) non-trading days, which aren't public
  holidays and aren't in that dataset.
- Outcome resolution is a directional read (did the plan get validated by
  subsequent price action), not a full trade simulation — it doesn't model
  a specific entry fill, and if both target and stop fall within the same
  day's range, it conservatively assumes the stop was hit first.
- The self-polling scheduler assumes a single running instance. If this app
  is ever scaled to multiple replicas, each would poll independently and
  could race past the per-hour dedup check.
- No authentication anywhere — acceptable for a single-user personal tool,
  not for anything more.
