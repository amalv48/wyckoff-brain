# Deploying PITA to Railway (recommended — simpler than Fly.io)

Mostly point-and-click through Railway's dashboard — no CLI install, no
`fly launch` prompts, no volume/secrets command syntax to remember. Can't be
run from the dev sandbox this repo was built in (its network policy blocks
Railway the same way it blocked Yahoo Finance and Fly.io), so do this from
your laptop or anywhere with normal internet access.

## 1. Create a Railway account and project

Go to [railway.app](https://railway.app), sign in with GitHub, click
**New Project → Deploy from GitHub repo**, and pick `plummer48/wyckoff-brain`.
If prompted for a branch, choose `claude/review-recommendations-lnukdf` (or
whatever branch this ends up merged into).

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

These are injected as environment variables at runtime — never baked into
the image or committed to the repo. The journal now lives in Supabase
(Postgres), not a local file, so no persistent volume is needed for it —
if you attached one earlier for `journal.json`, it's safe to leave or
remove, it's just unused now.

## 4. Deploy

If it didn't already deploy automatically after step 1, click **Deploy** in
the top right. Railway builds the Dockerfile and starts the container — the
app already listens on Railway's dynamically assigned `$PORT` (that's what
the `${PORT:-8000}` in the Dockerfile's CMD is for).

## 5. Get your URL

Service → **Settings → Networking → Generate Domain**. Gives you a public
`https://something.up.railway.app` URL.

## 6. Test the screener

Open the URL, go to the Screener tab, pick LQ45, run it. This is the one
thing that's never been tested outside a network-restricted sandbox — report
back what happens (success, or paste any error).

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
