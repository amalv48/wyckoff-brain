# Deploying PITA to Railway (recommended — simpler than Fly.io)

Mostly point-and-click through Railway's dashboard — no CLI install, no
`fly launch` prompts, no volume/secrets command syntax to remember. Can't be
run from the dev sandbox this repo was built in (its network policy blocks
Railway the same way it blocked Yahoo Finance and Fly.io), so do this from
your laptop or anywhere with normal internet access.

## 1. Create a Railway account and project

Go to [railway.app](https://railway.app), sign in with GitHub, click
**New Project → Deploy from GitHub repo**, and pick `plummer48/wyckoff-brain`.
If prompted for a branch, choose `main` — that's the branch Railway watches
for auto-deploys.

## 2. Confirm it found the Dockerfile

Railway auto-detects the root `Dockerfile` and builds from it — no config
file needed. Under the service's **Settings → Build**, confirm it says
"Dockerfile" as the builder. If it instead tries to auto-detect a buildpack,
explicitly set the builder to **Dockerfile** in Settings.

## 3. Set your API keys and Supabase credentials

Service → **Variables** tab → add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Claude key |
| `GEMINI_API_KEY` | your Gemini key |
| `SUPABASE_URL` | your Supabase project's API URL (Project Settings → API) |
| `SUPABASE_SERVICE_ROLE_KEY` | the **service_role** secret key — not anon/publishable (same page, marked "secret") |
| `TELEGRAM_BOT_TOKEN` (optional) | for automation push notifications — see README for setup |
| `TELEGRAM_CHAT_ID` (optional) | for automation push notifications — see README for setup |
| `SLACK_WEBHOOK_URL` (optional) | for automation push notifications — see README for setup |

These are injected as environment variables at runtime — never baked into
the image or committed to the repo. The journal now lives in Supabase
(Postgres), not a local file, so no persistent volume is needed for it —
if you attached one earlier for `journal.json`, it's safe to leave or
remove, it's just unused now.

## 3b. Apply the database migrations

The Journal and Automation tabs need their tables to exist first. In the
Supabase dashboard → **SQL Editor**, run every file in
`supabase/migrations/` **in numeric order** (0002 through the highest
number in that folder). Each is additive and safe to re-run
(`if not exists` guards throughout) — see the README's migration table for
what each one adds. Skipping one doesn't crash the app; it just shows a
clear "run this migration" error on the affected feature until you catch up.

## 4. Deploy

If it didn't already deploy automatically after step 1, click **Deploy** in
the top right. Railway builds the Dockerfile and starts the container — the
app already listens on Railway's dynamically assigned `$PORT` (that's what
the `${PORT:-8000}` in the Dockerfile's CMD is for).

## 5. Get your URL

Service → **Settings → Networking → Generate Domain**. Gives you a public
`https://something.up.railway.app` URL.

## 6. Test the screener

Open the URL, go to the Screener tab, pick LQ45, run it — confirms Yahoo
Finance and your AI provider key both actually work from Railway's network
(this app's dev sandbox can't reach either, so this is the first real
end-to-end test). If you set up automation, also check the Automation tab
loads without a "Settings unavailable" error — that confirms Supabase is
wired up correctly too.

## Redeploying after code changes

Push to the branch Railway is watching — it redeploys automatically. No
manual redeploy command needed (unlike Fly's `fly deploy`).

## Cost

Railway bills usage-based after a small monthly credit. A single small
service like this, without a lot of traffic, should stay cheap — check
Railway's current pricing/credit terms before relying on it, since billing
details change.

## If this still feels like too much friction

`DEPLOY.md` in this repo has the Fly.io path (more manual, CLI-driven, but
gives more infra control if you want it). If both feel like too much
ceremony, the fallback is reverting to the original Streamlit app
(`app.py` at the repo root, already present and working) on Streamlit
Community Cloud — free, git-push-to-deploy, zero infra — at the cost of
losing the custom ticket-card/ledger design in favor of Streamlit's default
widgets. Say the word and I'll switch you over to that.
