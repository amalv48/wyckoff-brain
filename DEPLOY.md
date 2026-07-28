# Deploying PITA to Fly.io

This can't be run from inside this dev sandbox (its network policy blocks
`fly.io` outright, same as it blocked Yahoo Finance). Run these from your own
machine.

## 1. Install the Fly CLI

```sh
curl -L https://fly.io/install.sh | sh
```

(or `brew install flyctl` on macOS)

## 2. Log in

```sh
fly auth login
```

Opens a browser. Sign up if you don't have an account — Fly asks for a card
even on the free allowance, but a single small always-off-when-idle app like
this should cost close to nothing (see Cost below).

## 3. Launch the app (don't deploy yet)

From the repo root, where `fly.toml` and `Dockerfile` already live:

```sh
fly launch --no-deploy
```

It will detect the existing `fly.toml`/`Dockerfile` and ask to confirm. The
app name `pita-idx` in `fly.toml` is almost certainly taken — when it asks,
pick a different name (or edit the `app = "..."` line in `fly.toml` yourself
first). Region `sin` (Singapore) is already set — closest to Indonesia.

You do **not** need Docker installed locally — `fly deploy` builds the image
on Fly's remote builders by default.

## 4. Set your API keys and Supabase credentials as secrets

The journal lives in Supabase (Postgres), not a local file, so no
persistent volume is needed — just secrets:

```sh
fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-..." \
  GEMINI_API_KEY="..." \
  SUPABASE_URL="https://<project-ref>.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="..."
```

Use the **service_role** secret key from Supabase (Project Settings → API),
not the anon/publishable one — every table's RLS has no anon/authenticated
policies, so only service_role can read or write them. These become
environment variables inside the container — never baked into the image or
committed to the repo.

Optionally, also set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` and/or
`SLACK_WEBHOOK_URL` for automation push notifications — see the README for
how to obtain each.

## 4b. Apply the database migrations

Before the Journal/Automation tabs will work, run every file in
`supabase/migrations/` **in numeric order** via the Supabase dashboard's SQL
Editor — see the README's migration table for what each one adds. The app
degrades gracefully (clear error, no crash) if you're missing one.

## 5. Deploy

```sh
fly deploy
```

## 6. Open it

```sh
fly open
```

## Verifying after deploy

The one thing I couldn't test from this sandbox: the screener's Yahoo
Finance fetch. Once deployed, open the Screener tab, pick LQ45, and run a
screening — Fly's network isn't restricted the way this dev sandbox's is, so
it should work, but confirm it end-to-end.

## Cost

- The VM (`shared-cpu-1x`, 512MB) is configured with `auto_stop_machines`/
  `min_machines_running = 0` — it scales to zero and stops billing compute
  when nobody's using it, waking on the next request (a few seconds' cold
  start).
- Supabase's free tier covers a small journal table with no extra cost.
- Check Fly's and Supabase's current pricing pages before deploying if this
  matters to you — rates change.

## Redeploying after code changes

```sh
git pull
fly deploy
```
