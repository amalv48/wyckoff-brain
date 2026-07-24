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

## 3. Set your API keys

Service → **Variables** tab → add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Claude key |
| `GEMINI_API_KEY` | your Gemini key |
| `JOURNAL_FILE` | `/data/journal.json` |

These are injected as environment variables at runtime — never baked into
the image or committed to the repo.

## 4. Attach a persistent volume

Without this, `journal.json` resets every redeploy — same reasoning as the
Fly.io setup.

Service → **Settings → Volumes → New Volume**. Mount path: `/data`. 1GB is
plenty for a JSON journal file.

## 5. Deploy

If it didn't already deploy automatically after step 1, click **Deploy** in
the top right. Railway builds the Dockerfile and starts the container — the
app already listens on Railway's dynamically assigned `$PORT` (that's what
the `${PORT:-8000}` in the Dockerfile's CMD is for).

## 6. Get your URL

Service → **Settings → Networking → Generate Domain**. Gives you a public
`https://something.up.railway.app` URL.

## 7. Test the screener

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
