# Foodsharing EinAb Notifier

Get a **Telegram** message when a new slot appears on the public [Foodsharing Zürich](https://foodsharing.network/region/zuerich) “Einführungsabholungen” (EinAb) Google Sheet—without checking the sheet yourself.

By default it notifies when a row’s **Status** contains `frei` (configurable).

---

## What you need

- A **Telegram** account
- A **GitHub** account (for the scheduled workflow)

---

## 1. Create a Telegram bot and get your chat ID

### Bot token

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the **HTTP API token** BotFather gives you. That value is your `TELEGRAM_BOT_TOKEN`.

### Chat ID

The bot must be allowed to message **you** (or a group you add it to). Your numeric ID is `TELEGRAM_CHAT_ID`.

**Easy approach:** message [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot) and copy your user ID.

**Alternative:** start a chat with **your** new bot, send any message, then open this URL in a browser (replace `YOUR_BOT_TOKEN`):

`https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates`

Look for `"chat":{"id": …}` and use that number (including a leading minus if it is a group).

---

## 2. Use this project on GitHub

### Fork or copy

- **Fork** this repository to your GitHub account, **or**
- Use “Use this template” / copy the files into a new repo.

### Add secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID (digits, or negative for a group) |

### Enable Actions

1. Open the **Actions** tab and enable workflows if GitHub asks.
2. The workflow **EinAb Poller** runs **every 5 minutes** and updates `state.json` in the repo when something changes (so each run knows what was already notified).

### First run (no spam)

On the **first** successful run after a fresh `state.json`, the script **records** existing `frei` rows and **does not** send messages. After that, **new** matching rows trigger Telegram notifications.

If you forked a copy that already had a populated `state.json`, replace it with the bootstrap version from this repo (empty `notified_keys`, `bootstrapped: false`) so your first run matches a clean setup.

---

## How it works

1. Downloads the sheet as CSV (public export URL).
2. Keeps rows whose status matches your `NOTIFY_STATUS` list.
3. Compares with hashes stored in `state.json` and notifies only on **new** rows.
4. Sends messages via the Telegram Bot API.

---

## Security and privacy

- **Never** commit real `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` values into the repo. Use **GitHub Actions secrets** only.
- The workflow needs **`contents: write`** so it can commit `state.json` (required for remembering state between runs).
- The default Google Sheet is **public**; this tool only reads its published CSV.

---

## License

This project is licensed under the [MIT License](LICENSE).
