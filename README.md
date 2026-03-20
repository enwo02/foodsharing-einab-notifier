# Foodsharing EinAb Notifier

Watches the public Foodsharing Zürich “Einführungsabholungen” Google Sheet for newly available entries and notifies you on your phone via **Telegram**.

Notifications are sent when a row’s status contains `frei` (configurable via `NOTIFY_STATUS`).

## How it works

1. Polls the sheet as a CSV export.
2. Filters rows by status (default: `frei`).
3. Detects entries that were not previously seen (persisted in `state.json`).
4. Sends a Telegram message for each new entry.

## Telegram setup

1. Create a bot via Telegram: talk to `@BotFather` and run `/newbot`.
2. Copy:
   - `TELEGRAM_BOT_TOKEN` (from BotFather)
   - `TELEGRAM_CHAT_ID` (find it by messaging your bot and using any “get chat id” bot, or using a simple script you have online)

## Local run (quick test)

```bash
cd "/Users/eliowanner/Documents/programming/local_stuff/foodsharing_einab_notifier"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export DRY_RUN="true"

python3 notifier.py --dry-run
```

Note: the first run “bootstraps” (remembers existing `frei` rows) so you don’t get spammed immediately.

## GitHub Actions (recommended)

The included workflow runs every 5 minutes and persists `state.json` by committing back to the repo.

### Create the private repo + push (using `gh`)

From this folder:

```bash
cd "/Users/eliowanner/Documents/programming/local_stuff/foodsharing_einab_notifier"

git init -b main
git add .
git commit -m "chore: initial foodsharing notifier"

# Create a private repo, then push current folder.
# (Pick a repo name, e.g. foodsharing-einab-notifier)
gh repo create foodsharing-einab-notifier --private --confirm --source=. --push
```

Alternative: you can use the GitHub UI to create the repo, then use the remote+push commands above.

### Enable + configure Secrets

In your private GitHub repo, set these Secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Then enable the workflow.

### Manual run (debug)

In **Actions → Workflows → EinAb Poller → Run workflow**, you can override:
- `skip_existing` (set to `false` to immediately notify current `frei` entries for testing)
- `reset_state` (set to `true` if you already bootstrapped and want to re-notify current entries again)

## Configuration (env vars)

- `SHEET_ID` (default is the sheet from your link)
- `SHEET_GID` (default `917833898`)
- `NOTIFY_STATUS` (default `frei`; comma-separated list also works)
- `SKIP_EXISTING` (default `true`; first run bootstraps without notifications)

