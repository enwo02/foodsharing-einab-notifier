import argparse
import csv
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


SHEET_EXPORT_URL_TMPL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _norm(s: Any) -> str:
    if s is None:
        return ""
    return " ".join(str(s).replace("\u200b", "").split()).strip()


def _norm_key_part(s: Any) -> str:
    # Lowercase + normalized whitespace for stable matching.
    return _norm(s).lower()


def _sha1_key(parts: List[str]) -> str:
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Entry:
    key: str
    category: str
    fairshare: str
    date: str
    time: str
    status: str
    instructor: str
    contact_link: str
    comment: str

    def telegram_text(self) -> str:
        lines = [
            "Neue EinAb verfügbar (Foodsharing Zürich)",
            "",
            f"Kategorie: {self.category}",
            f"Fairteiler-Besuch: {self.fairshare}",
            f"Datum/Uhrzeit: {self.date} {self.time}".strip(),
            f"Status: {self.status}",
            f"EinAb-Geber*in: {self.instructor}",
        ]
        if self.comment:
            lines.append(f"Notiz: {self.comment}")
        if self.contact_link:
            lines.append("")
            lines.append(f"Kontakt: {self.contact_link}")

        # Telegram max size is 4096 chars; we keep this short but safe.
        msg = "\n".join(lines)
        return msg[:3800]


def load_state(state_path: str) -> Dict[str, Any]:
    if not os.path.exists(state_path):
        return {"notified_keys": [], "bootstrapped": False, "last_checked_utc": None}
    with open(state_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "notified_keys" not in data:
        data["notified_keys"] = []
    if "bootstrapped" not in data:
        data["bootstrapped"] = False
    if "last_checked_utc" not in data:
        data["last_checked_utc"] = None
    return data


def save_state(state_path: str, state: Dict[str, Any]) -> None:
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, state_path)


def _guess_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
        return dialect.delimiter
    except Exception:
        return ","


def fetch_sheet_csv(sheet_id: str, gid: str, timeout_s: int = 30) -> str:
    headers = {
        "User-Agent": "einab-notifier/1.0 (+https://example.local)",
        "Accept": "text/csv,text/plain,*/*",
    }

    # Google Sheets “export” endpoints can behave differently depending on environment.
    # Try multiple equivalent ways to get CSV.
    urls = [
        SHEET_EXPORT_URL_TMPL.format(sheet_id=sheet_id, gid=gid),
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:tsv&gid={gid}",
    ]

    last_exc: Optional[Exception] = None
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            # Google exports should be UTF-8; utf-8-sig tolerates BOM.
            return resp.content.decode("utf-8-sig", errors="replace")
        except Exception as e:  # noqa: BLE001 - keep best-effort fallback
            last_exc = e
            continue

    # If all attempts fail, re-raise the last exception.
    assert last_exc is not None
    raise last_exc


def parse_entries_from_csv(csv_text: str) -> List[Entry]:
    delimiter = _guess_delimiter(csv_text[:4096])
    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    rows = list(reader)

    header_idx = None
    header_row: List[str] = []
    for idx, row in enumerate(rows[:80]):
        if not row:
            continue
        joined = " ".join([_norm(c).lower() for c in row])
        if ("category" in joined or "kategorie" in joined) and "status" in joined:
            header_idx = idx
            header_row = row
            break
    # Fallback: screenshot-like default column positions.
    # A: Category, B: Fairteiler, C: Date, D: Time, F: Status, G: Instructor name, H: contact link, I: Comment.
    default_indices = {
        "category": 0,
        "fairshare": 1,
        "date": 2,
        "time": 3,
        "status": 5,
        "instructor": 6,
        "contact_link": 7,
        "comment": 8,
    }
    indices = dict(default_indices)

    if header_idx is not None:
        # Map headers by substrings.
        for j, cell in enumerate(header_row):
            n = _norm(cell).lower()
            if not n:
                continue
            if indices.get("category") == 0 and ("category" in n or n == "kategorie" or "kategorie" in n):
                indices["category"] = j
            if ("fairteiler" in n) or ("fair-share" in n) or ("fair share" in n) or ("visit of fair" in n):
                indices["fairshare"] = j
            if n in ("date", "datum") or "date" in n or "datum" in n:
                indices["date"] = j
            if n in ("time", "uhrzeit") or "time" in n or "uhrzeit" in n:
                indices["time"] = j
            if "status" in n:
                indices["status"] = j
            if "instructor" in n and "contact" not in n and "instructor" in n:
                indices["instructor"] = j
            if "instructor" in n and "contact" in n:
                indices["contact_link"] = j
            if "comment" in n or "notes" in n:
                indices["comment"] = j

    start_idx = (header_idx + 1) if header_idx is not None else 0
    entries: List[Entry] = []
    for row in rows[start_idx:]:
        if not row or len(row) < 2:
            continue
        category = _norm(row[indices["category"]]) if indices["category"] < len(row) else ""
        status = _norm(row[indices["status"]]) if indices["status"] < len(row) else ""
        date = _norm(row[indices["date"]]) if indices["date"] < len(row) else ""
        time = _norm(row[indices["time"]]) if indices["time"] < len(row) else ""
        instructor = _norm(row[indices["instructor"]]) if indices["instructor"] < len(row) else ""
        fairshare = _norm(row[indices["fairshare"]]) if indices["fairshare"] < len(row) else ""
        contact_link = _norm(row[indices["contact_link"]]) if indices["contact_link"] < len(row) else ""
        comment = _norm(row[indices["comment"]]) if indices["comment"] < len(row) else ""

        # Skip empty lines.
        if not category:
            continue
        if not date or not time:
            # Some rows can exist with only category-ish text; ignore them.
            continue
        if not status:
            continue

        key = _sha1_key(
            [
                _norm_key_part(category),
                date,
                time,
                _norm_key_part(instructor),
                _norm_key_part(status),
            ]
        )
        entries.append(
            Entry(
                key=key,
                category=category,
                fairshare=fairshare,
                date=date,
                time=time,
                status=status,
                instructor=instructor,
                contact_link=contact_link,
                comment=comment,
            )
        )
    return entries


def filter_entries(
    entries: List[Entry],
    notify_status_contains: List[str],
) -> List[Entry]:
    needles = [n.lower() for n in notify_status_contains]
    out: List[Entry] = []
    for e in entries:
        s = e.status.lower()
        if any(n in s for n in needles):
            out.append(e)
    return out


def send_telegram(bot_token: str, chat_id: str, text: str, timeout_s: int = 30) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-path", default="state.json")
    ap.add_argument("--sheet-id", default=os.environ.get("SHEET_ID", "1blyF1PRpGZMLGf6ZzSXp88kkGnvtetEUJ7Mk3sV-ExM"))
    ap.add_argument("--gid", default=os.environ.get("SHEET_GID", "917833898"))
    ap.add_argument("--notify-status", default=os.environ.get("NOTIFY_STATUS", "frei"))
    ap.add_argument(
        "--skip-existing",
        default=os.environ.get("SKIP_EXISTING", "true").lower() in ("1", "true", "yes", "y", "on"),
        action="store_true",
    )
    # Make arg handling tolerant if argparse sees --skip-existing explicitly.
    ap.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    ap.add_argument("--dry-run", default=os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes", "y", "on"), action="store_true")
    ap.add_argument(
        "--reset-state",
        default=os.environ.get("RESET_STATE", "false").lower() in ("1", "true", "yes", "y", "on"),
        action="store_true",
    )
    args = ap.parse_args()

    # argparse quirk: we defined --skip-existing as both a boolean and store_true.
    # Normalize it after parsing.
    skip_existing: bool = getattr(args, "skip_existing", None)
    if skip_existing is None:
        skip_existing = args.skip_existing if hasattr(args, "skip_existing") else True

    notify_status_contains = [s.strip() for s in args.notify_status.split(",") if s.strip()]
    if not notify_status_contains:
        notify_status_contains = ["frei"]

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not args.dry_run and (not telegram_token or not telegram_chat_id):
        print("Missing Telegram env vars: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 2

    state = load_state(args.state_path)
    if args.reset_state:
        state = {"notified_keys": [], "bootstrapped": False, "last_checked_utc": None}
    notified_keys = set(state.get("notified_keys", []))

    print(f"Fetching sheet export (sheet_id={args.sheet_id}, gid={args.gid})...")
    csv_text = fetch_sheet_csv(args.sheet_id, args.gid)
    entries = parse_entries_from_csv(csv_text)
    candidates = filter_entries(entries, notify_status_contains=notify_status_contains)

    # Determine bootstrapping behavior.
    bootstrapped = bool(state.get("bootstrapped", False))
    now_utc = datetime.now(timezone.utc).isoformat()

    if (not bootstrapped) and skip_existing:
        # On first run: don't spam, just remember what exists right now.
        for e in candidates:
            notified_keys.add(e.key)
        state["notified_keys"] = sorted(notified_keys)
        state["bootstrapped"] = True
        state["last_checked_utc"] = now_utc
        save_state(args.state_path, state)
        print(f"Bootstrapped: remembered {len(candidates)} existing candidate entries (no notifications).")
        return 0

    new_entries = [e for e in candidates if e.key not in notified_keys]
    if not new_entries:
        state["last_checked_utc"] = now_utc
        save_state(args.state_path, state)
        print("No new entries found.")
        return 0

    print(f"Found {len(new_entries)} new entries.")
    if not args.dry_run:
        for e in new_entries:
            send_telegram(telegram_token, telegram_chat_id, e.telegram_text())

    for e in new_entries:
        notified_keys.add(e.key)
    state["notified_keys"] = sorted(notified_keys)
    state["bootstrapped"] = True
    state["last_checked_utc"] = now_utc
    save_state(args.state_path, state)
    if args.dry_run:
        print("Dry run: would have sent notifications.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

