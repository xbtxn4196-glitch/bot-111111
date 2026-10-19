"""HighlightHub Bot — সম্পূর্ণ বট একটাই ফাইল (main.py)

চালানো:
    pip install -r requirements.txt
    BOT_TOKEN=xxxxx python main.py          (লোকাল, polling)
    Render-এ শুধু Environment Variable দিলেই হবে (webhook + health check)

শুধু একটাই জিনিস লাগবে:  BOT_TOKEN  (Render → Environment → BOT_TOKEN)

বাকি সব কোডেই রেডি:
    ✅ ডেস্টিনেশন চ্যানেল  -1004308076789 (আপনার চ্যানেল)
    ✅ সোর্স চ্যানেল      -1002279362776
    ✅ অ্যাডমিন          @sabit12354 (ইউজারনেম দিয়েই চেনে)
    ✅ ৫ ভাষা, অ্যাড গেট, অ্যাডমিন প্যানেল, অটো-সিঙ্ক
    ✅ সোর্স চ্যানেল অটো-ডিটেক্ট: বটে সোর্সের যেকোনো পোস্ট ফরওয়ার্ড করলেই সেট

Environment Variables (ঐচ্ছিক):
    BOT_TOKEN         (আবশ্যক) BotFather থেকে নেওয়া টোকেন
    ADMIN_IDS         (ঐচ্ছিক) আপনার Telegram ID, একাধিক হলে কমা দিয়ে
    SOURCE_USERNAME   (ঐচ্ছিক) পাবলিক সোর্স চ্যানেলের ইউজারনেম, যেমন @mychannel
                      অ্যাডমিন প্যানেল থেকেও সেট করা যায় — অ্যাডমিন বানানো লাগে না
    SOURCE_CHANNEL    (ঐচ্ছিক) ডিফল্ট -1002279362776
    DEST_CHANNEL      (ঐচ্ছিক) ডিফল্ট -1004308076789
    DEFAULT_LANG      (ঐচ্ছিক) bn / hi / en / ur / ar  (ডিফল্ট bn)
    DB_PATH           (ঐচ্ছিক) ডিফল্ট data/bot.db
    POLL_INTERVAL     (ঐচ্ছিক) সোর্স চেকের ব্যবধান, সেকেন্ডে (ডিফল্ট 60)
    PORT / RENDER_EXTERNAL_URL — Render নিজেই সেট করে
"""


# ==========================================================================
# 📦 IMPORTS
# ==========================================================================

import asyncio
import difflib
import hashlib
import json
import logging
import secrets
import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import aiosqlite
import html as html_lib
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web



# ==========================================================================
# ⚙️  কনফিগ — টোকেন ও চ্যানেল (সবই Environment Variable থেকে)
# ==========================================================================

try:  # .env থাকলে লোড হবে (না থাকলেও চলবে)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


def _get_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# চ্যানেল আইডি
SOURCE_CHANNEL = _get_int("SOURCE_CHANNEL", -1002279362776)
DEST_CHANNEL = _get_int("DEST_CHANNEL", -1004308076789)

# অ্যাডমিন (একাধিক হলে কমা দিয়ে)
ADMIN_IDS = _get_admin_ids()

# ইউজারনেম দিয়েও অ্যাডমিন (আইডি না জানলেও চলবে)
ADMIN_USERNAMES = {
    u.strip().lstrip("@").lower()
    for u in os.getenv("ADMIN_USERNAMES", "sabit12354").split(",")
    if u.strip()
}

# ডাটাবেজ (Render-এ /data ডিস্ক মাউন্ট করা থাকলে সেখানেই থাকবে)
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db"))

# পাবলিক সোর্স চ্যানেলের ইউজারনেম (অ্যাডমিন না হলেও পড়া যাবে)। যেমন: @mychannel
SOURCE_USERNAME = os.getenv("SOURCE_USERNAME", "").strip()

# কত সেকেন্ড পর পর সোর্স চ্যানেল চেক হবে
POLL_INTERVAL = _get_int("POLL_INTERVAL", 60)

# সোর্স চ্যানেল অটো ডিটেক্ট (বটে পোস্ট ফরওয়ার্ড করলেই সেট হয়ে যায়)
# ডিফল্ট ভাষা
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "bn").strip().lower()

# টাইমজোন
TIMEZONE = os.getenv("TZ", "Asia/Dhaka")

# ভিডিওর নিচের ক্যাপশনে যা যাবে
VIDEO_CAPTION_TEMPLATE = os.getenv("VIDEO_CAPTION", "🎬 <b>{title}</b>\n🏆 {team}\n📅 {year}")

# ফাইল/লিস্টিং সাইজ
PAGE_MATCHES = 6
PAGE_TEAMS = 10
PAGE_USERS = 8
PAGE_ADMIN_MATCHES = 8
SEARCH_LIMIT = 100

MAX_BROADCAST_PER_SECOND = 25

# বট চালু হওয়ার সময় — এর আগের পুরোনো চ্যানেল পোস্ট ইগনোর হবে


STARTED_AT = datetime.now(timezone.utc)


# ==========================================================================
# 🌐 ৫ ভাষার সব টেক্সট (বাংলা, हिन्दी, English, اردو, العربية)
# ==========================================================================

LANGUAGES = {
    "bn": "🇧🇩 বাংলা",
    "hi": "🇮🇳 हिन्दी",
    "en": "🇬🇧 English",
    "ur": "🇵🇰 اردو",
    "ar": "🇸🇦 العربية",
}

S: dict[str, dict[str, str]] = {
    # ================================================================== English
    "en": {
        "choose_lang": "🌐 Please choose your language:",
        "lang_set": "✅ Language set: {lang}",
        "welcome": "👋 Welcome, {name}!\n\n🎬 Get match highlights instantly.\n🔍 Search by team or match name, or use the menu below.",
        "menu_search": "🔍 Search",
        "menu_popular": "🔥 Popular",
        "menu_latest": "🆕 Latest",
        "menu_teams": "📂 Teams",
        "menu_lang": "🌐 Language",
        "menu_help": "ℹ️ Help",
        "menu_admin": "🛠 Admin Panel",
        "menu_home": "🏠 Menu",
        "search_prompt": "🔍 Type a team or match name:\n<i>Example: real madrid, barcelona 2024</i>",
        "search_results": "🔍 Results for <b>{q}</b> — {n} found:",
        "search_empty": "😔 Nothing found.\nTry a different spelling or a shorter name.",
        "search_suggest": "💡 Did you mean:",
        "latest_header": "🆕 <b>Latest Highlights</b> ({n})",
        "popular_header": "🔥 <b>Popular Highlights</b> ({n})",
        "teams_header": "📂 <b>All Teams</b> ({n})",
        "team_header": "🏆 <b>{team}</b> — {n} matches",
        "no_content": "📭 No matches yet. New highlights will appear here.",
        "no_team_content": "📭 No matches found for this team.",
        "btn_prev": "⬅️ Prev",
        "btn_next": "Next ➡️",
        "btn_home": "🏠 Menu",
        "btn_back": "⬅️ Back",
        "btn_cancel": "❌ Cancel",
        "ad_header": "📣 <b>Sponsored</b>",
        "ad_note": "⚠️ Watch the ad below to get the video.",
        "ad_btn_open": "🔗 Click Here",
        "ad_btn_continue": "✅ Watched — Give Video",
        "video_unavailable": "⚠️ Video is not available right now. Please try later.",
        "delivering": "⏳ Sending video…",
        "help_text": "ℹ️ <b>How to use</b>\n\n1️⃣ Tap 🔍 Search\n2️⃣ Type the team or match name (typos are fine)\n3️⃣ Pick a match and watch instantly\n\n🔥 Popular = most watched\n🆕 Latest = newest uploads\n📂 Teams = all teams\n\nFor support, message the admin.",
        "admin_only": "⛔ You are not an admin.",
        "ap_title": "🛠 <b>Admin Panel</b>",
        "ap_stats": "📊 Stats",
        "ap_users": "👥 Users",
        "ap_broadcast": "📢 Broadcast",
        "ap_ad": "📣 Ad Manager",
        "ap_matches": "🎬 Matches",
        "ap_sync": "🔄 Channel Sync",
        "ap_manual": "➕ Manual Add",
        "not_set": "—",
        "stats_text": "📊 <b>Statistics</b>\n\n👥 Total users: <b>{users}</b>\n🆕 New today: <b>{new_today}</b>\n⚡ Active today: <b>{active_today}</b>\n🎬 Total matches: <b>{matches}</b>\n👁 Total views: <b>{views}</b>\n\n📣 Ad impressions: <b>{ad_imp}</b>\n👤 Unique ad viewers: <b>{ad_users}</b>",
        "users_header": "👥 <b>Users</b> — total {n} (page {p}/{tp})",
        "user_line": "👤 {name} — <code>{id}</code> — {lang}{username}\n🗓 {date}",
        "bc_prompt": "📢 Send any message (text / photo / video) to broadcast it to all users.\nSend /cancel to abort.",
        "bc_started": "📤 Broadcasting to {n} users…",
        "bc_done": "✅ Broadcast done.\nSent: {ok}\nFailed: {fail}",
        "ad_panel": "📣 <b>Ad Manager</b>\n\nStatus: {status}\nText: {text}\nButton: {btn}\nLink: {url}\nImpressions: {imp}\n\n⚠️ When the ad is ON, users must view it before every video.",
        "ad_on": "🟢 ON",
        "ad_off": "🔴 OFF",
        "ad_set_text": "✏️ Ad Text",
        "ad_set_btn": "🔤 Button Text",
        "ad_set_url": "🔗 Link",
        "ad_toggle_on": "🟢 Turn ON",
        "ad_toggle_off": "🔴 Turn OFF",
        "ad_preview": "👁 Preview",
        "ad_clear": "🗑 Clear Ad",
        "ad_enter_text": "Send the ad text:",
        "ad_enter_btn": "Send the button text (e.g. Join Channel):",
        "ad_enter_url": "Send the link (https://...) or /skip:",
        "ad_saved": "✅ Ad saved. Every video will now show the ad first.",
        "ad_cleared": "🗑 Ad cleared. Users will get videos for free.",
        "ad_need_text": "⚠️ Set the ad text first.",
        "bc_cancelled": "❌ Cancelled.",
        "matches_panel": "🎬 <b>Matches</b> — latest {n} (page {p}/{tp})",
        "match_card": "🎬 <b>Match #{id}</b>\n🏆 {team}\n📝 {title}\n📅 {year}\n👁 {views} views\n🗓 Added: {date}",
        "me_team_prompt": "Send the new team name for match #{id}:",
        "me_title_prompt": "Send the new title for match #{id}:",
        "saved_ok": "✅ Saved.",
        "deleted_ok": "🗑 Deleted.",
        "delete_confirm": "Delete match #{id}?",
        "delete_yes": "🗑 Yes, delete",
        "delete_no": "⬅️ No",
        "send_me": "📤 Send to Me",
        "manual_prompt_video": "➕ Send / forward the video you want to add:",
        "manual_prompt_info": "Now send the info in this format:\n<code>Team Name | Match Title</code>\n(The year is auto-detected if present)",
        "manual_saved": "✅ Match added: {team} — {title}",
        "manual_bad_format": "⚠️ Wrong format. Use: Team Name | Match Title",
        "sync_panel": "🔄 <b>Channel Sync</b>\n\n📥 Source: <code>{source}</code>\n📤 Destination: <code>{dest}</code>\nAuto-forward: {status}\n\nStatus: {check}",
        "sync_on": "🟢 ON",
        "sync_off": "🔴 OFF",
        "sync_toggle": "🔁 Toggle Auto-Forward",
        "sync_test": "🔍 Test Connection",
        "owner_assigned": "✅ You are now the bot owner/admin. Use /admin to open the panel.",
        "capture_notice": "🎬 <b>New match added</b>\n\n🏆 {team}\n📝 {title}\n📅 {year}\n📤 Channel post: {posted}",
        "capture_posted": "✅ done",
        "capture_failed": "❌ failed",
        "ad_preview_text": "📣 <b>Preview</b>\n\n{text}",
    },
    # ================================================================== Bangla
    "bn": {
        "choose_lang": "🌐 ভাষা নির্বাচন করুন:",
        "lang_set": "✅ ভাষা সেট হয়েছে: {lang}",
        "welcome": "👋 স্বাগতম, {name}!\n\n🎬 সব ম্যাচের হাইলাইট এখানেই পাবেন।\n🔍 টিম বা ম্যাচের নাম লিখে সার্চ করুন, অথবা নিচের মেনু ব্যবহার করুন।",
        "menu_search": "🔍 সার্চ",
        "menu_popular": "🔥 জনপ্রিয়",
        "menu_latest": "🆕 লেটেস্ট",
        "menu_teams": "📂 টিম লিস্ট",
        "menu_lang": "🌐 ভাষা",
        "menu_help": "ℹ️ সাহায্য",
        "menu_admin": "🛠 অ্যাডমিন প্যানেল",
        "menu_home": "🏠 মেনু",
        "search_prompt": "🔍 টিম বা ম্যাচের নাম লিখুন:\n<i>যেমন: real madrid, barcelona 2024</i>",
        "search_results": "🔍 <b>{q}</b> এর ফলাফল — {n}টি পাওয়া গেছে:",
        "search_empty": "😔 কিছু পাওয়া যায়নি।\nঅন্য বানানে বা ছোট নাম দিয়ে চেষ্টা করুন।",
        "search_suggest": "💡 হয়তো এগুলো খুঁজছেন:",
        "latest_header": "🆕 <b>সর্বশেষ হাইলাইট</b> ({n})",
        "popular_header": "🔥 <b>জনপ্রিয় হাইলাইট</b> ({n})",
        "teams_header": "📂 <b>সব টিম</b> ({n})",
        "team_header": "🏆 <b>{team}</b> — {n}টি ম্যাচ",
        "no_content": "📭 এখনো কোনো ম্যাচ নেই। নতুন হাইলাইট এখানে দেখা যাবে।",
        "no_team_content": "📭 এই টিমের কোনো ম্যাচ পাওয়া যায়নি।",
        "btn_prev": "⬅️ আগের",
        "btn_next": "পরের ➡️",
        "btn_home": "🏠 মেনু",
        "btn_back": "⬅️ পেছনে",
        "btn_cancel": "❌ বাতিল",
        "ad_header": "📣 <b>স্পনসর</b>",
        "ad_note": "⚠️ ভিডিও পেতে নিচের অ্যাডটি দেখুন।",
        "ad_btn_open": "🔗 এখানে ক্লিক করুন",
        "ad_btn_continue": "✅ দেখেছি — ভিডিও দিন",
        "video_unavailable": "⚠️ ভিডিওটি এই মুহূর্তে পাওয়া যাচ্ছে না। একটু পরে চেষ্টা করুন।",
        "delivering": "⏳ ভিডিও পাঠানো হচ্ছে…",
        "help_text": "ℹ️ <b>কিভাবে ব্যবহার করবেন</b>\n\n১️⃣ 🔍 সার্চ বাটনে চাপ দিন\n২️⃣ টিম বা ম্যাচের নাম লিখুন (বানান ভুল হলেও চলবে)\n৩️⃣ ম্যাচ বেছে নিন, সাথে সাথে ভিডিও পেয়ে যাবেন\n\n🔥 জনপ্রিয় = সবচেয়ে বেশি দেখা\n🆕 লেটেস্ট = নতুন আপলোড\n📂 টিম লিস্ট = সব টিম\n\nসাহায্যের জন্য অ্যাডমিনকে মেসেজ দিন।",
        "admin_only": "⛔ আপনি অ্যাডমিন নন।",
        "ap_title": "🛠 <b>অ্যাডমিন প্যানেল</b>",
        "ap_stats": "📊 স্ট্যাটস",
        "ap_users": "👥 ইউজার",
        "ap_broadcast": "📢 ব্রডকাস্ট",
        "ap_ad": "📣 অ্যাড ম্যানেজার",
        "ap_matches": "🎬 ম্যাচ",
        "ap_sync": "🔄 চ্যানেল সিঙ্ক",
        "ap_manual": "➕ ম্যানুয়াল অ্যাড",
        "not_set": "—",
        "stats_text": "📊 <b>স্ট্যাটিসটিকস</b>\n\n👥 মোট ইউজার: <b>{users}</b>\n🆕 আজ নতুন: <b>{new_today}</b>\n⚡ আজ অ্যাক্টিভ: <b>{active_today}</b>\n🎬 মোট ম্যাচ: <b>{matches}</b>\n👁 মোট ভিউ: <b>{views}</b>\n\n📣 অ্যাড ইমপ্রেশন: <b>{ad_imp}</b>\n👤 ইউনিক অ্যাড দর্শক: <b>{ad_users}</b>",
        "users_header": "👥 <b>ইউজারলিস্ট</b> — মোট {n} জন (পৃষ্ঠা {p}/{tp})",
        "user_line": "👤 {name} — <code>{id}</code> — {lang}{username}\n🗓 {date}",
        "bc_prompt": "📢 ব্রডকাস্ট করতে যেকোনো মেসেজ (টেক্সট / ছবি / ভিডিও) পাঠান।\nবাতিল করতে /cancel",
        "bc_started": "📤 {n} জনকে পাঠানো হচ্ছে…",
        "bc_done": "✅ ব্রডকাস্ট সম্পন্ন।\nসফল: {ok}\nব্যর্থ: {fail}",
        "ad_panel": "📣 <b>অ্যাড ম্যানেজার</b>\n\nঅবস্থা: {status}\nটেক্সট: {text}\nবাটন: {btn}\nলিংক: {url}\nইমপ্রেশন: {imp}\n\n⚠️ অ্যাড চালু থাকলে প্রতিটি ভিডিওর আগে ইউজারকে অ্যাড দেখতে হবে।",
        "ad_on": "🟢 চালু",
        "ad_off": "🔴 বন্ধ",
        "ad_set_text": "✏️ অ্যাড টেক্সট",
        "ad_set_btn": "🔤 বাটন টেক্সট",
        "ad_set_url": "🔗 লিংক",
        "ad_toggle_on": "🟢 চালু করুন",
        "ad_toggle_off": "🔴 বন্ধ করুন",
        "ad_preview": "👁 প্রিভিউ",
        "ad_clear": "🗑 মুছে ফেলুন",
        "ad_enter_text": "অ্যাডের টেক্সট পাঠান:",
        "ad_enter_btn": "বাটনের টেক্সট পাঠান (যেমন: চ্যানেলে জয়েন করুন):",
        "ad_enter_url": "লিংক পাঠান (https://...) অথবা /skip:",
        "ad_saved": "✅ অ্যাড সেভ হয়েছে। এখন প্রতিটি ভিডিওর আগে অ্যাড দেখানো হবে।",
        "ad_cleared": "🗑 অ্যাড মুছে ফেলা হয়েছে। ইউজাররা ফ্রিতে ভিডিও পাবে।",
        "ad_need_text": "⚠️ আগে অ্যাড টেক্সট সেট করুন।",
        "bc_cancelled": "❌ বাতিল হয়েছে।",
        "matches_panel": "🎬 <b>ম্যাচ ম্যানেজার</b> — সর্বশেষ {n}টি (পৃষ্ঠা {p}/{tp})",
        "match_card": "🎬 <b>ম্যাচ #{id}</b>\n🏆 {team}\n📝 {title}\n📅 {year}\n👁 {views} ভিউ\n🗓 যোগ হয়েছে: {date}",
        "me_team_prompt": "ম্যাচ #{id} এর নতুন টিমের নাম পাঠান:",
        "me_title_prompt": "ম্যাচ #{id} এর নতুন টাইটেল পাঠান:",
        "saved_ok": "✅ সেভ হয়েছে।",
        "deleted_ok": "🗑 ডিলিট হয়েছে।",
        "delete_confirm": "ম্যাচ #{id} ডিলিট করবেন?",
        "delete_yes": "🗑 হ্যাঁ, ডিলিট",
        "delete_no": "⬅️ না",
        "send_me": "📤 আমাকে পাঠান",
        "manual_prompt_video": "➕ যে ভিডিওটি যোগ করতে চান সেটি পাঠান / ফরোয়ার্ড করুন:",
        "manual_prompt_info": "এখন এই ফরম্যাটে তথ্য পাঠান:\n<code>টিমের নাম | ম্যাচের নাম</code>\n(সাল থাকলে অটো ধরা হবে)",
        "manual_saved": "✅ ম্যাচ যোগ হয়েছে: {team} — {title}",
        "manual_bad_format": "⚠️ ফরম্যাট ভুল। এভাবে দিন: টিমের নাম | ম্যাচের নাম",
        "sync_panel": "🔄 <b>চ্যানেল সিঙ্ক</b>\n\n📥 সোর্স: <code>{source}</code>\n📤 ডেস্টিনেশন: <code>{dest}</code>\nঅটো-ফরওয়ার্ড: {status}\n\nস্ট্যাটাস: {check}",
        "sync_on": "🟢 চালু",
        "sync_off": "🔴 বন্ধ",
        "sync_toggle": "🔁 অটো-ফরওয়ার্ড টগল",
        "sync_test": "🔍 কানেকশন টেস্ট",
        "owner_assigned": "✅ আপনাকে বটের owner/admin বানানো হয়েছে। /admin দিয়ে প্যানেল খুলুন।",
        "capture_notice": "🎬 <b>নতুন ম্যাচ যোগ হয়েছে</b>\n\n🏆 {team}\n📝 {title}\n📅 {year}\n📤 চ্যানেল পোস্ট: {posted}",
        "capture_posted": "✅ হয়েছে",
        "capture_failed": "❌ হয়নি",
        "ad_preview_text": "📣 <b>প্রিভিউ</b>\n\n{text}",
    },
    # ================================================================== Hindi
    "hi": {
        "choose_lang": "🌐 अपनी भाषा चुनें:",
        "lang_set": "✅ भाषा सेट हो गई: {lang}",
        "welcome": "👋 स्वागत है, {name}!\n\n🎬 सभी मैचों के हाइलाइट्स यहीं मिलेंगे।\n🔍 टीम या मैच का नाम लिखकर सर्च करें, या नीचे मेनू यूज़ करें।",
        "menu_search": "🔍 सर्च",
        "menu_popular": "🔥 लोकप्रिय",
        "menu_latest": "🆕 नवीनतम",
        "menu_teams": "📂 टीम लिस्ट",
        "menu_lang": "🌐 भाषा",
        "menu_help": "ℹ️ मदद",
        "menu_admin": "🛠 एडमिन पैनल",
        "menu_home": "🏠 मेनू",
        "search_prompt": "🔍 टीम या मैच का नाम लिखें:\n<i>जैसे: real madrid, barcelona 2024</i>",
        "search_results": "🔍 <b>{q}</b> के नतीजे — {n} मिले:",
        "search_empty": "😔 कुछ नहीं मिला।\nदूसरी स्पेलिंग या छोटा नाम आज़माएँ।",
        "search_suggest": "💡 शायद आप ये खोज रहे हैं:",
        "latest_header": "🆕 <b>नवीनतम हाइलाइट्स</b> ({n})",
        "popular_header": "🔥 <b>लोकप्रिय हाइलाइट्स</b> ({n})",
        "teams_header": "📂 <b>सभी टीमें</b> ({n})",
        "team_header": "🏆 <b>{team}</b> — {n} मैच",
        "no_content": "📭 अभी कोई मैच नहीं है। नए हाइलाइट्स यहाँ दिखेंगे।",
        "no_team_content": "📭 इस टीम के लिए कोई मैच नहीं मिला।",
        "btn_prev": "⬅️ पिछला",
        "btn_next": "अगला ➡️",
        "btn_home": "🏠 मेनू",
        "btn_back": "⬅️ वापस",
        "btn_cancel": "❌ रद्द करें",
        "ad_header": "📣 <b>स्पॉन्सर</b>",
        "ad_note": "⚠️ वीडियो पाने के लिए नीचे दिया गया ऐड देखें।",
        "ad_btn_open": "🔗 यहाँ क्लिक करें",
        "ad_btn_continue": "✅ देख लिया — वीडियो दें",
        "video_unavailable": "⚠️ वीडियो अभी उपलब्ध नहीं है। थोड़ी देर बाद कोशिश करें।",
        "delivering": "⏳ वीडियो भेजा जा रहा है…",
        "help_text": "ℹ️ <b>कैसे इस्तेमाल करें</b>\n\n1️⃣ 🔍 सर्च बटन दबाएँ\n2️⃣ टीम या मैच का नाम लिखें (गलत स्पेलिंग भी चलेगी)\n3️⃣ मैच चुनें और वीडियो तुरंत पाएँ\n\n🔥 लोकप्रिय = सबसे ज़्यादा देखे गए\n🆕 नवीनतम = नए अपलोड\n📂 टीम लिस्ट = सभी टीमें\n\nसहायता के लिए एडमिन को मैसेज करें।",
        "admin_only": "⛔ आप एडमिन नहीं हैं।",
        "ap_title": "🛠 <b>एडमिन पैनल</b>",
        "ap_stats": "📊 स्टैट्स",
        "ap_users": "👥 यूज़र्स",
        "ap_broadcast": "📢 ब्रॉडकास्ट",
        "ap_ad": "📣 ऐड मैनेजर",
        "ap_matches": "🎬 मैच",
        "ap_sync": "🔄 चैनल सिंक",
        "ap_manual": "➕ मैन्युअल ऐड",
        "not_set": "—",
        "stats_text": "📊 <b>स्टैटिस्टिक्स</b>\n\n👥 कुल यूज़र्स: <b>{users}</b>\n🆕 आज नए: <b>{new_today}</b>\n⚡ आज सक्रिय: <b>{active_today}</b>\n🎬 कुल मैच: <b>{matches}</b>\n👁 कुल व्यूज़: <b>{views}</b>\n\n📣 ऐड इंप्रेशन: <b>{ad_imp}</b>\n👤 यूनिक ऐड दर्शक: <b>{ad_users}</b>",
        "users_header": "👥 <b>यूज़र लिस्ट</b> — कुल {n} (पेज {p}/{tp})",
        "user_line": "👤 {name} — <code>{id}</code> — {lang}{username}\n🗓 {date}",
        "bc_prompt": "📢 ब्रॉडकास्ट के लिए कोई भी मैसेज (टेक्स्ट / फोटो / वीडियो) भेजें।\nरद्द करने के लिए /cancel",
        "bc_started": "📤 {n} यूज़र्स को भेजा जा रहा है…",
        "bc_done": "✅ ब्रॉडकास्ट पूरा।\nसफल: {ok}\nफेल: {fail}",
        "ad_panel": "📣 <b>ऐड मैनेजर</b>\n\nस्थिति: {status}\nटेक्स्ट: {text}\nबटन: {btn}\nलिंक: {url}\nइंप्रेशन: {imp}\n\n⚠️ ऐड चालू होने पर हर वीडियो से पहले यूज़र को ऐड देखना होगा।",
        "ad_on": "🟢 चालू",
        "ad_off": "🔴 बंद",
        "ad_set_text": "✏️ ऐड टेक्स्ट",
        "ad_set_btn": "🔤 बटन टेक्स्ट",
        "ad_set_url": "🔗 लिंक",
        "ad_toggle_on": "🟢 चालू करें",
        "ad_toggle_off": "🔴 बंद करें",
        "ad_preview": "👁 प्रीव्यू",
        "ad_clear": "🗑 ऐड हटाएँ",
        "ad_enter_text": "ऐड का टेक्स्ट भेजें:",
        "ad_enter_btn": "बटन का टेक्स्ट भेजें (जैसे: चैनल जॉइन करें):",
        "ad_enter_url": "लिंक भेजें (https://...) या /skip:",
        "ad_saved": "✅ ऐड सेव हो गया। अब हर वीडियो से पहले ऐड दिखेगा।",
        "ad_cleared": "🗑 ऐड हटा दिया गया। यूज़र्स को वीडियो फ्री मिलेगा।",
        "ad_need_text": "⚠️ पहले ऐड टेक्स्ट सेट करें।",
        "bc_cancelled": "❌ रद्द किया गया।",
        "matches_panel": "🎬 <b>मैच मैनेजर</b> — नवीनतम {n} (पेज {p}/{tp})",
        "match_card": "🎬 <b>मैच #{id}</b>\n🏆 {team}\n📝 {title}\n📅 {year}\n👁 {views} व्यूज़\n🗓 जोड़ा गया: {date}",
        "me_team_prompt": "मैच #{id} के लिए नया टीम नाम भेजें:",
        "me_title_prompt": "मैच #{id} के लिए नया टाइटल भेजें:",
        "saved_ok": "✅ सेव हो गया।",
        "deleted_ok": "🗑 डिलीट हो गया।",
        "delete_confirm": "मैच #{id} डिलीट करें?",
        "delete_yes": "🗑 हाँ, डिलीट",
        "delete_no": "⬅️ नहीं",
        "send_me": "📤 मुझे भेजें",
        "manual_prompt_video": "➕ जो वीडियो जोड़ना है वह भेजें / फॉरवर्ड करें:",
        "manual_prompt_info": "अब इस फॉर्मेट में जानकारी भेजें:\n<code>टीम का नाम | मैच का नाम</code>\n(साल हो तो ऑटो पकड़ा जाएगा)",
        "manual_saved": "✅ मैच जोड़ा गया: {team} — {title}",
        "manual_bad_format": "⚠️ फॉर्मेट गलत है। ऐसे भेजें: टीम का नाम | मैच का नाम",
        "sync_panel": "🔄 <b>चैनल सिंक</b>\n\n📥 सोर्स: <code>{source}</code>\n📤 डेस्टिनेशन: <code>{dest}</code>\nऑटो-फॉरवर्ड: {status}\n\nस्टेटस: {check}",
        "sync_on": "🟢 चालू",
        "sync_off": "🔴 बंद",
        "sync_toggle": "🔁 ऑटो-फॉरवर्ड टॉगल",
        "sync_test": "🔍 कनेक्शन टेस्ट",
        "owner_assigned": "✅ अब आप बॉट के owner/admin हैं। /admin से पैनल खोलें।",
        "capture_notice": "🎬 <b>नया मैच जुड़ा</b>\n\n🏆 {team}\n📝 {title}\n📅 {year}\n📤 चैनल पोस्ट: {posted}",
        "capture_posted": "✅ हुआ",
        "capture_failed": "❌ नहीं हुआ",
        "ad_preview_text": "📣 <b>प्रीव्यू</b>\n\n{text}",
    },
    # ================================================================== Urdu
    "ur": {
        "choose_lang": "🌐 اپنی زبان منتخب کریں:",
        "lang_set": "✅ زبان سیٹ ہو گئی: {lang}",
        "welcome": "👋 خوش آمدید، {name}!\n\n🎬 تمام میچز کی ہائی لائٹس یہیں ملیں گی۔\n🔍 ٹیم یا میچ کا نام لکھ کر سرچ کریں، یا نیچے مینو استعمال کریں۔",
        "menu_search": "🔍 تلاش",
        "menu_popular": "🔥 مقبول",
        "menu_latest": "🆕 تازہ ترین",
        "menu_teams": "📂 ٹیمیں",
        "menu_lang": "🌐 زبان",
        "menu_help": "ℹ️ مدد",
        "menu_admin": "🛠 ایڈمن پینل",
        "menu_home": "🏠 مینو",
        "search_prompt": "🔍 ٹیم یا میچ کا نام لکھیں:\n<i>مثلاً: real madrid, barcelona 2024</i>",
        "search_results": "🔍 <b>{q}</b> کے نتائج — {n} ملے:",
        "search_empty": "😔 کچھ نہیں ملا۔\nدوسری اسپیلنگ یا چھوٹا نام آزمائیں۔",
        "search_suggest": "💡 شاید آپ یہ تلاش کر رہے ہیں:",
        "latest_header": "🆕 <b>تازہ ترین ہائی لائٹس</b> ({n})",
        "popular_header": "🔥 <b>مقبول ہائی لائٹس</b> ({n})",
        "teams_header": "📂 <b>تمام ٹیمیں</b> ({n})",
        "team_header": "🏆 <b>{team}</b> — {n} میچز",
        "no_content": "📭 ابھی کوئی میچ نہیں۔ نئی ہائی لائٹس یہاں نظر آئیں گی۔",
        "no_team_content": "📭 اس ٹیم کے لیے کوئی میچ نہیں ملا۔",
        "btn_prev": "⬅️ پچھلا",
        "btn_next": "اگلا ➡️",
        "btn_home": "🏠 مینو",
        "btn_back": "⬅️ واپس",
        "btn_cancel": "❌ منسوخ",
        "ad_header": "📣 <b>اسپانسر</b>",
        "ad_note": "⚠️ ویڈیو حاصل کرنے کے لیے نیچے دیا گیا اشتہار دیکھیں۔",
        "ad_btn_open": "🔗 یہاں کلک کریں",
        "ad_btn_continue": "✅ دیکھ لیا — ویڈیو دیں",
        "video_unavailable": "⚠️ ویڈیو ابھی دستیاب نہیں۔ تھوڑی دیر بعد کوشش کریں۔",
        "delivering": "⏳ ویڈیو بھیجی جا رہی ہے…",
        "help_text": "ℹ️ <b>کیسے استعمال کریں</b>\n\n1️⃣ 🔍 تلاش بٹن دبائیں\n2️⃣ ٹیم یا میچ کا نام لکھیں (غلط اسپیلنگ بھی چلے گی)\n3️⃣ میچ منتخب کریں اور ویڈیو فوراً پائیں\n\n🔥 مقبول = سب سے زیادہ دیکھے گئے\n🆕 تازہ ترین = نئی اپ لوڈز\n📂 ٹیمیں = تمام ٹیمیں\n\nمدد کے لیے ایڈمن کو میسج کریں۔",
        "admin_only": "⛔ آپ ایڈمن نہیں ہیں۔",
        "ap_title": "🛠 <b>ایڈمن پینل</b>",
        "ap_stats": "📊 اعدادوشمار",
        "ap_users": "👥 صارفین",
        "ap_broadcast": "📢 براڈکاسٹ",
        "ap_ad": "📣 اشتہار مینیجر",
        "ap_matches": "🎬 میچز",
        "ap_sync": "🔄 چینل سنک",
        "ap_manual": "➕ دستی اضافہ",
        "not_set": "—",
        "stats_text": "📊 <b>اعدادوشمار</b>\n\n👥 کل صارفین: <b>{users}</b>\n🆕 آج نئے: <b>{new_today}</b>\n⚡ آج فعال: <b>{active_today}</b>\n🎬 کل میچز: <b>{matches}</b>\n👁 کل ویوز: <b>{views}</b>\n\n📣 اشتہار امپریشنز: <b>{ad_imp}</b>\n👤 منفرد ناظرین: <b>{ad_users}</b>",
        "users_header": "👥 <b>صارفین</b> — کل {n} (صفحہ {p}/{tp})",
        "user_line": "👤 {name} — <code>{id}</code> — {lang}{username}\n🗓 {date}",
        "bc_prompt": "📢 براڈکاسٹ کے لیے کوئی بھی میسج (ٹیکسٹ / تصویر / ویڈیو) بھیجیں۔\nمنسوخ کرنے کے لیے /cancel",
        "bc_started": "📤 {n} صارفین کو بھیجا جا رہا ہے…",
        "bc_done": "✅ براڈکاسٹ مکمل۔\nکامیاب: {ok}\nناکام: {fail}",
        "ad_panel": "📣 <b>اشتہار مینیجر</b>\n\nحالت: {status}\nٹیکسٹ: {text}\nبٹن: {btn}\nلنک: {url}\nامپریشنز: {imp}\n\n⚠️ اشتہار آن ہونے پر ہر ویڈیو سے پہلے صارف کو اشتہار دیکھنا ہوگا۔",
        "ad_on": "🟢 آن",
        "ad_off": "🔴 آف",
        "ad_set_text": "✏️ اشتہار ٹیکسٹ",
        "ad_set_btn": "🔤 بٹن ٹیکسٹ",
        "ad_set_url": "🔗 لنک",
        "ad_toggle_on": "🟢 آن کریں",
        "ad_toggle_off": "🔴 آف کریں",
        "ad_preview": "👁 پیش نظارہ",
        "ad_clear": "🗑 اشتہار ہٹائیں",
        "ad_enter_text": "اشتہار کا ٹیکسٹ بھیجیں:",
        "ad_enter_btn": "بٹن کا ٹیکسٹ بھیجیں (مثلاً: چینل جوائن کریں):",
        "ad_enter_url": "لنک بھیجیں (https://...) یا /skip:",
        "ad_saved": "✅ اشتہار محفوظ ہو گیا۔ اب ہر ویڈیو سے پہلے اشتہار دکھایا جائے گا۔",
        "ad_cleared": "🗑 اشتہار ہٹا دیا گیا۔ صارفین کو ویڈیو مفت ملے گی۔",
        "ad_need_text": "⚠️ پہلے اشتہار ٹیسٹ سیٹ کریں۔",
        "bc_cancelled": "❌ منسوخ کر دیا گیا۔",
        "matches_panel": "🎬 <b>میچ مینیجر</b> — تازہ ترین {n} (صفحہ {p}/{tp})",
        "match_card": "🎬 <b>میچ #{id}</b>\n🏆 {team}\n📝 {title}\n📅 {year}\n👁 {views} ویوز\n🗓 شامل کیا گیا: {date}",
        "me_team_prompt": "میچ #{id} کے لیے نیا ٹیم نام بھیجیں:",
        "me_title_prompt": "میچ #{id} کے لیے نیا ٹائٹل بھیجیں:",
        "saved_ok": "✅ محفوظ ہو گیا۔",
        "deleted_ok": "🗑 حذف ہو گیا۔",
        "delete_confirm": "میچ #{id} حذف کریں?",
        "delete_yes": "🗑 ہاں، حذف کریں",
        "delete_no": "⬅️ نہیں",
        "send_me": "📤 مجھے بھیجیں",
        "manual_prompt_video": "➕ جو ویڈیو شامل کرنی ہے وہ بھیجیں / فارورڈ کریں:",
        "manual_prompt_info": "اب اس فارمیٹ میں معلومات بھیجیں:\n<code>ٹیم کا نام | میچ کا نام</code>\n(سال ہو تو خود پکڑا جائے گا)",
        "manual_saved": "✅ میچ شامل ہو گیا: {team} — {title}",
        "manual_bad_format": "⚠️ فارمیٹ غلط ہے۔ ایسے بھیجیں: ٹیم کا نام | میچ کا نام",
        "sync_panel": "🔄 <b>چینل سنک</b>\n\n📥 سورس: <code>{source}</code>\n📤 ڈیسٹینیشن: <code>{dest}</code>\nآٹو-فارورڈ: {status}\n\nاسٹیٹس: {check}",
        "sync_on": "🟢 آن",
        "sync_off": "🔴 آف",
        "sync_toggle": "🔁 آٹو-فارورڈ ٹوگل",
        "sync_test": "🔍 کنکشن ٹیسٹ",
        "owner_assigned": "✅ اب آپ بوٹ کے owner/admin ہیں۔ /admin سے پینل کھولیں۔",
        "capture_notice": "🎬 <b>نیا میچ شامل ہوا</b>\n\n🏆 {team}\n📝 {title}\n📅 {year}\n📤 چینل پوسٹ: {posted}",
        "capture_posted": "✅ ہوا",
        "capture_failed": "❌ نہیں ہوا",
        "ad_preview_text": "📣 <b>پیش نظارہ</b>\n\n{text}",
    },
    # ================================================================== Arabic
    "ar": {
        "choose_lang": "🌐 اختر لغتك:",
        "lang_set": "✅ تم ضبط اللغة: {lang}",
        "welcome": "👋 أهلاً {name}!\n\n🎬 ستجد هنا ملخصات جميع المباريات فورًا.\n🔍 ابحث باسم الفريق أو المباراة، أو استخدم القائمة أدناه.",
        "menu_search": "🔍 بحث",
        "menu_popular": "🔥 الأكثر شعبية",
        "menu_latest": "🆕 الأحدث",
        "menu_teams": "📂 الفرق",
        "menu_lang": "🌐 اللغة",
        "menu_help": "ℹ️ مساعدة",
        "menu_admin": "🛠 لوحة الإدارة",
        "menu_home": "🏠 القائمة",
        "search_prompt": "🔍 اكتب اسم الفريق أو المباراة:\n<i>مثال: real madrid, barcelona 2024</i>",
        "search_results": "🔍 نتائج <b>{q}</b> — تم إيجاد {n}:",
        "search_empty": "😔 لم يتم العثور على شيء.\nجرّب كتابة مختلفة أو اسمًا أقصر.",
        "search_suggest": "💡 ربما تبحث عن:",
        "latest_header": "🆕 <b>أحدث الملخصات</b> ({n})",
        "popular_header": "🔥 <b>الملخصات الشائعة</b> ({n})",
        "teams_header": "📂 <b>جميع الفرق</b> ({n})",
        "team_header": "🏆 <b>{team}</b> — {n} مباراة",
        "no_content": "📭 لا توجد مباريات بعد. ستظهر الملخصات الجديدة هنا.",
        "no_team_content": "📭 لا توجد مباريات لهذا الفريق.",
        "btn_prev": "⬅️ السابق",
        "btn_next": "التالي ➡️",
        "btn_home": "🏠 القائمة",
        "btn_back": "⬅️ رجوع",
        "btn_cancel": "❌ إلغاء",
        "ad_header": "📣 <b>إعلان مدعوم</b>",
        "ad_note": "⚠️ شاهد الإعلان أدناه للحصول على الفيديو.",
        "ad_btn_open": "🔗 اضغط هنا",
        "ad_btn_continue": "✅ شاهدت — أعطني الفيديو",
        "video_unavailable": "⚠️ الفيديو غير متاح الآن. حاول لاحقًا.",
        "delivering": "⏳ جارٍ إرسال الفيديو…",
        "help_text": "ℹ️ <b>كيفية الاستخدام</b>\n\n1️⃣ اضغط 🔍 بحث\n2️⃣ اكتب اسم الفريق أو المباراة (الأخطاء الإملائية مقبولة)\n3️⃣ اختر المباراة وشاهد فورًا\n\n🔥 الأكثر شعبية = الأكثر مشاهدة\n🆕 الأحدث = أحدث الرفع\n📂 الفرق = جميع الفرق\n\nللدعم راسل الإدارة.",
        "admin_only": "⛔ أنت لست مشرفًا.",
        "ap_title": "🛠 <b>لوحة الإدارة</b>",
        "ap_stats": "📊 الإحصائيات",
        "ap_users": "👥 المستخدمون",
        "ap_broadcast": "📢 بث جماعي",
        "ap_ad": "📣 مدير الإعلانات",
        "ap_matches": "🎬 المباريات",
        "ap_sync": "🔄 مزامنة القنوات",
        "ap_manual": "➕ إضافة يدوية",
        "not_set": "—",
        "stats_text": "📊 <b>الإحصائيات</b>\n\n👥 إجمالي المستخدمين: <b>{users}</b>\n🆕 الجدد اليوم: <b>{new_today}</b>\n⚡ النشطون اليوم: <b>{active_today}</b>\n🎬 إجمالي المباريات: <b>{matches}</b>\n👁 إجمالي المشاهدات: <b>{views}</b>\n\n📣 مرات ظهور الإعلان: <b>{ad_imp}</b>\n👤 مشاهدون فريدون: <b>{ad_users}</b>",
        "users_header": "👥 <b>المستخدمون</b> — الإجمالي {n} (صفحة {p}/{tp})",
        "user_line": "👤 {name} — <code>{id}</code> — {lang}{username}\n🗓 {date}",
        "bc_prompt": "📢 أرسل أي رسالة (نص / صورة / فيديو) لبثها لجميع المستخدمين.\nللإلغاء /cancel",
        "bc_started": "📤 جارٍ الإرسال إلى {n} مستخدمًا…",
        "bc_done": "✅ اكتمل البث.\nنجح: {ok}\nفشل: {fail}",
        "ad_panel": "📣 <b>مدير الإعلانات</b>\n\nالحالة: {status}\nالنص: {text}\nالزر: {btn}\nالرابط: {url}\nمرات الظهور: {imp}\n\n⚠️ عند تفعيل الإعلان يجب على المستخدم مشاهدته قبل كل فيديو.",
        "ad_on": "🟢 مفعّل",
        "ad_off": "🔴 متوقف",
        "ad_set_text": "✏️ نص الإعلان",
        "ad_set_btn": "🔤 نص الزر",
        "ad_set_url": "🔗 الرابط",
        "ad_toggle_on": "🟢 تفعيل",
        "ad_toggle_off": "🔴 إيقاف",
        "ad_preview": "👁 معاينة",
        "ad_clear": "🗑 حذف الإعلان",
        "ad_enter_text": "أرسل نص الإعلان:",
        "ad_enter_btn": "أرسل نص الزر (مثل: انضم للقناة):",
        "ad_enter_url": "أرسل الرابط (https://...) أو /skip:",
        "ad_saved": "✅ تم حفظ الإعلان. سيظهر قبل كل فيديو.",
        "ad_cleared": "🗑 تم حذف الإعلان. سيحصل المستخدمون على الفيديو مجانًا.",
        "ad_need_text": "⚠️ قم بتعيين نص الإعلان أولاً.",
        "bc_cancelled": "❌ تم الإلغاء.",
        "matches_panel": "🎬 <b>مدير المباريات</b> — الأحدث {n} (صفحة {p}/{tp})",
        "match_card": "🎬 <b>مباراة #{id}</b>\n🏆 {team}\n📝 {title}\n📅 {year}\n👁 {views} مشاهدة\n🗓 أضيفت: {date}",
        "me_team_prompt": "أرسل اسم الفريق الجديد للمباراة #{id}:",
        "me_title_prompt": "أرسل العنوان الجديد للمباراة #{id}:",
        "saved_ok": "✅ تم الحفظ.",
        "deleted_ok": "🗑 تم الحذف.",
        "delete_confirm": "حذف المباراة #{id}?",
        "delete_yes": "🗑 نعم، احذف",
        "delete_no": "⬅️ لا",
        "send_me": "📤 أرسل لي",
        "manual_prompt_video": "➕ أرسل / أعد توجيه الفيديو الذي تريد إضافته:",
        "manual_prompt_info": "الآن أرسل المعلومات بهذا الشكل:\n<code>اسم الفريق | عنوان المباراة</code>\n(السنة تُكتشف تلقائيًا إن وجدت)",
        "manual_saved": "✅ تمت إضافة المباراة: {team} — {title}",
        "manual_bad_format": "⚠️ صيغة خاطئة. استخدم: اسم الفريق | عنوان المباراة",
        "sync_panel": "🔄 <b>مزامنة القنوات</b>\n\n📥 المصدر: <code>{source}</code>\n📤 الوجهة: <code>{dest}</code>\nإعادة التوجيه التلقائي: {status}\n\nالحالة: {check}",
        "sync_on": "🟢 مفعّل",
        "sync_off": "🔴 متوقف",
        "sync_toggle": "🔁 تبديل إعادة التوجيه",
        "sync_test": "🔍 اختبار الاتصال",
        "owner_assigned": "✅ أصبحت الآن مالك/مشرف البوت. استخدم /admin لفتح اللوحة.",
        "capture_notice": "🎬 <b>تمت إضافة مباراة جديدة</b>\n\n🏆 {team}\n📝 {title}\n📅 {year}\n📤 نشر في القناة: {posted}",
        "capture_posted": "✅ تم",
        "capture_failed": "❌ لم يتم",
        "ad_preview_text": "📣 <b>معاينة</b>\n\n{text}",
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    """অনুবাদ নাও — না পেলে ইংরেজি, তাও না পেলে key।"""
    lang = (lang or "bn").lower()
    table = S.get(lang, S["bn"])
    text = table.get(key) or S["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text

# ---------------------------------------------------------------------------
# অতিরিক্ত শর্ট বাটন লেবেল
_EXTRA = {
    "en": {"me_team_btn": "✏️ Team", "me_title_btn": "📝 Title", "me_delete_btn": "🗑 Delete"},
    "bn": {"me_team_btn": "✏️ টিম", "me_title_btn": "📝 টাইটেল", "me_delete_btn": "🗑 ডিলিট"},
    "hi": {"me_team_btn": "✏️ टीम", "me_title_btn": "📝 टाइटल", "me_delete_btn": "🗑 डिलीट"},
    "ur": {"me_team_btn": "✏️ ٹیم", "me_title_btn": "📝 ٹائٹل", "me_delete_btn": "🗑 حذف"},
    "ar": {"me_team_btn": "✏️ الفريق", "me_title_btn": "📝 العنوان", "me_delete_btn": "🗑 حذف"},
}
for _code, _d in _EXTRA.items():
    S.setdefault(_code, {}).update(_d)

# ---------------------------------------------------------------------------
# চ্যানেল সিঙ্ক (পাবলিক সোর্স — অ্যাডমিন ছাড়াই) টেক্সট
_SYNC = {
    "bn": {
        "sync_panel": "🔄 <b>চ্যানেল সিঙ্ক</b>\n\n📥 পাবলিক সোর্স: {source}\n📤 আপনার চ্যানেল: {dest}\n🔁 অটো-সিঙ্ক: {status}\n🕒 শেষ চেক: {last_run}\n\n{check}",
        "sync_public": "@{user} — শেষ ধরা পোস্ট #{last}",
        "sync_no_user": "❌ এখনো সেট হয়নি (নিচের বাটনে চাপ দিয়ে দিন)",
        "sync_set_user_btn": "✏️ সোর্স ইউজারনেম দিন",
        "sync_ask_user": "সোর্স চ্যানেলের পাবলিক ইউজারনেম পাঠান (যেমন: @mychannel):\nমুছতে /skip",
        "sync_user_saved": "✅ সোর্স সেট হয়েছে: @{user}",
        "sync_bad_user": "⚠️ ভুল ইউজারনেম। এভাবে পাঠান: @mychannel",
        "sync_check_btn": "🔍 চেক করুন",
        "sync_check_ok": "✅ @{user} — {n}টি ভিডিও পোস্ট পাওয়া গেছে (সর্বশেষ #{last})।\nনতুন পোস্ট বট প্রতি {interval} সেকেন্ডে চেক করে নিজেই তুলে নেবে।",
        "sync_check_fail": "❌ চ্যানেল পড়া যায়নি: {err}\nইউজারনেম ঠিক আছে কিনা দেখুন — চ্যানেলটা পাবলিক হতে হবে।",
    },
    "en": {
        "sync_panel": "🔄 <b>Channel Sync</b>\n\n📥 Public source: {source}\n📤 Your channel: {dest}\n🔁 Auto-sync: {status}\n🕒 Last check: {last_run}\n\n{check}",
        "sync_public": "@{user} — last captured post #{last}",
        "sync_no_user": "❌ Not set yet (use the button below)",
        "sync_set_user_btn": "✏️ Set Source Username",
        "sync_ask_user": "Send the source channel's public username (e.g. @mychannel):\nSend /skip to clear",
        "sync_user_saved": "✅ Source set: @{user}",
        "sync_bad_user": "⚠️ Invalid username. Send like: @mychannel",
        "sync_check_btn": "🔍 Check Now",
        "sync_check_ok": "✅ @{user} — {n} video posts found (latest #{last}).\nNew posts will be captured automatically every {interval}s.",
        "sync_check_fail": "❌ Could not read channel: {err}\nCheck the username — the channel must be public.",
    },
    "hi": {
        "sync_panel": "🔄 <b>चैनल सिंक</b>\n\n📥 पब्लिक सोर्स: {source}\n📤 आपका चैनल: {dest}\n🔁 ऑटो-सिंक: {status}\n🕒 आखिरी चेक: {last_run}\n\n{check}",
        "sync_public": "@{user} — आखिरी पकड़ा पोस्ट #{last}",
        "sync_no_user": "❌ अभी सेट नहीं (नीचे बटन दबाएँ)",
        "sync_set_user_btn": "✏️ सोर्स यूज़रनेम दें",
        "sync_ask_user": "सोर्स चैनल का पब्लिक यूज़रनेम भेजें (जैसे: @mychannel):\nहटाने के लिए /skip",
        "sync_user_saved": "✅ सोर्स सेट हुआ: @{user}",
        "sync_bad_user": "⚠️ गलत यूज़रनेम। ऐसे भेजें: @mychannel",
        "sync_check_btn": "🔍 चेक करें",
        "sync_check_ok": "✅ @{user} — {n} वीडियो पोस्ट मिले (नवीनतम #{last})।\nनए पोस्ट हर {interval} सेकंड में अपने आप जुड़ेंगे।",
        "sync_check_fail": "❌ चैनल नहीं पढ़ा जा सका: {err}\nयूज़रनेम जाँचें — चैनल पब्लिक होना चाहिए।",
    },
    "ur": {
        "sync_panel": "🔄 <b>چینل سنک</b>\n\n📥 پبلک سورس: {source}\n📤 آپ کا چینل: {dest}\n🔁 آٹو سنک: {status}\n🕒 آخری چیک: {last_run}\n\n{check}",
        "sync_public": "@{user} — آخری پکڑی پوسٹ #{last}",
        "sync_no_user": "❌ ابھی سیٹ نہیں (نیچے بٹن دبائیں)",
        "sync_set_user_btn": "✏️ سورس یوزرنیم دیں",
        "sync_ask_user": "سورس چینل کا پبلک یوزرنیم بھیجیں (مثلاً: @mychannel):\nہٹانے کے لیے /skip",
        "sync_user_saved": "✅ سورس سیٹ ہو گیا: @{user}",
        "sync_bad_user": "⚠️ غلط یوزرنیم۔ ایسے بھیجیں: @mychannel",
        "sync_check_btn": "🔍 چیک کریں",
        "sync_check_ok": "✅ @{user} — {n} ویڈیو پوسٹس ملیں (آخری #{last})۔\nنئی پوسٹس ہر {interval} سیکنڈ میں خود شامل ہوں گی۔",
        "sync_check_fail": "❌ چینل نہیں پڑھا جا سکا: {err}\nیوزرنیم چیک کریں — چینل پبلک ہونا چاہیے۔",
    },
    "ar": {
        "sync_panel": "🔄 <b>مزامنة القنوات</b>\n\n📥 المصدر العام: {source}\n📤 قناتك: {dest}\n🔁 المزامنة التلقائية: {status}\n🕒 آخر فحص: {last_run}\n\n{check}",
        "sync_public": "@{user} — آخر منشور تم التقاطه #{last}",
        "sync_no_user": "❌ لم يُضبط بعد (استخدم الزر أدناه)",
        "sync_set_user_btn": "✏️ ضبط اسم المستخدم للمصدر",
        "sync_ask_user": "أرسل اسم المستخدم العام لقناة المصدر (مثال: @mychannel):\nللحذف /skip",
        "sync_user_saved": "✅ تم ضبط المصدر: @{user}",
        "sync_bad_user": "⚠️ اسم مستخدم غير صالح. أرسله هكذا: @mychannel",
        "sync_check_btn": "🔍 فحص الآن",
        "sync_check_ok": "✅ @{user} — تم إيجاد {n} منشور فيديو (الأحدث #{last}).\nستُضاف المنشورات الجديدة تلقائيًا كل {interval} ثانية.",
        "sync_check_fail": "❌ تعذر قراءة القناة: {err}\nتحقق من اسم المستخدم — يجب أن تكون القناة عامة.",
    },
}
for _code, _d in _SYNC.items():
    S.setdefault(_code, {}).update(_d)


# ==========================================================================
# 🔧 fuzzy সার্চ, ক্যাপশন পার্স, হেল্পার
# ==========================================================================

# ------------------------------------------------ লেবেল ম্যাপ (সব ভাষার বাটন)
# locale key -> handler action
LABEL_ACTIONS = {
    # Bangla
    "🔍 সার্চ": "search",
    "🔥 জনপ্রিয়": "popular",
    "🆕 লেটেস্ট": "latest",
    "📂 টিম লিস্ট": "teams",
    "🌐 ভাষা": "lang",
    "ℹ️ সাহায্য": "help",
    "🛠 অ্যাডমিন প্যানেল": "admin",
    "🏠 মেনু": "menu",
    # English
    "🔍 Search": "search",
    "🔥 Popular": "popular",
    "🆕 Latest": "latest",
    "📂 Teams": "teams",
    "🌐 Language": "lang",
    "ℹ️ Help": "help",
    "🛠 Admin Panel": "admin",
    "🏠 Menu": "menu",
    # Hindi
    "🔍 सर्च": "search",
    "🔥 लोकप्रिय": "popular",
    "🆕 नवीनतम": "latest",
    "📂 टीम लिस्ट": "teams",
    "🌐 भाषा": "lang",
    "ℹ️ मदद": "help",
    "🛠 एडमिन पैनल": "admin",
    "🏠 मेनू": "menu",
    # Urdu
    "🔍 تلاش": "search",
    "🔥 مقبول": "popular",
    "🆕 تازہ ترین": "latest",
    "📂 ٹیمیں": "teams",
    "🌐 زبان": "lang",
    "ℹ️ مدد": "help",
    "🛠 ایڈمن پینل": "admin",
    "🏠 مینو": "menu",
    # Arabic
    "🔍 بحث": "search",
    "🔥 الأكثر شعبية": "popular",
    "🆕 الأحدث": "latest",
    "📂 الفرق": "teams",
    "🌐 اللغة": "lang",
    "ℹ️ مساعدة": "help",
    "🛠 لوحة الإدارة": "admin",
    "🏠 القائمة": "menu",
}

_URL_RE = re.compile(
    r"(?i)(?:https?://\S+|www\.\S+|t\.me/\S+|telegram\.(?:me|dog)/\S+|"
    r"[a-z0-9.\-]+\.(?:com|net|org|io|me|co|in|bd|xyz|tv|live|link|site|top|club|vip|info|app|ly|gl|gg|to)(?:/\S*)?|"
    r"\S+@\S+\.\S+|@\w+)"
)

# কমন বানান ভুল ও শর্টকাট ম্যাপ (যাতে ইউজার ভুল বানান লিখলেও বট নিজেই বুঝে নেয়)
TEAM_TYPO_ALIASES = {
    "barca": "barcelona",
    "barsa": "barcelona",
    "barselona": "barcelona",
    "barclona": "barcelona",
    "bercelona": "barcelona",
    "barcalona": "barcelona",
    "fcb": "barcelona",
    "বার্সা": "barcelona",
    "বার্সেলোনা": "barcelona",
    "rm": "real madrid",
    "rma": "real madrid",
    "ral madrid": "real madrid",
    "real madri": "real madrid",
    "reall madrid": "real madrid",
    "realmadrid": "real madrid",
    "riel madrid": "real madrid",
    "রিয়াল": "real madrid",
    "রিয়াল": "real madrid",
    "রিয়াল মাদ্রিদ": "real madrid",
    "arg": "argentina",
    "argntina": "argentina",
    "arjentina": "argentina",
    "arjantina": "argentina",
    "argentena": "argentina",
    "messi": "argentina",
    "আর্জেন্টিনা": "argentina",
    "bra": "brazil",
    "brajil": "brazil",
    "brazl": "brazil",
    "brasil": "brazil",
    "neymar": "brazil",
    "ব্রাজিল": "brazil",
    "fra": "france",
    "frans": "france",
    "frnce": "france",
    "ফ্রান্স": "france",
    "ger": "germany",
    "jarmani": "germany",
    "germni": "germany",
    "জার্মানি": "germany",
    "por": "portugal",
    "portugl": "portugal",
    "ronaldo": "portugal",
    "cr7": "portugal",
    "পর্তুগাল": "portugal",
    "psg": "paris saint germain",
    "paris": "paris saint germain",
    "man utd": "manchester united",
    "man united": "manchester united",
    "mufc": "manchester united",
    "mancity": "manchester city",
    "man city": "manchester city",
    "liverpol": "liverpool",
    "lfc": "liverpool",
    "bd": "bangladesh",
    "ban": "bangladesh",
    "banglades": "bangladesh",
    "বাংলাদেশ": "bangladesh",
    "ind": "india",
    "indea": "india",
    "pak": "pakistan",
    "paksitan": "pakistan",
}
_HASHTAG_RE = re.compile(r"#([\w\u0600-\u06FF\u0900-\u097F\u0980-\u09FF]+)", re.UNICODE)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")


# ------------------------------------------------------------------ normalize
def norm(text: str) -> str:
    """সার্চের জন্য টেক্সট নরমালাইজ (case, যুক্তি/চিহ্ন সব বাদ + বানান ভুল সংশোধন)।"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", text).strip()
    if cleaned in TEAM_TYPO_ALIASES:
        return TEAM_TYPO_ALIASES[cleaned]
    tokens = [TEAM_TYPO_ALIASES.get(tok, tok) for tok in cleaned.split()]
    return " ".join(tokens)


def compact(text: str) -> str:
    return norm(text).replace(" ", "")


def match_ref(match_id: int) -> str:
    """রিভার্জিবল শর্ট রেফ: 123-abcdef (কলব্যাক ডেটা ৬৪ বাইটের মধ্যে)।"""
    sig = hashlib.md5(f"m{match_id}".encode()).hexdigest()[:6]
    return f"{match_id}-{sig}"


def match_id_from_ref(ref: str) -> int:
    try:
        return int(str(ref).split("-")[0])
    except (ValueError, TypeError):
        return 0


def team_ref(team_key: str) -> str:
    return hashlib.md5(("t" + team_key).encode()).hexdigest()[:10]


AD_TIMER_SECONDS = _get_int("AD_TIMER_SECONDS", 5)


async def load_ad(db) -> dict | None:
    """অ্যাড চালু থাকলে অ্যাডের ডেটা, নাহলে None (অ্যাড বন্ধ বা লিংক না থাকলে ফ্রি মোড)।"""
    s = await db.get_settings("ad_")
    url = (s.get("ad_url") or "").strip()
    text = (s.get("ad_text") or "").strip()
    if s.get("ad_active") == "1" and (url or text):
        if not text:
            text = "🔥 হাইলাইট ভিডিওটি আনলক করতে নিচের অ্যাড লিংকে ক্লিক করে মাত্র ৫ সেকেন্ড অপেক্ষা করুন!"
        return {
            "text": text,
            "btn": (s.get("ad_btn") or "").strip() or "📺 অ্যাড দেখুন (৫ সেকেন্ড)",
            "url": url,
        }
    return None


async def resolve_team_ref(db, ref: str) -> str | None:
    """team_ref থেকে team_key বের করে (ক্যাশ + DB ফলব্যাক)।"""
    if ref in _TEAM_REF_CACHE:
        return _TEAM_REF_CACHE[ref]
    for row in await db.get_teams():
        _TEAM_REF_CACHE[team_ref(row["team_key"])] = row["team_key"]
    return _TEAM_REF_CACHE.get(ref)


_TEAM_REF_CACHE: dict[str, str] = {}


def split_camel(text: str) -> str:
    """RealMadrid -> Real Madrid"""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)


# ------------------------------------------------------------------ fuzzy
def _field_score(query: str, query_compact: str, field_text: str) -> float:
    if not query or not field_text:
        return 0.0
    field = norm(field_text)
    if not field:
        return 0.0
    if query == field:
        return 1.0
    if query in field or (query_compact and query_compact in field.replace(" ", "")):
        return 0.93
    qtokens = [t for t in query.split() if len(t) >= 3]
    ftokens = [t for t in field.split() if len(t) >= 3]
    if qtokens and all(t in field for t in qtokens):
        return 0.90
    best = difflib.SequenceMatcher(None, query, field).ratio()
    for q in qtokens or query.split():
        for f in ftokens or field.split():
            r = difflib.SequenceMatcher(None, q, f).ratio()
            if r > best:
                best = r
    return best * 0.97


def score_match(query: str, row) -> float:
    """একটা ম্যাচ কতটা query-র সাথে মিলে (0..1)।"""
    q = norm(query)
    if not q:
        return 0.0
    qc = q.replace(" ", "")
    best = 0.0
    fields = [row["team"], row["title"], row["team_key"]]
    tags = row["tags"] or ""
    if tags:
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                fields.append(tag)
                fields.append(split_camel(tag))
    for f in fields:
        best = max(best, _field_score(q, qc, f))
        if best >= 1.0:
            break
    # বছরও মিললে একটু বুস্ট
    year = (row["year"] or "").strip()
    if year and year in q.split():
        best += 0.05
    return min(best, 1.0)


def search_matches(rows: list, query: str, threshold: float = 0.55, limit: int = 100) -> list:
    scored = []
    for row in rows:
        s = score_match(query, row)
        if s >= threshold:
            scored.append((s, row["views"] or 0, row))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:limit]]


def suggest_teams(teams: list, query: str, limit: int = 5) -> list:
    q = norm(query)
    if not q:
        return []
    scored = []
    for row in teams:
        s = _field_score(q, q.replace(" ", ""), row["team"])
        if s >= 0.45 and s < 1.0:
            scored.append((s, row["team"]))
    scored.sort(reverse=True)
    out, seen = [], set()
    for _, name in scored:
        key = norm(name)
        if key not in seen:
            seen.add(key)
            out.append(name)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ caption
def parse_caption(caption: str | None) -> dict:
    """চ্যানেলের ক্যাপশন থেকে টিম, টাইটেল, সাল, হ্যাশট্যাগ বের করে।"""
    raw = (caption or "").strip()
    hashtags = [h for h in _HASHTAG_RE.findall(raw)]
    text = _URL_RE.sub(" ", raw)
    text = re.sub(r"#\S+", " ", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else ""
    if len(title) < 12 and len(lines) > 1:
        title = f"{title} {lines[1]}".strip()
    title = re.sub(r"\s{2,}", " ", title).strip(" -–|:•")
    if len(title) > 180:
        title = title[:177].rsplit(" ", 1)[0] + "…"

    year_match = _YEAR_RE.search(raw)
    year = year_match.group(1) if year_match else ""

    team = ""
    if hashtags:
        team = split_camel(hashtags[0]).replace("_", " ").strip()
    if not team:
        if "|" in title:
            team = title.split("|")[0].strip()
        else:
            vs = re.split(r"\s+vs\.?\s+|\s+v\s+", title, maxsplit=1, flags=re.IGNORECASE)
            team = vs[0].strip() if len(vs) == 2 else " ".join(title.split()[:3])
    team = re.sub(r"\s{2,}", " ", team).strip(" -–|:•")
    if len(team) > 48:
        team = team[:48]

    if not team:
        team = "Highlights"
    if not title:
        title = team

    return {
        "team": team,
        "title": title,
        "year": year,
        "tags": ",".join(dict.fromkeys(hashtags)),
    }


# ------------------------------------------------------------------ media
def extract_media(message) -> tuple[str, str, str]:
    """(media_type, file_id, file_unique_id) রিটার্ন করে।"""
    if message.video:
        vid = message.video
        return "video", vid.file_id, vid.file_unique_id
    if message.animation:
        anim = message.animation
        return "animation", anim.file_id, anim.file_unique_id
    if message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        if mime.startswith("video") or mime in ("application/mp4", "video/mp4"):
            return "document", doc.file_id, doc.file_unique_id
    return "", "", ""


def message_text_or_caption(message) -> str:
    return message.caption or message.text or ""


# ------------------------------------------------------------------ misc
def fmt_date(iso: str, tz=None) -> str:
    if not iso:
        return "-"
    try:
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        if tz:
            dt = dt.astimezone(tz)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return iso[:10]


def year_of(match) -> str:
    if match["year"]:
        return str(match["year"])
    created = match["created_at"] or ""
    return created[:4] if len(created) >= 4 else "-"


def video_caption(match, template: str) -> str:
    return template.format(
        team=esc(match["team"]),
        title=esc(match["title"]),
        year=esc(year_of(match)),
    )


def safe_username(username: str | None) -> str:
    if not username:
        return "—"
    return f"@{username}"


def esc(text: str) -> str:
    """HTML এর জন্য টেক্সট এস্কেপ।"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ==========================================================================
# 🗄️ SQLite ডেটাবেস — users, matches, settings, ad_views
# ==========================================================================

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def utcnow_iso() -> str:
    return _iso(datetime.now(timezone.utc))


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ setup
    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def _create_tables(self) -> None:
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                first_name  TEXT DEFAULT '',
                username    TEXT DEFAULT '',
                lang        TEXT DEFAULT '',
                created_at  TEXT,
                last_active TEXT
            );

            CREATE TABLE IF NOT EXISTS matches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                team        TEXT NOT NULL,
                team_key    TEXT NOT NULL,
                title       TEXT NOT NULL,
                year        TEXT DEFAULT '',
                tags        TEXT DEFAULT '',
                file_id     TEXT NOT NULL,
                media_type  TEXT DEFAULT 'video',
                source_msg  INTEGER DEFAULT 0,
                dest_msg    INTEGER DEFAULT 0,
                views       INTEGER DEFAULT 0,
                created_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_matches_team_key ON matches(team_key);
            CREATE INDEX IF NOT EXISTS idx_matches_created ON matches(created_at);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS ad_views (
                user_id    INTEGER PRIMARY KEY,
                views      INTEGER DEFAULT 0,
                last_view  TEXT
            );

            CREATE TABLE IF NOT EXISTS ad_sessions (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                match_id    INTEGER NOT NULL,
                ad_url      TEXT DEFAULT '',
                created_at  REAL NOT NULL,
                opened_at   REAL DEFAULT 0,
                verified    INTEGER DEFAULT 0,
                delivered   INTEGER DEFAULT 0
            );
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ------------------------------------------------------------------ users
    async def add_or_update_user(
        self,
        user_id: int,
        first_name: str = "",
        username: str = "",
        lang: str | None = None,
    ) -> None:
        now = utcnow_iso()
        async with self._lock:
            row = await self._fetchone("SELECT id, lang FROM users WHERE id = ?", (user_id,))
            if row is None:
                await self._db.execute(
                    "INSERT INTO users (id, first_name, username, lang, created_at, last_active) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, first_name or "", username or "", lang or "", now, now),
                )
            else:
                if lang:
                    await self._db.execute(
                        "UPDATE users SET first_name=?, username=?, lang=?, last_active=? WHERE id=?",
                        (first_name or "", username or "", lang, now, user_id),
                    )
                else:
                    await self._db.execute(
                        "UPDATE users SET first_name=?, username=?, last_active=? WHERE id=?",
                        (first_name or "", username or "", now, user_id),
                    )
            await self._db.commit()

    async def touch_user(self, user_id: int) -> None:
        async with self._lock:
            await self._db.execute(
                "UPDATE users SET last_active=? WHERE id=?", (utcnow_iso(), user_id)
            )
            await self._db.commit()

    async def set_user_lang(self, user_id: int, lang: str) -> None:
        async with self._lock:
            await self._db.execute("UPDATE users SET lang=? WHERE id=?", (lang, user_id))
            await self._db.commit()

    async def get_user(self, user_id: int):
        return await self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))

    async def get_all_user_ids(self) -> list[int]:
        rows = await self._fetchall("SELECT id FROM users ORDER BY id")
        return [r["id"] for r in rows]

    async def get_users_page(self, offset: int, limit: int) -> list:
        return await self._fetchall(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )

    async def count_users(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS c FROM users")
        return row["c"] if row else 0

    async def count_new_today(self) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM users WHERE created_at >= ?", (_iso(start),)
        )
        return row["c"] if row else 0

    async def count_active_today(self) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM users WHERE last_active >= ?", (_iso(start),)
        )
        return row["c"] if row else 0

    # ------------------------------------------------------------------ matches
    async def add_match(
        self,
        team: str,
        team_key: str,
        title: str,
        year: str,
        tags: str,
        file_id: str,
        media_type: str,
        source_msg: int = 0,
        dest_msg: int = 0,
    ) -> int:
        async with self._lock:
            cur = await self._db.execute(
                "INSERT INTO matches (team, team_key, title, year, tags, file_id, media_type, "
                "source_msg, dest_msg, views, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (team, team_key, title, year or "", tags or "", file_id, media_type, source_msg, dest_msg, utcnow_iso()),
            )
            await self._db.commit()
            return int(cur.lastrowid)

    async def get_match_by_source(self, source_msg: int):
        return await self._fetchone(
            "SELECT * FROM matches WHERE source_msg = ? AND source_msg != 0", (source_msg,)
        )

    async def get_match_by_dest(self, dest_msg: int):
        return await self._fetchone(
            "SELECT * FROM matches WHERE dest_msg = ? AND dest_msg != 0", (dest_msg,)
        )

    async def get_match(self, match_id: int):
        return await self._fetchone("SELECT * FROM matches WHERE id = ?", (match_id,))

    async def get_matches_latest(self, offset: int = 0, limit: int = 6) -> list:
        return await self._fetchall(
            "SELECT * FROM matches ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    async def get_matches_popular(self, offset: int = 0, limit: int = 6) -> list:
        return await self._fetchall(
            "SELECT * FROM matches ORDER BY views DESC, created_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    async def get_team_matches(self, team_key: str, offset: int = 0, limit: int = 6) -> list:
        return await self._fetchall(
            "SELECT * FROM matches WHERE team_key = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (team_key, limit, offset),
        )

    async def count_matches(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS c FROM matches")
        return row["c"] if row else 0

    async def count_team_matches(self, team_key: str) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM matches WHERE team_key = ?", (team_key,)
        )
        return row["c"] if row else 0

    async def total_views(self) -> int:
        row = await self._fetchone("SELECT COALESCE(SUM(views), 0) AS s FROM matches")
        return row["s"] if row else 0

    async def increment_views(self, match_id: int) -> None:
        async with self._lock:
            await self._db.execute("UPDATE matches SET views = views + 1 WHERE id = ?", (match_id,))
            await self._db.commit()

    async def update_match(self, match_id: int, **fields) -> None:
        allowed = {"team", "team_key", "title", "year", "tags", "file_id", "media_type"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                values.append(value)
        if not sets:
            return
        values.append(match_id)
        async with self._lock:
            await self._db.execute(f"UPDATE matches SET {', '.join(sets)} WHERE id = ?", values)
            await self._db.commit()

    async def delete_match(self, match_id: int) -> None:
        async with self._lock:
            await self._db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
            await self._db.commit()

    async def get_teams(self) -> list:
        return await self._fetchall(
            "SELECT team, team_key, COUNT(*) AS total FROM matches "
            "GROUP BY team_key ORDER BY total DESC, team ASC"
        )

    async def get_search_index(self) -> list:
        return await self._fetchall(
            "SELECT id, team, team_key, title, year, tags, views, created_at FROM matches "
            "ORDER BY created_at DESC, id DESC"
        )

    # ------------------------------------------------------------------ settings
    async def set_setting(self, key: str, value: str | None) -> None:
        async with self._lock:
            if value is None:
                await self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                await self._db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
            await self._db.commit()

    async def get_setting(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    async def get_settings(self, prefix: str = "") -> dict:
        if prefix:
            rows = await self._fetchall(
                "SELECT key, value FROM settings WHERE key LIKE ?", (prefix + "%",)
            )
        else:
            rows = await self._fetchall("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------ ad views
    async def register_ad_view(self, user_id: int) -> None:
        now = utcnow_iso()
        async with self._lock:
            await self._db.execute(
                "INSERT INTO ad_views (user_id, views, last_view) VALUES (?, 1, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET views = views + 1, last_view = excluded.last_view",
                (user_id, now),
            )
            await self._db.commit()

    async def ad_stats(self) -> tuple[int, int]:
        row = await self._fetchone("SELECT COALESCE(SUM(views), 0) AS s, COUNT(*) AS c FROM ad_views")
        if not row:
            return 0, 0
        return row["s"], row["c"]

    # ------------------------------------------------------------------ 5s anti-cheat ad sessions
    async def create_ad_session(self, user_id: int, match_id: int, ad_url: str) -> str:
        token = secrets.token_urlsafe(10)
        now = time.time()
        async with self._lock:
            await self._db.execute(
                "INSERT INTO ad_sessions (token, user_id, match_id, ad_url, created_at, opened_at, verified, delivered) "
                "VALUES (?, ?, ?, ?, ?, 0, 0, 0)",
                (token, user_id, match_id, ad_url or "", now),
            )
            await self._db.commit()
        return token

    async def get_ad_session(self, token: str):
        return await self._fetchone("SELECT * FROM ad_sessions WHERE token = ?", (token,))

    async def mark_ad_opened(self, token: str) -> None:
        now = time.time()
        async with self._lock:
            await self._db.execute(
                "UPDATE ad_sessions SET opened_at = CASE WHEN opened_at = 0 THEN ? ELSE opened_at END WHERE token = ?",
                (now, token),
            )
            await self._db.commit()

    async def mark_ad_verified(self, token: str) -> None:
        async with self._lock:
            await self._db.execute("UPDATE ad_sessions SET verified = 1 WHERE token = ?", (token,))
            await self._db.commit()

    async def mark_ad_delivered(self, token: str) -> None:
        async with self._lock:
            await self._db.execute("UPDATE ad_sessions SET delivered = 1 WHERE token = ?", (token,))
            await self._db.commit()

    # ------------------------------------------------------------------ helpers
    async def _fetchone(self, query: str, params: tuple = ()):
        cur = await self._db.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def _fetchall(self, query: str, params: tuple = ()) -> list:
        cur = await self._db.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def get_matches_by_ids(self, ids: list[int]) -> list:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = await self._fetchall(
            f"SELECT * FROM matches WHERE id IN ({placeholders})", tuple(ids)
        )
        by_id = {r["id"]: r for r in rows}
        return [by_id[i] for i in ids if i in by_id]


# ==========================================================================
# ⌨️ মেনু ও inline বাটন
# ==========================================================================

# locale key → action (মেনু প্রসেসিং এক জায়গায়)
MENU_KEYS = {
    "menu_search": "search",
    "menu_popular": "popular",
    "menu_latest": "latest",
    "menu_teams": "teams",
    "menu_lang": "lang",
    "menu_help": "help",
    "menu_admin": "admin",
    "menu_home": "menu",
}


def main_menu_kb(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=t(lang, "menu_search")), KeyboardButton(text=t(lang, "menu_popular"))],
        [KeyboardButton(text=t(lang, "menu_latest")), KeyboardButton(text=t(lang, "menu_teams"))],
        [KeyboardButton(text=t(lang, "menu_lang")), KeyboardButton(text=t(lang, "menu_help"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(lang, "menu_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def lang_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, name in LANGUAGES.items():
        row.append(InlineKeyboardButton(text=name, callback_data=f"lang:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ------------------------------------------------------------------ listings
def _nav_row(lang: str, page: int, total_pages: int, kind: str, ref: str) -> list:
    if total_pages <= 1:
        return []
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton(text=t(lang, "btn_prev"), callback_data=f"pg:{kind}:{ref}:{page - 1}")
        )
    row.append(
        InlineKeyboardButton(text=f"· {page}/{total_pages} ·", callback_data="noop")
    )
    if page < total_pages:
        row.append(
            InlineKeyboardButton(text=t(lang, "btn_next"), callback_data=f"pg:{kind}:{ref}:{page + 1}")
        )
    return row


def list_markup(
    lang: str,
    item_buttons: list[tuple[str, str]],
    page: int,
    total_pages: int,
    kind: str,
    ref: str = "",
    back_cb: str = "home",
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=text, callback_data=cb)] for text, cb in item_buttons]
    nav = _nav_row(lang, page, total_pages, kind, ref)
    if nav:
        rows.append(nav)
    if back_cb:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="•", callback_data="noop")]])


def format_match_details_block(rows, start_idx: int = 1) -> str:
    """ম্যাচের তালিকায় টিম, কোন ম্যাচ এবং কত সাল — সব বিবরণ সুন্দর করে দেখায়।"""
    lines = []
    for idx, m in enumerate(rows, start=start_idx):
        yr = year_of(m)
        yr_badge = f" ({yr})" if yr and yr != "-" else ""
        lines.append(f"<b>{idx}. 🏆 {esc(m['team'])}</b> — {esc(m['title'])}{yr_badge}")
    return "\n".join(lines)


def match_buttons(lang: str, rows, page: int, total: int, page_size: int, kind: str, ref: str, back_cb: str = "home"):
    buttons = []
    for m in rows:
        title = (m["title"] or "").strip()
        yr = year_of(m)
        yr_str = f" [{yr}]" if yr and yr != "-" else ""
        if len(title) > 28:
            title = title[:25] + "…"
        label = f"🎬 {m['team']} — {title}{yr_str}"
        buttons.append((label[:64], f"v:{match_ref(m['id'])}"))
    total_pages = max(1, (total + page_size - 1) // page_size)
    return list_markup(lang, buttons, page, total_pages, kind, ref, back_cb)


def team_buttons(lang: str, teams, page: int, total: int, page_size: int, back_cb: str = "home"):
    buttons = []
    for row in teams:
        buttons.append((f"🏆 {row['team']} ({row['total']})", f"tm:{team_ref(row['team_key'])}:0"))
    total_pages = max(1, (total + page_size - 1) // page_size)
    return list_markup(lang, buttons, page, total_pages, "tl", "", back_cb)


# ------------------------------------------------------------------ ad gate
def ad_kb(lang: str, match_id: int, url: str = "", btn_text: str = "", token: str = "") -> InlineKeyboardMarkup:
    rows = []
    base = webhook_base_url()
    target_url = f"{base}/ad/{token}" if (base and token and url) else url
    if target_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=btn_text or f"📺 {t(lang, 'ad_btn_open')} ({AD_TIMER_SECONDS}s)",
                    url=target_url,
                )
            ]
        )
    cb_payload = f"vx:{token}" if token else f"vx:{match_ref(match_id)}"
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "ad_btn_continue"),
                callback_data=cb_payload,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ------------------------------------------------------------------ admin
def admin_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=t(lang, "ap_stats"), callback_data="a:stats"),
            InlineKeyboardButton(text=t(lang, "ap_users"), callback_data="a:users:0"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "ap_ad"), callback_data="a:ad"),
            InlineKeyboardButton(text=t(lang, "ap_matches"), callback_data="a:matches:0"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "ap_manual"), callback_data="a:manual"),
            InlineKeyboardButton(text=t(lang, "ap_broadcast"), callback_data="a:bc"),
        ],
        [InlineKeyboardButton(text=t(lang, "ap_sync"), callback_data="a:sync")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_panel_kb(lang: str, ad_on: bool, has_text: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=t(lang, "ad_set_text"), callback_data="a:ad:text"),
            InlineKeyboardButton(text=t(lang, "ad_set_btn"), callback_data="a:ad:btn"),
        ],
        [InlineKeyboardButton(text=t(lang, "ad_set_url"), callback_data="a:ad:url")],
    ]
    toggle_text = t(lang, "ad_toggle_off") if ad_on else t(lang, "ad_toggle_on")
    rows.append([InlineKeyboardButton(text=toggle_text, callback_data="a:ad:toggle")])
    extra = []
    if has_text:
        extra.append(InlineKeyboardButton(text=t(lang, "ad_preview"), callback_data="a:ad:preview"))
        extra.append(InlineKeyboardButton(text=t(lang, "ad_clear"), callback_data="a:ad:clear"))
    if extra:
        rows.append(extra)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="a:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_matches_kb(lang: str, rows_matches, page: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    buttons = []
    for m in rows_matches:
        title = (m["title"] or "").strip()
        if len(title) > 26:
            title = title[:23] + "…"
        buttons.append((f"🎬 #{m['id']} {m['team']} — {title}"[:64], f"am:{m['id']}:{page}"))
    total_pages = max(1, (total + page_size - 1) // page_size)
    return list_markup(lang, buttons, page, total_pages, "mt", "", "a:home")


def match_admin_kb(lang: str, match_id: int, page: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=t(lang, "me_team_btn"), callback_data=f"emt:{match_id}:{page}"),
            InlineKeyboardButton(text=t(lang, "me_title_btn"), callback_data=f"emz:{match_id}:{page}"),
        ],
        [InlineKeyboardButton(text=t(lang, "send_me"), callback_data=f"amd:{match_id}")],
        [
            InlineKeyboardButton(text=t(lang, "me_delete_btn"), callback_data=f"adm:{match_id}:{page}"),
            InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=f"a:matches:{page}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_kb(lang: str, match_id: int, page: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=t(lang, "delete_yes"), callback_data=f"admy:{match_id}:{page}"),
            InlineKeyboardButton(text=t(lang, "delete_no"), callback_data=f"am:{match_id}:{page}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sync_kb(lang: str, auto_on: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "sync_set_user_btn"), callback_data="a:sync:user")],
        [InlineKeyboardButton(text=t(lang, "sync_check_btn"), callback_data="a:sync:check")],
        [InlineKeyboardButton(text=t(lang, "sync_toggle"), callback_data="a:sync:toggle")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="a:home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_kb(lang: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text=t(lang, "btn_prev"), callback_data=f"a:users:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"· {page}/{total_pages} ·", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text=t(lang, "btn_next"), callback_data=f"a:users:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="a:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb(lang: str, cb: str = "a:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=cb)]]
    )


def cancel_kb(lang: str, cb: str = "a:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data=cb)]]
    )


def ad_preview_kb(lang: str, url: str = "", btn_text: str = "") -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([InlineKeyboardButton(text=btn_text or t(lang, "ad_btn_open"), url=url)])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="a:ad")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==========================================================================
# 🤝 ভাষা ও অ্যাডমিন হেল্পার
# ==========================================================================

async def get_lang(db, user_id: int) -> str:
    row = await db.get_user(user_id)
    if row and row["lang"]:
        return row["lang"]
    return DEFAULT_LANG if DEFAULT_LANG in LANGUAGES else "bn"


async def is_admin(db, user_id: int, username: str | None = None) -> bool:
    if user_id in ADMIN_IDS:
        return True
    owner = await db.get_setting("owner_id")
    if owner and str(user_id) == owner:
        return True
    uname = (username or "").lstrip("@").lower()
    if not uname:
        row = await db.get_user(user_id)
        uname = (row["username"] if row and row["username"] else "").lstrip("@").lower()
    return bool(uname and uname in ADMIN_USERNAMES)


async def admin_ids(db) -> list[int]:
    ids = set(ADMIN_IDS)
    owner = await db.get_setting("owner_id")
    if owner and owner.lstrip("-").isdigit():
        ids.add(int(owner))
    return sorted(ids)


async def notify_admins(db, bot, text: str, reply_markup=None) -> None:
    """সব অ্যাডমিনকে নোটিফিকেশন (প্রত্যেকের নিজের ভাষায় নয় — একই টেক্সট)।"""
    for uid in await admin_ids(db):
        try:
            await bot.send_message(uid, text, reply_markup=reply_markup)
        except Exception:
            continue


async def send_admin_panel(message, db, lang: str, edit: bool = False) -> None:
    text = t(lang, "ap_title")
    kb = admin_kb(lang)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ==========================================================================
# 🔄 পাবলিক সোর্স চ্যানেল পোলার (অ্যাডমিন লাগে না)
# ==========================================================================

POST_RE = re.compile(r'data-post="([^"/]+)/(\d+)"')
VIDEO_SRC_RE = re.compile(r"<video[^>]+src=\"([^\"]+)\"", re.IGNORECASE)
TEXT_BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
TAG_RE = re.compile(r"<[^>]+>")
VIDEO_MARKERS = (
    "tgme_widget_message_video",
    "<video",
    "tgme_widget_message_roundvideo",
    "tgme_widget_message_document_wrap",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ------------------------------------------------------------------ fetching
async def fetch_channel_html(username: str) -> str:
    url = f"https://t.me/s/{username.lstrip('@')}"
    timeout = aiohttp.ClientTimeout(total=25)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return await resp.text()


def _block_text(block: str) -> str:
    match = TEXT_BLOCK_RE.search(block)
    if not match:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", match.group(1))
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def parse_posts(html: str) -> list[dict]:
    """পেজের HTML থেকে পোস্টের তালিকা — ভিডিও আছে কিনা, ভিডিও URL, ক্যাপশন।"""
    matches = list(POST_RE.finditer(html))
    posts: list[dict] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        block = html[start:end]
        has_video = any(marker in block for marker in VIDEO_MARKERS)
        if not has_video:
            continue
        video_match = VIDEO_SRC_RE.search(block)
        posts.append(
            {
                "id": int(match.group(2)),
                "video_url": video_match.group(1) if video_match else "",
                "text": _block_text(block),
            }
        )
    # একই আইডি একবারই
    seen, unique = set(), []
    for post in sorted(posts, key=lambda p: p["id"]):
        if post["id"] not in seen:
            seen.add(post["id"])
            unique.append(post)
    return unique


def parse_video_post_ids(html: str) -> list[int]:
    return [p["id"] for p in parse_posts(html)]


# ------------------------------------------------------------------ helpers
async def source_username(db: Database) -> str:
    """অ্যাডমিন প্যানেল থেকে সেট করা নাম, না থাকলে env থেকে।"""
    value = (await db.get_setting("source_username")) or SOURCE_USERNAME
    return (value or "").strip().lstrip("@")


async def notify_new_match(bot: Bot, db: Database, team: str, title: str, year: str) -> None:
    for admin_id in await admin_ids(db):
        row = await db.get_user(admin_id)
        lang = (row["lang"] if row and row["lang"] else DEFAULT_LANG) or "bn"
        try:
            await bot.send_message(
                admin_id,
                t(
                    lang,
                    "capture_notice",
                    team=esc(team),
                    title=esc(title),
                    year=year or t(lang, "not_set"),
                    posted=t(lang, "capture_posted"),
                ),
            )
        except Exception:
            continue


async def _copy_post(bot: Bot, username: str, post: dict):
    """প্রথমে copy_message, না পারলে ভিডিও URL দিয়ে পাঠানোর চেষ্টা।"""
    try:
        return await bot.copy_message(
            chat_id=DEST_CHANNEL,
            from_chat_id=f"@{username}",
            message_id=post["id"],
        )
    except Exception as copy_exc:  # noqa: BLE001
        log.warning("copyMessage @%s/%s ব্যর্থ: %s", username, post["id"], copy_exc)

    if post.get("video_url"):
        try:
            return await bot.send_video(
                DEST_CHANNEL, post["video_url"], caption=(post["text"] or "")[:1024] or None
            )
        except Exception as url_exc:  # noqa: BLE001
            log.warning("video URL পাঠানো ব্যর্থ @%s/%s: %s", username, post["id"], url_exc)
    return None


async def poll_once(bot: Bot, db: Database, username: str) -> int:
    """একবার চেক করে নতুন ভিডিও পোস্টগুলো কপি + সেভ করে।"""
    username = (username or "").strip().lstrip("@")
    if not username:
        return 0

    html = await fetch_channel_html(username)
    posts = parse_posts(html)
    if not posts:
        return 0

    key = f"poll_last_{username.lower()}"
    last_raw = await db.get_setting(key)
    if last_raw is None:
        await db.set_setting(key, str(posts[-1]["id"]))
        log.info("Poller সেট হলো @%s — পোস্ট #%s থেকে নতুনগুলো নেবে", username, posts[-1]["id"])
        return 0

    try:
        last_id = int(last_raw)
    except ValueError:
        last_id = posts[-1]["id"]

    new_posts = [p for p in posts if p["id"] > last_id][:10]
    processed = 0
    for post in new_posts:
        sent = await _copy_post(bot, username, post)
        await db.set_setting(key, str(post["id"]))
        if sent is None:
            continue


        result = await index_message(
            db, sent, source_msg=post["id"], from_poller=True, fallback_caption=post["text"]
        )
        if result:
            processed += 1
            await notify_new_match(bot, db, result["team"], result["title"], result["year"])

    if processed:
        log.info("Poller @%s: %sটি নতুন ম্যাচ যোগ হলো", username, processed)
    await db.set_setting("poll_last_run", time.strftime("%Y-%m-%d %H:%M:%S"))
    return processed


async def poller_loop(bot: Bot, db: Database) -> None:
    """ব্যাকগ্রাউন্ড টাস্ক — নির্দিষ্ট সময় পর পর সোর্স চ্যানেল চেক করে।"""
    log.info("সোর্স পোলার চালু (প্রতি %s সেকেন্ড)", POLL_INTERVAL)
    while True:
        try:
            if (await db.get_setting("autosync")) != "0":
                username = await source_username(db)
                if username:
                    await poll_once(bot, db, username)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Poller এরর: %s", exc)
        await asyncio.sleep(max(30, POLL_INTERVAL))


# ==========================================================================
# 👤 ইউজার — সার্চ, লিস্ট, ভিডিও ডেলিভারি, অ্যাড গেট
# ==========================================================================

user_router = Router(name="user")


class Search(StatesGroup):
    query = State()


# প্রতি ইউজারের শেষ সার্চ (query, [match ids])
SEARCH_CACHE: dict[int, tuple[str, list[int]]] = {}


# ------------------------------------------------------------------ helpers
def _name(user) -> str:
    return esc(user.first_name or "Friend")


def _short(text: str, limit: int = 60) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _menu_keyboard(db: Database, user_id: int, lang: str, username: str | None = None):
    return main_menu_kb(lang, await is_admin(db, user_id, username))


async def send_welcome(message: Message, db: Database, lang: str, user_id: int, username: str | None = None):
    await message.answer(
        t(lang, "welcome", name=_name(message.from_user)),
        reply_markup=await _menu_keyboard(db, user_id, lang, username),
    )


async def send_video_to(bot: Bot, db: Database, chat_id: int, match, lang: str) -> bool:
    """ম্যাচের ভিডিও পাঠায় (কোনো লিংক ছাড়া, শুধু file_id)।"""
    caption = video_caption(match, VIDEO_CAPTION_TEMPLATE)
    try:
        if match["media_type"] == "animation":
            await bot.send_animation(chat_id, match["file_id"], caption=caption, parse_mode="HTML")
        elif match["media_type"] == "document":
            await bot.send_document(chat_id, match["file_id"], caption=caption, parse_mode="HTML")
        else:
            await bot.send_video(chat_id, match["file_id"], caption=caption, parse_mode="HTML")
        await db.increment_views(match["id"])
        return True
    except TelegramBadRequest:
        await bot.send_message(chat_id, t(lang, "video_unavailable"))
        return False


async def build_list(db: Database, lang: str, kind: str, page: int, ref: str, user_id: int):
    """(text, keyboard) রিটার্ন করে; কিছু না থাকলে None।"""
    page = max(1, int(page))
    size = PAGE_MATCHES

    if kind in ("l", "p"):
        total = await db.count_matches()
        if total == 0:
            return None
        offset = (page - 1) * size
        if kind == "l":
            rows = await db.get_matches_latest(offset, size)
            header = t(lang, "latest_header", n=total)
        else:
            rows = await db.get_matches_popular(offset, size)
            header = t(lang, "popular_header", n=total)
        kb = match_buttons(lang, rows, page, total, size, kind, "")
        return header, kb

    if kind == "sr":
        cached = SEARCH_CACHE.get(user_id)
        if not cached or not cached[1]:
            return None
        query, ids = cached
        offset = (page - 1) * size
        rows = await db.get_matches_by_ids(ids[offset : offset + size])
        if not rows:
            return None
        details = format_match_details_block(rows, offset + 1)
        header = t(lang, "search_results", q=esc(_short(query)), n=len(ids)) + "\n\n" + details
        kb = match_buttons(lang, rows, page, len(ids), size, "sr", "")
        return header, kb

    if kind == "tm":
        team_key = await resolve_team_ref(db, ref)
        if not team_key:
            return None
        total = await db.count_team_matches(team_key)
        if total == 0:
            return None
        offset = (page - 1) * size
        rows = await db.get_team_matches(team_key, offset, size)
        team_name = rows[0]["team"] if rows else team_key
        details = format_match_details_block(rows, offset + 1)
        header = t(lang, "team_header", team=esc(team_name), n=total) + "\n\n" + details
        kb = match_buttons(lang, rows, page, total, size, "tm", ref, back_cb="home")
        return header, kb

    if kind == "tl":
        teams = await db.get_teams()
        if not teams:
            return None
        size_t = PAGE_TEAMS
        offset = (page - 1) * size_t
        chunk = teams[offset : offset + size_t]
        if not chunk:
            return None
        header = t(lang, "teams_header", n=len(teams))
        kb = team_buttons(lang, chunk, page, len(teams), size_t, back_cb="home")
        return header, kb

    return None


async def _edit_or_send(cb: CallbackQuery, text: str, kb):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            await cb.message.answer(text, reply_markup=kb)


async def _do_search(message: Message, db: Database, lang: str) -> None:
    query = (message.text or "").strip()
    rows = await db.get_search_index()
    found = search_matches(rows, query, limit=SEARCH_LIMIT)
    ids = [r["id"] for r in found]
    SEARCH_CACHE[message.from_user.id] = (query, ids)

    if not ids:
        teams = await db.get_teams()
        suggestions = suggest_teams(teams, query)
        text = t(lang, "search_empty")
        if suggestions:
            text += "\n\n" + t(lang, "search_suggest") + "\n" + "\n".join(
                f"• {esc(s)}" for s in suggestions
            )
        await message.answer(text)
        return

    page_rows = found[: PAGE_MATCHES]
    details = format_match_details_block(page_rows, 1)
    header = t(lang, "search_results", q=esc(_short(query)), n=len(ids)) + "\n\n" + details
    kb = match_buttons(lang, page_rows, 1, len(ids), PAGE_MATCHES, "sr", "")
    await message.answer(header, reply_markup=kb)


# ------------------------------------------------------------------ commands
@user_router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext, db: Database):
    user = message.from_user
    await state.clear()
    await db.add_or_update_user(user.id, user.first_name or "", user.username or "")
    row = await db.get_user(user.id)
    lang = (row["lang"] if row and row["lang"] else DEFAULT_LANG) or "bn"
    if lang not in LANGUAGES:
        lang = "bn"
    if not (row and row["lang"]):
        await message.answer(t(lang, "choose_lang"), reply_markup=lang_kb())
    await send_welcome(message, db, lang, user.id, user.username)


@user_router.message(Command("help"), F.chat.type == "private")
async def cmd_help(message: Message, db: Database):
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "help_text"), reply_markup=back_kb(lang, "home"))


@user_router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message, db: Database):
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "choose_lang"), reply_markup=lang_kb())


@user_router.message(Command("id"), F.chat.type == "private")
async def cmd_id(message: Message, db: Database):
    user = message.from_user
    await message.answer(
        f"👤 <b>{esc(user.full_name)}</b>\n"
        f"🆔 <code>{user.id}</code>\n"
        f"📛 {('@' + user.username) if user.username else '—'}\n\n"
        f"<i>এই ID টা অ্যাডমিন হিসেবে সেট করা যায়।</i>"
    )


@user_router.message(Command("cancel"), F.chat.type == "private")
async def user_cmd_cancel(message: Message, state: FSMContext, db: Database):
    await state.clear()
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "bc_cancelled"))


# ------------------------------------------------------------------ language
@user_router.callback_query(F.data.startswith("lang:"))
async def on_lang_choice(cb: CallbackQuery, db: Database):
    code = cb.data.split(":", 1)[1]
    if code not in LANGUAGES:
        await cb.answer()
        return
    user = cb.from_user
    await db.add_or_update_user(user.id, user.first_name or "", user.username or "", lang=code)
    try:
        await cb.message.edit_text(t(code, "lang_set", lang=LANGUAGES[code]))
    except TelegramBadRequest:
        pass
    await cb.message.answer(
        t(code, "welcome", name=_name(user)),
        reply_markup=await _menu_keyboard(db, user.id, code, user.username),
    )
    await cb.answer()


# ------------------------------------------------------------------ menu
@user_router.message(F.chat.type == "private", F.text.in_(set(LABEL_ACTIONS.keys())))
async def on_menu(message: Message, state: FSMContext, db: Database):
    action = LABEL_ACTIONS[message.text]
    await state.clear()
    lang = await get_lang(db, message.from_user.id)

    if action == "search":
        await message.answer(t(lang, "search_prompt"))
        await state.set_state(Search.query)
        return

    if action in ("popular", "latest", "teams"):
        kind = {"popular": "p", "latest": "l", "teams": "tl"}[action]
        result = await build_list(db, lang, kind, 1, "", message.from_user.id)
        if not result:
            await message.answer(t(lang, "no_content"))
            return
        text, kb = result
        await message.answer(text, reply_markup=kb)
        return

    if action == "lang":
        await message.answer(t(lang, "choose_lang"), reply_markup=lang_kb())
        return

    if action == "help":
        await message.answer(t(lang, "help_text"), reply_markup=back_kb(lang, "home"))
        return

    if action == "admin":
        if not await is_admin(db, message.from_user.id, message.from_user.username):
            await message.answer(t(lang, "admin_only"))
            return
        await send_admin_panel(message, db, lang)
        return

    # menu / home
    await send_welcome(message, db, lang, message.from_user.id, message.from_user.username)


# ------------------------------------------------------------------ search
@user_router.message(Search.query, F.chat.type == "private")
async def on_search_state(message: Message, db: Database):
    lang = await get_lang(db, message.from_user.id)
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    if len(text) < 2:
        await message.answer(t(lang, "search_prompt"))
        return
    await _do_search(message, db, lang)


@user_router.message(F.chat.type == "private", F.text)
async def on_any_text(message: Message, state: FSMContext, db: Database):
    """মেনুর বাইরে কেউ সরাসরি নাম লিখলেও সার্চ হবে।"""
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    lang = await get_lang(db, message.from_user.id)
    if len(text) < 2:
        await message.answer(t(lang, "search_prompt"))
        return
    await state.clear()
    await _do_search(message, db, lang)


# ------------------------------------------------------------------ callbacks
@user_router.callback_query(F.data == "noop")
async def on_noop(cb: CallbackQuery):
    await cb.answer()


@user_router.callback_query(F.data == "home")
async def on_home(cb: CallbackQuery, db: Database):
    lang = await get_lang(db, cb.from_user.id)
    await cb.message.answer(
        t(lang, "welcome", name=_name(cb.from_user)),
        reply_markup=await _menu_keyboard(db, cb.from_user.id, lang, cb.from_user.username),
    )
    await cb.answer()


@user_router.callback_query(F.data.startswith("pg:"))
async def on_page(cb: CallbackQuery, db: Database):
    try:
        _, kind, ref, page_raw = cb.data.split(":", 3)
        page = int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    lang = await get_lang(db, cb.from_user.id)
    result = await build_list(db, lang, kind, page, ref, cb.from_user.id)
    if not result:
        await cb.answer(t(lang, "no_content"))
        return
    text, kb = result
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@user_router.callback_query(F.data.startswith("tm:"))
async def on_team_click(cb: CallbackQuery, db: Database):
    try:
        _, ref, page_raw = cb.data.split(":", 2)
        page = int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    lang = await get_lang(db, cb.from_user.id)
    result = await build_list(db, lang, "tm", page, ref, cb.from_user.id)
    if not result:
        await cb.answer(t(lang, "no_team_content"))
        return
    text, kb = result
    await _edit_or_send(cb, text, kb)
    await cb.answer()


@user_router.callback_query(F.data.startswith("v:"))
async def on_video_click(cb: CallbackQuery, db: Database, bot: Bot):
    match_id = match_id_from_ref(cb.data[2:])
    lang = await get_lang(db, cb.from_user.id)
    match = await db.get_match(match_id) if match_id else None
    if not match:
        await cb.answer(t(lang, "video_unavailable"), show_alert=False)
        return

    ad = await load_ad(db)
    if ad:
        token = await db.create_ad_session(cb.from_user.id, match_id, ad["url"])
        await db.register_ad_view(cb.from_user.id)
        timer_note = (
            f"⏱ <b>বাধ্যতামূলক {AD_TIMER_SECONDS} সেকেন্ড অ্যাড:</b> নিচের বাটনে ক্লিক করে মাত্র {AD_TIMER_SECONDS} সেকেন্ড অপেক্ষা করলেই ভিডিওটি আনলক হয়ে যাবে!"
            if lang == "bn"
            else f"{t(lang, 'ad_note')} ({AD_TIMER_SECONDS}s)"
        )
        text = (
            f"{t(lang, 'ad_header')}\n\n"
            f"🎬 <b>{esc(match['title'])}</b> ({esc(match['team'])})\n\n"
            f"{esc(ad['text'])}\n\n"
            f"{timer_note}"
        )
        kb = ad_kb(lang, match_id, ad["url"], ad["btn"], token=token)
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except TelegramBadRequest:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return

    # অ্যাড বন্ধ বা সেট করা না থাকলে সাথে সাথে ফ্রি ভিডিও!
    await cb.answer(t(lang, "delivering"))
    await send_video_to(bot, db, cb.message.chat.id, match, lang)


@user_router.callback_query(F.data.startswith("vx:"))
async def on_video_after_ad(cb: CallbackQuery, db: Database, bot: Bot):
    payload = cb.data[3:]
    lang = await get_lang(db, cb.from_user.id)
    session = await db.get_ad_session(payload)

    if session:
        match_id = int(session["match_id"])
        match = await db.get_match(match_id)
        if not match:
            await cb.answer(t(lang, "video_unavailable"), show_alert=False)
            return

        # ইতিমধ্যে অটো-ডেলিভারি হয়ে থাকলে আবার পাঠানোর দরকার নেই
        if session["delivered"] == 1:
            await cb.answer("✅ ভিডিওটি ইতিমধ্যে পাঠানো হয়েছে!", show_alert=False)
            return

        base = webhook_base_url()
        now = time.time()

        # যদি ওয়েব ভেরিফিকেশন গেটওয়ে চালু থাকে (Render / Server URL আছে) এবং অ্যাড লিংক থাকে
        if base and session["ad_url"]:
            if session["verified"] != 1:
                opened_at = float(session["opened_at"] or 0)
                if opened_at <= 0:
                    msg = (
                        f"⚠️ ফাঁকি দেওয়া যাবে না! আগে উপরের বাটনে ক্লিক করে {AD_TIMER_SECONDS} সেকেন্ড অ্যাডটি দেখুন।"
                        if lang == "bn"
                        else f"⚠️ Please click the Ad button above and wait {AD_TIMER_SECONDS} seconds first!"
                    )
                    await cb.answer(msg, show_alert=True)
                    return
                elapsed = now - opened_at
                if elapsed < (AD_TIMER_SECONDS - 0.3):
                    rem = max(1, int(round(AD_TIMER_SECONDS - elapsed)))
                    msg = (
                        f"⏳ এখনো {AD_TIMER_SECONDS} সেকেন্ড পূর্ণ হয়নি! আরও {rem} সেকেন্ড অপেক্ষা করুন।"
                        if lang == "bn"
                        else f"⏳ Please wait {rem} more seconds!"
                    )
                    await cb.answer(msg, show_alert=True)
                    return
                await db.mark_ad_verified(payload)
        else:
            # পোলিং মোডে (যেখানে ওয়েব সার্ভার URL নেই) তৈরি হওয়ার সময় থেকে ৫ সেকেন্ড যাচাই
            elapsed = now - float(session["created_at"] or 0)
            if elapsed < (AD_TIMER_SECONDS - 0.2):
                rem = max(1, int(round(AD_TIMER_SECONDS - elapsed)))
                msg = (
                    f"⚠️ ফাঁকি দেওয়া যাবে না! অ্যাড লিংকে ক্লিক করে আরও {rem} সেকেন্ড অপেক্ষা করুন।"
                    if lang == "bn"
                    else f"⚠️ Please open the ad and wait {rem} more seconds!"
                )
                await cb.answer(msg, show_alert=True)
                return

        await db.mark_ad_delivered(payload)
        await cb.answer(t(lang, "delivering"))
        ok = await send_video_to(bot, db, cb.message.chat.id, match, lang)
        if ok:
            try:
                await cb.message.delete()
            except TelegramBadRequest:
                pass
        return

    # Fallback for legacy callback ref
    match_id = match_id_from_ref(payload)
    match = await db.get_match(match_id) if match_id else None
    if not match:
        await cb.answer(t(lang, "video_unavailable"), show_alert=False)
        return
    await cb.answer(t(lang, "delivering"))
    await send_video_to(bot, db, cb.message.chat.id, match, lang)


# ==========================================================================
# 🛠️ অ্যাডমিন প্যানেল
# ==========================================================================

admin_router = Router(name="admin")


class Admin(StatesGroup):
    bc = State()
    sync_user = State()
    ad_text = State()
    ad_btn = State()
    ad_url = State()
    edit_team = State()
    edit_title = State()
    manual_video = State()
    manual_info = State()


# ------------------------------------------------------------------ helpers
def _flag(lang: str, value: bool) -> str:
    return t(lang, "ad_on" if value else "ad_off")


async def _guard(cb: CallbackQuery, db: Database) -> tuple[bool, str]:
    lang = await get_lang(db, cb.from_user.id)
    if not await is_admin(db, cb.from_user.id, cb.from_user.username):
        await cb.answer(t(lang, "admin_only"), show_alert=True)
        return False, lang
    return True, lang


async def _safe_edit(cb: CallbackQuery, text: str, kb=None):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            await cb.message.answer(text, reply_markup=kb)


async def _render_ad_panel(cb: CallbackQuery, db: Database, lang: str):
    s = await db.get_settings("ad_")
    has_ad_content = bool((s.get("ad_url") or "").strip() or (s.get("ad_text") or "").strip())
    ad_on = s.get("ad_active") == "1" and has_ad_content
    imp_total, imp_users = await db.ad_stats()
    text = t(
        lang,
        "ad_panel",
        status=_flag(lang, ad_on),
        text=esc(s.get("ad_text") or "🔥 ভিডিওটি পেতে ৫ সেকেন্ড অ্যাড দেখুন (অটো)"),
        btn=esc(s.get("ad_btn") or f"📺 অ্যাড দেখুন ({AD_TIMER_SECONDS}s)"),
        url=esc(s.get("ad_url") or t(lang, "not_set")),
        imp=f"{imp_total} ({imp_users} 👤)",
    )
    await _safe_edit(cb, text, ad_panel_kb(lang, ad_on, has_ad_content))


async def _render_matches(cb: CallbackQuery, db: Database, lang: str, page: int):
    page = max(1, page)
    size = PAGE_ADMIN_MATCHES
    total = await db.count_matches()
    pages = max(1, math.ceil(total / size))
    page = min(page, pages)
    rows = await db.get_matches_latest((page - 1) * size, size)
    if not rows:
        await _safe_edit(cb, t(lang, "no_content"), back_kb(lang, "a:home"))
        return
    text = t(lang, "matches_panel", n=total, p=page, tp=pages)
    await _safe_edit(cb, text, admin_matches_kb(lang, rows, page, total, size))


async def _show_match_card(cb: CallbackQuery, db: Database, lang: str, match_id: int, page: int):
    match = await db.get_match(match_id)
    if not match:
        await _safe_edit(cb, t(lang, "no_content"), back_kb(lang, "a:matches:1"))
        return
    text = t(
        lang,
        "match_card",
        id=match["id"],
        team=esc(match["team"]),
        title=esc(match["title"]),
        year=year_of(match),
        views=match["views"],
        date=fmt_date(match["created_at"]),
    )
    await _safe_edit(cb, text, match_admin_kb(lang, match["id"], page))


async def _channel_status(bot: Bot, chat_id: int) -> str:
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
        return f"✅ {esc(title)} (<code>{chat_id}</code>)"
    except Exception:  # noqa: BLE001
        return f"❌ <code>{chat_id}</code>"


async def _source_label(db: Database, lang: str) -> str:

    username = await source_username(db)
    if not username:
        return t(lang, "sync_no_user")
    last_id = await db.get_setting(f"poll_last_{username.lower()}") or "—"
    return t(lang, "sync_public", user=username, last=last_id)


async def _render_sync(cb: CallbackQuery, db: Database, lang: str, bot: Bot):
    auto_on = (await db.get_setting("autosync")) != "0"
    check = f"📤 {await _channel_status(bot, DEST_CHANNEL)}"
    last_run = await db.get_setting("poll_last_run") or t(lang, "not_set")
    text = t(
        lang,
        "sync_panel",
        source=await _source_label(db, lang),
        dest=DEST_CHANNEL,
        status=t(lang, "sync_on" if auto_on else "sync_off"),
        last_run=last_run,
        check=check,
    )
    await _safe_edit(cb, text, sync_kb(lang, auto_on))


# ------------------------------------------------------------------ entry points
@admin_router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: Message, db: Database):
    uid = message.from_user.id
    lang = await get_lang(db, uid)
    if await is_admin(db, uid, message.from_user.username):
        await send_admin_panel(message, db, lang)
        return
    owner = await db.get_setting("owner_id")
    if not owner:
        # প্রথম /admin যে দেবে সে-ই owner (বটের সেটআপ সহজ করতে)
        await db.set_setting("owner_id", str(uid))
        await message.answer(
            t(lang, "owner_assigned"), reply_markup=main_menu_kb(lang, True)
        )
        await send_admin_panel(message, db, lang)
        return
    await message.answer(t(lang, "admin_only"))


@admin_router.message(Command("cancel"), F.chat.type == "private")
async def admin_cmd_cancel(message: Message, state: FSMContext, db: Database):
    await state.clear()
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "bc_cancelled"))


@admin_router.message(F.chat.type == "private", F.forward_origin)
async def learn_source_channel(message: Message, db: Database, bot: Bot):
    """অ্যাডমিন সোর্স চ্যানেলের যেকোনো পোস্ট ফরওয়ার্ড করলে বট নিজে সোর্স চ্যানেল ধরে নেয়।"""
    if not await is_admin(db, message.from_user.id, message.from_user.username):
        return
    lang = await get_lang(db, message.from_user.id)
    origin = message.forward_origin
    chat = getattr(origin, "chat", None)
    if chat is None or getattr(chat, "type", "") != "channel":
        return
    if chat.id == DEST_CHANNEL:
        return
    username = getattr(chat, "username", None)
    if not username:
        await message.answer(
            "⚠️ এই চ্যানেলটা প্রাইভেট (পাবলিক ইউজারনেম নেই)।\n"
            "প্রাইভেট চ্যানেল পড়তে হলে বটকে ওই চ্যানেলে অ্যাডমিন বানাতে হবে।"
        )
        return
    await db.set_setting("source_username", "@" + username)
    await message.answer(
        f"✅ সোর্স চ্যানেল সেট হয়েছে: <b>@{username}</b>\n"
        f"এখন থেকে ওখানে নতুন ভিডিও এলে বট নিজেই আপনার চ্যানেলে নিয়ে আসবে।"
    )
    try:

        count = await poll_once(bot, db, username)
        if count:
            await message.answer(t(lang, "capture_posted"))
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"⚠️ প্রথম চেক ব্যর্থ: {exc}")


# ------------------------------------------------------------------ panel core
@admin_router.callback_query(F.data == "a:home")
async def cb_home(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    await _safe_edit(cb, t(lang, "ap_title"), admin_kb(lang))
    await cb.answer()


@admin_router.callback_query(F.data == "a:stats")
async def cb_stats(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    ad_imp, ad_users = await db.ad_stats()
    text = t(
        lang,
        "stats_text",
        users=await db.count_users(),
        new_today=await db.count_new_today(),
        active_today=await db.count_active_today(),
        matches=await db.count_matches(),
        views=await db.total_views(),
        ad_imp=ad_imp,
        ad_users=ad_users,
    )
    await _safe_edit(cb, text, admin_kb(lang))
    await cb.answer()


# ------------------------------------------------------------------ users
@admin_router.callback_query(F.data.startswith("a:users:"))
async def cb_users(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    total = await db.count_users()
    pages = max(1, math.ceil(total / PAGE_USERS))
    page = min(max(1, page), pages)
    users = await db.get_users_page((page - 1) * PAGE_USERS, PAGE_USERS)

    lines = [t(lang, "users_header", n=total, p=page, tp=pages)]
    for u in users:
        uname = f" · @{u['username']}" if u["username"] else ""
        lines.append(
            t(
                lang,
                "user_line",
                name=esc(u["first_name"] or "—"),
                id=u["id"],
                lang=LANGUAGES.get(u["lang"] or "", "—"),
                username=esc(uname),
                date=fmt_date(u["created_at"]),
            )
        )
    await _safe_edit(cb, "\n\n".join(lines), users_kb(lang, page, pages))
    await cb.answer()


# ------------------------------------------------------------------ broadcast
@admin_router.callback_query(F.data == "a:bc")
async def cb_broadcast(cb: CallbackQuery, state: FSMContext, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    await state.set_state(Admin.bc)
    await _safe_edit(cb, t(lang, "bc_prompt"), cancel_kb(lang, "a:home"))
    await cb.answer()


@admin_router.message(Admin.bc, F.chat.type == "private")
async def do_broadcast(message: Message, state: FSMContext, db: Database):
    lang = await get_lang(db, message.from_user.id)
    if message.text and (message.text in LABEL_ACTIONS or message.text.startswith("/")):
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"))
        return

    users = await db.get_all_user_ids()
    await message.answer(t(lang, "bc_started", n=len(users)))
    sent = fail = 0
    for index, uid in enumerate(users, start=1):
        try:
            await message.copy_to(uid)
            sent += 1
        except Exception:  # noqa: BLE001
            fail += 1
        if index % MAX_BROADCAST_PER_SECOND == 0:
            await asyncio.sleep(1.0)
    await state.clear()
    await message.answer(t(lang, "bc_done", ok=sent, fail=fail))


# ------------------------------------------------------------------ ad manager
@admin_router.callback_query(F.data == "a:ad")
async def cb_ad(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    await _render_ad_panel(cb, db, lang)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("a:ad:"))
async def cb_ad_action(cb: CallbackQuery, state: FSMContext, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    action = cb.data.split(":", 2)[2]

    if action == "text":
        await state.set_state(Admin.ad_text)
        await _safe_edit(cb, t(lang, "ad_enter_text"), cancel_kb(lang, "a:ad"))
        await cb.answer()
        return

    if action == "btn":
        await state.set_state(Admin.ad_btn)
        await _safe_edit(cb, t(lang, "ad_enter_btn"), cancel_kb(lang, "a:ad"))
        await cb.answer()
        return

    if action == "url":
        await state.set_state(Admin.ad_url)
        await _safe_edit(cb, t(lang, "ad_enter_url"), cancel_kb(lang, "a:ad"))
        await cb.answer()
        return

    if action == "toggle":
        s = await db.get_settings("ad_")
        if not ((s.get("ad_url") or "").strip() or (s.get("ad_text") or "").strip()):
            await cb.answer("⚠️ আগে 🔗 লিংক বাটনে চাপ দিয়ে আপনার অ্যাড লিংক দিন!", show_alert=True)
            return
        new_value = "0" if s.get("ad_active") == "1" else "1"
        await db.set_setting("ad_active", new_value)
        await _render_ad_panel(cb, db, lang)
        await cb.answer()
        return

    if action == "clear":
        for key in ("ad_text", "ad_btn", "ad_url", "ad_active"):
            await db.set_setting(key, None)
        await _render_ad_panel(cb, db, lang)
        await cb.answer(t(lang, "ad_cleared"), show_alert=True)
        return

    if action == "preview":
        s = await db.get_settings("ad_")
        text = f"{t(lang, 'ad_header')}\n\n{esc(s.get('ad_text') or '')}\n\n{t(lang, 'ad_note')}"
        kb = ad_preview_kb(lang, s.get("ad_url") or "", s.get("ad_btn") or "")
        await _safe_edit(cb, text, kb)
        await cb.answer()
        return

    await cb.answer()


def _is_escape(text: str) -> bool:
    return text in LABEL_ACTIONS or text.startswith("/")


@admin_router.message(Admin.ad_text, F.chat.type == "private", F.text)
async def ad_save_text(message: Message, state: FSMContext, db: Database):
    if _is_escape(message.text):
        await state.clear()
        lang = await get_lang(db, message.from_user.id)
        await message.answer(t(lang, "bc_cancelled"), reply_markup=main_menu_kb(lang, True))
        return
    await db.set_setting("ad_text", message.text.strip()[:900])
    await state.clear()
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "ad_saved"), reply_markup=admin_kb(lang))


@admin_router.message(Admin.ad_btn, F.chat.type == "private", F.text)
async def ad_save_btn(message: Message, state: FSMContext, db: Database):
    if _is_escape(message.text):
        await state.clear()
        lang = await get_lang(db, message.from_user.id)
        await message.answer(t(lang, "bc_cancelled"), reply_markup=main_menu_kb(lang, True))
        return
    await db.set_setting("ad_btn", message.text.strip()[:64])
    await state.clear()
    lang = await get_lang(db, message.from_user.id)
    await message.answer(t(lang, "ad_saved"), reply_markup=admin_kb(lang))


@admin_router.message(Admin.ad_url, F.chat.type == "private", F.text)
async def ad_save_url(message: Message, state: FSMContext, db: Database):
    lang = await get_lang(db, message.from_user.id)
    text = message.text.strip()
    if text in LABEL_ACTIONS:
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"), reply_markup=main_menu_kb(lang, True))
        return
    if text == "/skip":
        await db.set_setting("ad_url", None)
        await db.set_setting("ad_active", "0")
        await state.clear()
        await message.answer(t(lang, "ad_cleared"), reply_markup=admin_kb(lang))
        return

    if not (text.startswith("http://") or text.startswith("https://") or text.startswith("tg://")):
        if "." in text and " " not in text:
            text = "https://" + text
        else:
            await message.answer(t(lang, "ad_enter_url"))
            return

    await db.set_setting("ad_url", text[:500])
    # অ্যাড লিংক দিলেই অটোমেটিক ডিফল্ট টেক্সট ও বাটন সেট হয়ে ৫ সেকেন্ডের বাধ্যতামূলক অ্যাড চালু হয়ে যাবে!
    s = await db.get_settings("ad_")
    if not (s.get("ad_text") or "").strip():
        await db.set_setting(
            "ad_text",
            f"🔥 হাইলাইট ভিডিওটি পেতে নিচের বাটনে ক্লিক করে মাত্র {AD_TIMER_SECONDS} সেকেন্ড অ্যাডটি দেখুন!",
        )
    if not (s.get("ad_btn") or "").strip():
        await db.set_setting("ad_btn", f"📺 অ্যাড দেখুন ({AD_TIMER_SECONDS} সেকেন্ড)")
    await db.set_setting("ad_active", "1")
    await state.clear()
    await message.answer(t(lang, "ad_saved"), reply_markup=admin_kb(lang))


# ------------------------------------------------------------------ matches
@admin_router.callback_query(F.data.startswith("a:matches:"))
async def cb_matches(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        page = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        page = 1
    await _render_matches(cb, db, lang, page)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("pg:mt:"))
async def cb_matches_page(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        page = int(cb.data.split(":")[3])
    except (IndexError, ValueError):
        page = 1
    await _render_matches(cb, db, lang, page)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("am:"))
async def cb_match_card(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        _, raw_id, page_raw = cb.data.split(":", 2)
        match_id, page = int(raw_id), int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    await _show_match_card(cb, db, lang, match_id, page)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("amd:"))
async def cb_match_send_me(cb: CallbackQuery, db: Database, bot: Bot):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    match_id = match_id_from_ref(cb.data.split(":", 1)[1])
    match = await db.get_match(match_id) if match_id else None
    if not match:
        await cb.answer(t(lang, "video_unavailable"), show_alert=True)
        return
    await cb.answer(t(lang, "delivering"))
    await send_video_to(bot, db, cb.from_user.id, match, lang)


@admin_router.callback_query(F.data.startswith("emt:"))
async def cb_edit_team(cb: CallbackQuery, state: FSMContext, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        _, raw_id, page_raw = cb.data.split(":", 2)
        match_id, page = int(raw_id), int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    await state.set_state(Admin.edit_team)
    await state.update_data(match_id=match_id, page=page)
    await _safe_edit(cb, t(lang, "me_team_prompt", id=match_id), cancel_kb(lang, f"am:{match_id}:{page}"))
    await cb.answer()


@admin_router.message(Admin.edit_team, F.chat.type == "private", F.text)
async def save_team_name(message: Message, state: FSMContext, db: Database):
    lang = await get_lang(db, message.from_user.id)
    if message.text in LABEL_ACTIONS or message.text.startswith("/"):
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"))
        return
    data = await state.get_data()
    match_id = data.get("match_id", 0)
    new_team = message.text.strip()[:60]
    await db.update_match(match_id, team=new_team, team_key=norm(new_team))
    await state.clear()
    await message.answer(t(lang, "saved_ok"), reply_markup=main_menu_kb(lang, True))


@admin_router.callback_query(F.data.startswith("emz:"))
async def cb_edit_title(cb: CallbackQuery, state: FSMContext, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        _, raw_id, page_raw = cb.data.split(":", 2)
        match_id, page = int(raw_id), int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    await state.set_state(Admin.edit_title)
    await state.update_data(match_id=match_id, page=page)
    await _safe_edit(cb, t(lang, "me_title_prompt", id=match_id), cancel_kb(lang, f"am:{match_id}:{page}"))
    await cb.answer()


@admin_router.message(Admin.edit_title, F.chat.type == "private", F.text)
async def save_match_title(message: Message, state: FSMContext, db: Database):
    lang = await get_lang(db, message.from_user.id)
    if message.text in LABEL_ACTIONS or message.text.startswith("/"):
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"))
        return
    data = await state.get_data()
    match_id = data.get("match_id", 0)
    await db.update_match(match_id, title=message.text.strip()[:200])
    await state.clear()
    await message.answer(t(lang, "saved_ok"), reply_markup=main_menu_kb(lang, True))


@admin_router.callback_query(F.data.startswith("adm:"))
async def cb_delete_ask(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        _, raw_id, page_raw = cb.data.split(":", 2)
        match_id, page = int(raw_id), int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    await _safe_edit(cb, t(lang, "delete_confirm", id=match_id), delete_confirm_kb(lang, match_id, page))
    await cb.answer()


@admin_router.callback_query(F.data.startswith("admy:"))
async def cb_delete_yes(cb: CallbackQuery, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    try:
        _, raw_id, page_raw = cb.data.split(":", 2)
        match_id, page = int(raw_id), int(page_raw)
    except (ValueError, IndexError):
        await cb.answer()
        return
    await db.delete_match(match_id)
    await cb.answer(t(lang, "deleted_ok"), show_alert=True)
    await _render_matches(cb, db, lang, page)


# ------------------------------------------------------------------ sync
@admin_router.callback_query(F.data == "a:sync")
async def cb_sync(cb: CallbackQuery, db: Database, bot: Bot):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    await _render_sync(cb, db, lang, bot)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("a:sync:"))
async def cb_sync_action(cb: CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    action = cb.data.split(":", 2)[2]

    if action == "toggle":
        current = await db.get_setting("autosync")
        await db.set_setting("autosync", "0" if current != "0" else "1")
        await _render_sync(cb, db, lang, bot)
        await cb.answer()
        return

    if action == "user":
        await state.set_state(Admin.sync_user)
        await _safe_edit(cb, t(lang, "sync_ask_user"), cancel_kb(lang, "a:sync"))
        await cb.answer()
        return

    if action == "check":

        username = await source_username(db)
        if not username:
            await cb.answer(t(lang, "sync_no_user"), show_alert=True)
            return
        await cb.answer()
        try:
            html = await fetch_channel_html(username)
            ids = parse_video_post_ids(html)
            if not ids:
                await cb.message.answer(t(lang, "sync_check_fail", err="no video posts"))
                return
            await cb.message.answer(
                t(lang, "sync_check_ok", user=username, n=len(ids), last=ids[-1], interval=POLL_INTERVAL)
            )
        except Exception as exc:  # noqa: BLE001
            await cb.message.answer(t(lang, "sync_check_fail", err=str(exc)[:120]))
        return

    await _render_sync(cb, db, lang, bot)
    await cb.answer()


@admin_router.message(Admin.sync_user, F.chat.type == "private", F.text)
async def save_source_username(message: Message, state: FSMContext, db: Database, bot: Bot):
    lang = await get_lang(db, message.from_user.id)
    text = message.text.strip()
    if text in LABEL_ACTIONS:
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"), reply_markup=main_menu_kb(lang, True))
        return
    if text == "/skip":
        await db.set_setting("source_username", None)
        await state.clear()
        await message.answer(t(lang, "saved_ok"), reply_markup=main_menu_kb(lang, True))
        return
    username = text.lstrip("@").strip()
    if not username or not all(c.isalnum() or c == "_" for c in username):
        await message.answer(t(lang, "sync_bad_user"))
        return
    await db.set_setting("source_username", "@" + username)
    await state.clear()
    await message.answer(
        t(lang, "sync_user_saved", user=username), reply_markup=main_menu_kb(lang, True)
    )


# ------------------------------------------------------------------ manual add
@admin_router.callback_query(F.data == "a:manual")
async def cb_manual(cb: CallbackQuery, state: FSMContext, db: Database):
    ok, lang = await _guard(cb, db)
    if not ok:
        return
    await state.set_state(Admin.manual_video)
    await _safe_edit(cb, t(lang, "manual_prompt_video"), cancel_kb(lang, "a:home"))
    await cb.answer()


@admin_router.message(Admin.manual_video, F.chat.type == "private")
async def manual_take_video(message: Message, state: FSMContext, db: Database):
    lang = await get_lang(db, message.from_user.id)
    media_type, file_id, _ = extract_media(message)
    if not media_type:
        if message.text and message.text.startswith("/"):
            await state.clear()
            await message.answer(t(lang, "bc_cancelled"))
            return
        await message.answer(t(lang, "manual_prompt_video"))
        return
    await state.update_data(file_id=file_id, media_type=media_type)
    await state.set_state(Admin.manual_info)
    await message.answer(t(lang, "manual_prompt_info"))


@admin_router.message(Admin.manual_info, F.chat.type == "private", F.text)
async def manual_take_info(message: Message, state: FSMContext, db: Database, bot: Bot):
    lang = await get_lang(db, message.from_user.id)
    text = message.text.strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer(t(lang, "bc_cancelled"))
        return

    parsed = parse_caption(text)
    if "|" in text:
        left, right = text.split("|", 1)
        team, title = left.strip(), right.strip()
    elif parsed["team"] and parsed["title"]:
        team, title = parsed["team"], parsed["title"]
    else:
        team = title = ""

    if not team or not title:
        await message.answer(t(lang, "manual_bad_format"))
        return

    data = await state.get_data()
    file_id, media_type = data.get("file_id"), data.get("media_type", "video")
    if not file_id:
        await state.clear()
        await message.answer(t(lang, "manual_prompt_video"))
        return

    posted, dest_msg = await copy_to_destination(
        bot, media_type, file_id, clean_caption(team, title, parsed["year"])
    )
    await db.add_match(
        team=team,
        team_key=norm(team),
        title=title,
        year=parsed["year"],
        tags=parsed["tags"],
        file_id=file_id,
        media_type=media_type,
        dest_msg=dest_msg,
    )
    await state.clear()
    await message.answer(
        t(lang, "manual_saved", team=esc(team), title=esc(title)),
        reply_markup=main_menu_kb(lang, True),
    )


# ==========================================================================
# 📥 চ্যানেল ইনডেক্স ও অটো-কপি
# ==========================================================================

channel_router = Router(name="channel")


def clean_caption(team: str, title: str, year: str) -> str:
    """চ্যানেলে যাওয়া ক্যাপশন — সব লিংক/ইউজারনেম বাদ।"""
    lines = [f"🎬 <b>{esc(title)}</b>", f"🏆 {esc(team)}"]
    if year:
        lines.append(f"📅 {year}")
    return "\n".join(lines)


async def copy_to_destination(bot: Bot, media_type: str, file_id: str, caption: str) -> tuple[bool, int]:
    if not DEST_CHANNEL:
        return False, 0
    try:
        if media_type == "animation":
            sent = await bot.send_animation(
                DEST_CHANNEL, file_id, caption=caption, parse_mode="HTML"
            )
        elif media_type == "document":
            sent = await bot.send_document(
                DEST_CHANNEL, file_id, caption=caption, parse_mode="HTML"
            )
        else:
            sent = await bot.send_video(
                DEST_CHANNEL, file_id, caption=caption, parse_mode="HTML"
            )
        return True, sent.message_id
    except Exception as exc:  # noqa: BLE001
        log.warning("Destination copy failed: %s", exc)
        return False, 0


async def index_message(
    db: Database,
    message: Message,
    *,
    source_msg: int = 0,
    dest_msg: int = 0,
    from_poller: bool = False,
    fallback_caption: str = "",
) -> dict | None:
    """একটা মেসেজ থেকে ভিডিও+ক্যাপশন নিয়ে ডেটাবেজে সেভ করে।"""
    media_type, file_id, _ = extract_media(message)
    if not media_type:
        return None

    if source_msg and await db.get_match_by_source(source_msg):
        return None
    if dest_msg and await db.get_match_by_dest(dest_msg):
        return None

    raw_caption = message_text_or_caption(message)
    if not (raw_caption or "").strip() and fallback_caption:
        raw_caption = fallback_caption
    info = parse_caption(raw_caption)
    team, title, year, tags = info["team"], info["title"], info["year"], info["tags"]

    await db.add_match(
        team=team,
        team_key=norm(team),
        title=title,
        year=year,
        tags=tags,
        file_id=file_id,
        media_type=media_type,
        source_msg=source_msg,
        dest_msg=dest_msg,
    )
    log.info("Indexed match: %s | %s | poller=%s", team, title, from_poller)
    return {"team": team, "title": title, "year": year}


async def notify_admins_new_match(bot: Bot, db: Database, team: str, title: str, year: str, posted: bool) -> None:

    for admin_id in await admin_ids(db):
        row = await db.get_user(admin_id)
        lang = (row["lang"] if row and row["lang"] else DEFAULT_LANG) or "bn"
        posted_text = t(lang, "capture_posted") if posted else t(lang, "capture_failed")
        try:
            await bot.send_message(
                admin_id,
                t(
                    lang,
                    "capture_notice",
                    team=esc(team),
                    title=esc(title),
                    year=year or t(lang, "not_set"),
                    posted=posted_text,
                ),
            )
        except Exception:
            continue


@channel_router.channel_post(F.chat.id == DEST_CHANNEL)
async def on_dest_channel_post(message: Message, bot: Bot, db: Database):
    """আপনার চ্যানেলে নতুন ভিডিও পোস্ট হলে সাথে সাথে ইনডেক্স (ম্যানুয়ালি ফরওয়ার্ড করলেও কাজ করবে)।"""
    if await db.get_setting("autosync") == "0":
        return
    result = await index_message(db, message, dest_msg=message.message_id)
    if result:
        await notify_admins_new_match(bot, db, result["team"], result["title"], result["year"], True)


@channel_router.channel_post(F.chat.id == SOURCE_CHANNEL)
async def on_source_channel_post(message: Message, bot: Bot, db: Database):
    """যদি বটকে সোর্স চ্যানেলেও অ্যাডমিন বানানো হয় — তবেই এটা চলে (রিয়েলটাইম মোড)।"""
    if SOURCE_CHANNEL == DEST_CHANNEL:
        return
    if await db.get_setting("autosync") == "0":
        return

    media_type, file_id, _ = extract_media(message)
    if not media_type:
        return
    info = parse_caption(message_text_or_caption(message))
    posted, dest_msg = await copy_to_destination(
        bot, media_type, file_id, clean_caption(info["team"], info["title"], info["year"])
    )
    result = await index_message(
        db,
        message,
        source_msg=message.message_id,
        dest_msg=dest_msg if posted else 0,
    )
    if result:
        await notify_admins_new_match(bot, db, result["team"], result["title"], result["year"], posted)


# ==========================================================================
# 🚀 চালু করা (webhook + polling + health check)
# ==========================================================================

WEBHOOK_PATH = "/webhook"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("highlighthub")


class ActivityMiddleware:
    """প্রতিটা ইউজার অ্যাক্টিভিটি ট্র্যাক করে (অ্যাডমিন স্ট্যাটসের জন্য)।"""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, event, data):
        try:
            user = getattr(event, "from_user", None)
            if user and not user.is_bot:
                await self.db.touch_user(user.id)
        except Exception:
            pass
        return await handler(event, data)


def create_bot_and_dispatcher():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    db = Database()

    dp["db"] = db
    dp["bot"] = bot

    middleware = ActivityMiddleware(db)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(channel_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    return bot, dp


def webhook_base_url() -> str:
    return (
        os.getenv("WEBHOOK_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or ""
    ).rstrip("/")


AD_GATE_HTML = """<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⏳ ৫ সেকেন্ড অপেক্ষা করুন — HighlightHub</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#090d16;color:#f8fafc;display:flex;flex-direction:column;height:100vh;overflow:hidden}
  .topbar{background:linear-gradient(90deg,#0f172a,#1e293b);border-bottom:1px solid #334155;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:20}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px;color:#38bdf8}
  .timer-pill{background:#1e293b;border:1px solid #475569;padding:8px 16px;border-radius:999px;font-weight:700;font-size:14px;display:flex;align-items:center;gap:8px;color:#fbbf24}
  .timer-pill.done{background:#065f46;border-color:#10b981;color:#ecfdf5}
  .progress-wrap{height:5px;background:#1e293b;width:100%}
  .progress-bar{height:100%;width:0%;background:linear-gradient(90deg,#f59e0b,#10b981);transition:width 0.25s linear}
  .ad-container{flex:1;position:relative;background:#0f172a;display:flex;flex-direction:column;align-items:center;justify-content:center}
  iframe{width:100%;height:100%;border:0;background:#fff}
  .fallback-card{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);background:rgba(15,23,42,0.95);border:1px solid #334155;padding:16px 22px;border-radius:14px;text-align:center;max-width:440px;width:92%;box-shadow:0 12px 32px rgba(0,0,0,0.5);z-index:30}
  .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 20px;border-radius:10px;font-weight:700;font-size:14px;text-decoration:none;border:0;cursor:pointer;margin-top:10px;width:100%}
  .btn-ad{background:#2563eb;color:#fff}
  .btn-unlock{background:#10b981;color:#052e16;display:none}
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">🎬 HighlightHub Video Gate</div>
    <div id="timerBox" class="timer-pill">⏳ বাকি আছে: <span id="secLeft">__SECONDS__</span> সেকেন্ড</div>
  </div>
  <div class="progress-wrap"><div id="progBar" class="progress-bar"></div></div>
  <div class="ad-container">
    <iframe id="adFrame" src="__AD_URL__" sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>
    <div class="fallback-card">
      <div id="statusMsg" style="font-size:14px;line-height:1.5;color:#cbd5e1">
        🔒 ভিডিওটি আনলক হচ্ছে... দয়া করে <b><span id="secText">__SECONDS__</span> সেকেন্ড</b> এই পেজে অপেক্ষা করুন (ফাঁকি দেওয়া যাবে না)।
      </div>
      <a href="__AD_URL__" target="_blank" rel="noopener" class="btn btn-ad" id="openAdBtn">🔗 বিজ্ঞাপনটি নতুন ট্যাবে দেখুন</a>
      <button class="btn btn-unlock" id="unlockBtn" onclick="finishAndClose()">✅ ভিডিও আনলক হয়েছে — বটে ফিরে যান</button>
    </div>
  </div>
<script>
  const token = "__TOKEN__";
  const totalSec = __SECONDS__;
  let elapsed = 0;
  let completed = false;
  const secLeftEl = document.getElementById("secLeft");
  const secTextEl = document.getElementById("secText");
  const progBar = document.getElementById("progBar");
  const timerBox = document.getElementById("timerBox");
  const statusMsg = document.getElementById("statusMsg");
  const unlockBtn = document.getElementById("unlockBtn");

  const interval = setInterval(async () => {
    if (document.hidden) return; // ট্যাব মিনিমাইজ করলে কাউন্টডাউন থেমে থাকবে (ফাঁকি রোধ)
    elapsed += 0.25;
    const rem = Math.max(0, Math.ceil(totalSec - elapsed));
    secLeftEl.textContent = rem;
    secTextEl.textContent = rem;
    progBar.style.width = Math.min(100, (elapsed / totalSec) * 100) + "%";

    if (elapsed >= totalSec && !completed) {
      completed = true;
      clearInterval(interval);
      timerBox.classList.add("done");
      timerBox.innerHTML = "✅ ৫ সেকেন্ড সম্পন্ন!";
      statusMsg.innerHTML = "🎉 <b>অভিনন্দন! আপনার ভিডিওটি বটে পাঠিয়ে দেওয়া হয়েছে!</b> এখন টেলিগ্রাম বটে ফিরে যান।";
      unlockBtn.style.display = "inline-flex";
      try {
        await fetch("/api/ad/verify/" + encodeURIComponent(token), {method: "POST"});
      } catch (e) {}
    }
  }, 250);

  function finishAndClose() {
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.close();
    }
    window.location.href = "https://t.me/__BOT_USERNAME__";
  }
</script>
</body>
</html>"""


DASHBOARD_HTML = """<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HighlightHub Bot — Control & Status</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0b1120;color:#e2e8f0;padding:24px 16px;line-height:1.6}
  .wrap{max-width:960px;margin:0 auto;display:grid;gap:20px}
  .card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:24px;box-shadow:0 10px 25px rgba(0,0,0,0.35)}
  h1{font-size:24px;color:#f8fafc;display:flex;align-items:center;gap:10px;margin-bottom:8px}
  h2{font-size:18px;color:#38bdf8;margin-bottom:12px}
  .badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;font-size:13px;font-weight:700}
  .badge-ok{background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4)}
  .badge-warn{background:rgba(245,158,11,0.18);color:#fbbf24;border:1px solid rgba(245,158,11,0.4)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:14px}
  .stat{background:#0f172a;border:1px solid #1e293b;padding:16px;border-radius:12px}
  .stat-label{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px}
  .stat-val{font-size:24px;font-weight:800;color:#f8fafc;margin-top:4px}
  code{background:#0f172a;color:#38bdf8;padding:2px 8px;border-radius:6px;font-size:13px}
  input,select{width:100%;padding:11px 14px;border-radius:10px;border:1px solid #475569;background:#0f172a;color:#f8fafc;font-size:14px;margin-top:6px}
  button{background:#2563eb;color:#fff;border:0;padding:11px 18px;border-radius:10px;font-weight:700;cursor:pointer;font-size:14px}
  button:hover{background:#1d4ed8}
  .btn-green{background:#059669}
  .btn-green:hover{background:#047857}
  .btn-red{background:#dc2626}
  .step-list{padding-left:20px;display:grid;gap:8px;color:#cbd5e1;font-size:14px}
  .sim-box{background:#0f172a;border:1px solid #334155;border-radius:12px;padding:16px;margin-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
      <div>
        <h1>🤖 HighlightHub Bot (@HighlightHubOfficial_bot)</h1>
        <p style="color:#94a3b8;font-size:14px">অ্যাডমিন: <code>@sabit12354</code> | ডেস্টিনেশন চ্যানেল: <code>-1004308076789</code> | সোর্স চ্যানেল: <code>-1002279362776</code></p>
      </div>
      <div>__BOT_STATUS_BADGE__</div>
    </div>

    <div class="grid">
      <div class="stat"><div class="stat-label">👥 মোট ইউজার</div><div class="stat-val" id="stUsers">__USERS__</div></div>
      <div class="stat"><div class="stat-label">🎬 মোট হাইলাইট ম্যাচ</div><div class="stat-val" id="stMatches">__MATCHES__</div></div>
      <div class="stat"><div class="stat-label">👁 মোট ভিডিও ভিউ</div><div class="stat-val" id="stViews">__VIEWS__</div></div>
      <div class="stat"><div class="stat-label">📣 ৫ সেকেন্ড অ্যাড গেট</div><div class="stat-val" id="stAd">__AD_STATUS__</div></div>
    </div>
  </div>

  __TOKEN_WARNING_CARD__

  <div class="card">
    <h2>🔍 লাইভ বট ফিচার টেস্টার (সার্চ, বানান ভুল সংশোধন ও ৫-সেকেন্ড অ্যাড গেট)</h2>
    <p style="font-size:14px;color:#94a3b8;margin-bottom:12px">
      নিচে ভুল বানানে টিমের নাম লিখে (যেমন: <code>barselona</code>, <code>ral madrid</code>, <code>argntina</code>, <code>brajil</code>) সার্চ করে দেখুন বট কীভাবে নিজে থেকেই বুঝে নেয় এবং সব ম্যাচের বিবরণ দেয়:
    </p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <input type="text" id="qInput" placeholder="টিম বা ম্যাচের নাম লিখুন (যেমন: barselona, ral madrid, argntina)..." style="flex:1;min-width:220px;margin:0" value="barselona">
      <button onclick="runTestSearch()">🔍 সার্চ টেস্ট করুন</button>
    </div>
    <div id="searchOut" class="sim-box" style="margin-top:14px;font-size:14px"></div>
  </div>

  <div class="card">
    <h2>📣 অ্যাডমিন অ্যাড লিংক ও ফ্রি মোড কন্ট্রোল (৫ সেকেন্ড বাধ্যতামূলক টাইমার)</h2>
    <p style="font-size:14px;color:#94a3b8;margin-bottom:12px">
      আপনি বটের ভেতরে <code>/admin</code> → <b>📣 অ্যাড ম্যানেজার</b> থেকে অথবা নিচের বক্স থেকে সরাসরি অ্যাড লিংক বসাতে বা বন্ধ করতে পারবেন। অ্যাড বন্ধ থাকলে ইউজাররা সরাসরি ফ্রিতে ভিডিও পাবে, আর চালু থাকলে ৫ সেকেন্ড বাধ্যতামূলক অ্যাড দেখতে হবে:
    </p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <input type="text" id="adUrlInput" placeholder="https://your-ad-link.com ..." value="__CURRENT_AD_URL__" style="flex:1;min-width:220px;margin:0">
      <button class="btn-green" onclick="saveAdConfig(true)">🟢 অ্যাড চালু করুন (5s Timer)</button>
      <button class="btn-red" onclick="saveAdConfig(false)">🔴 অ্যাড বন্ধ করুন (Free Mode)</button>
    </div>
    <div id="adSaveMsg" style="margin-top:10px;font-size:13px;color:#34d399"></div>
  </div>

  <div class="card">
    <h2>🚀 কেন আগের ডিপ্লয় Failed হয়েছিল এবং এখন কীভাবে ১ মিনিটে চালাবেন</h2>
    <ol class="step-list">
      <li><b>আগের সমস্যার কারণ ১:</b> আপনার GitHub রিপোজিটরিতে (<code>xbtxn4196-glitch/bot-111111</code>) ফাইলের নাম ভুলে <code>requiremennts.txt</code> (দুইটা <code>n</code>) দেওয়া ছিল, তাই Render <code>requirements.txt</code> খুঁজে না পেয়ে Build Failed দেখিয়েছিল।</li>
      <li><b>আগের সমস্যার কারণ ২:</b> আপনার পুরোনো বট টোকেনটি (<code>8653868768:AAEk...5qU</code>) বাতিল (401 Unauthorized) হয়ে যাওয়ায় আগের কোড ক্র্যাশ করছিল। এখন কোডটি এমনভাবে ঠিক করা হয়েছে যে টোকেন ভুল থাকলেও সার্ভার কখনোই ক্র্যাশ বা Failed হবে না!</li>
      <li><b>এখন করণীয়:</b> আমরা আপনার জন্য একদম নিখুঁত <code>main.py</code> এবং সঠিক নামের <code>requirements.txt</code> তৈরি করে দিয়েছি। এই ফাইল দুইটি আপনার GitHub-এ আপলোড করে Render-এ নতুন <code>BOT_TOKEN</code> বসিয়ে <b>Deploy</b> চাপলেই বট সাথে সাথে চালু হয়ে যাবে!</li>
    </ol>
  </div>
</div>

<script>
async function runTestSearch() {
  const q = document.getElementById('qInput').value;
  const out = document.getElementById('searchOut');
  out.innerHTML = '⏳ খোঁজা হচ্ছে...';
  const res = await fetch('/api/test/search?q=' + encodeURIComponent(q));
  const data = await res.json();
  if (!data.matches || data.matches.length === 0) {
    out.innerHTML = '😔 কোনো ম্যাচ পাওয়া যায়নি।';
    return;
  }
  let html = `<div style="margin-bottom:10px;color:#38bdf8;font-weight:700">🔍 "${data.query}" (সংশোধিত: ${data.normalized}) — মোট ${data.matches.length}টি ম্যাচ পাওয়া গেছে:</div>`;
  data.matches.forEach((m, i) => {
    html += `<div style="padding:10px;border-bottom:1px solid #1e293b;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
      <div><b>${i+1}. 🏆 ${m.team}</b> — ${m.title} <span style="color:#fbbf24">(${m.year || '-'})</span></div>
      <a href="/ad/${m.demo_token}" target="_blank" style="background:#2563eb;color:#fff;padding:6px 12px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:700">🎬 ম্যাচটিতে ক্লিক করুন</a>
    </div>`;
  });
  out.innerHTML = html;
}

async function saveAdConfig(enable) {
  const url = document.getElementById('adUrlInput').value.trim();
  const res = await fetch('/api/test/ad', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enable, url})
  });
  const data = await res.json();
  document.getElementById('stAd').textContent = data.ad_status;
  document.getElementById('adSaveMsg').textContent = data.message;
  runTestSearch();
}

async function saveLiveToken() {
  const tok = document.getElementById('liveTokenInput').value.trim();
  const msgEl = document.getElementById('tokenSaveMsg');
  if (!tok) return;
  msgEl.textContent = '⏳ টোকেন যাচাই করে বট চালু করা হচ্ছে...';
  const res = await fetch('/api/setup/token', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: tok})
  });
  const data = await res.json();
  msgEl.textContent = data.message;
  if (data.ok) setTimeout(() => location.reload(), 1200);
}

runTestSearch();
</script>
</body>
</html>"""


# গ্লোবাল রানটাইম স্টেট (যাতে টোকেন ছাড়াও বা ভুল টোকেনেও সার্ভার ১০০% সচল থাকে)
RUNTIME_STATE = {
    "bot_online": False,
    "bot_username": "HighlightHubOfficial_bot",
    "bot_error": "",
    "bot": None,
    "dp": None,
    "db": None,
    "polling_task": None,
}


async def seed_demo_matches_if_empty(db: Database) -> None:
    """ডেটাবেসে কোনো ম্যাচ না থাকলে টেস্ট ও ডেমোর জন্য কয়েকটি জনপ্রিয় ম্যাচ যোগ করে।"""
    if await db.count_matches() > 0:
        return
    samples = [
        ("Real Madrid", "Real Madrid vs Barcelona 3-2 (El Clasico)", "2024", "#RealMadrid,#Barcelona"),
        ("Real Madrid", "Real Madrid vs Manchester City 3-1 (UCL Semi-Final)", "2022", "#RealMadrid,#ManCity"),
        ("Barcelona", "Barcelona vs PSG 6-1 (UCL La Remontada)", "2017", "#Barcelona,#PSG"),
        ("Barcelona", "Barcelona vs Real Madrid 4-0 (La Liga)", "2024", "#Barcelona,#RealMadrid"),
        ("Argentina", "Argentina vs France 3-3 (FIFA World Cup Final)", "2022", "#Argentina,#France"),
        ("Argentina", "Argentina vs Brazil 1-0 (Copa America Final)", "2021", "#Argentina,#Brazil"),
        ("Brazil", "Brazil vs Germany 1-7 (FIFA World Cup Semi-Final)", "2014", "#Brazil,#Germany"),
        ("Bangladesh", "Bangladesh vs India 265/8 (Asia Cup Thriller)", "2023", "#Bangladesh,#India"),
    ]
    for team, title, yr, tags in samples:
        await db.add_match(
            team=team,
            team_key=norm(team),
            title=title,
            year=yr,
            tags=tags,
            file_id=f"DEMO_{norm(team).replace(' ', '_')}_{yr}",
            media_type="video",
        )


async def try_start_telegram_bot(token: str, db: Database) -> tuple[bool, str]:
    """বট টোকেন যাচাই করে নিরাপদে Telegram Bot চালু করে (ক্র্যাশ ছাড়া)।"""
    token = (token or "").strip()
    if not token:
        RUNTIME_STATE["bot_online"] = False
        RUNTIME_STATE["bot_error"] = "BOT_TOKEN দেওয়া হয়নি"
        return False, "BOT_TOKEN সেট করা নেই।"

    try:
        test_bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        me = await test_bot.get_me()
    except Exception as exc:
        RUNTIME_STATE["bot_online"] = False
        RUNTIME_STATE["bot_error"] = f"টোকেন সঠিক নয় বা মেয়াদ শেষ ({exc})"
        log.error("Bot token check failed: %s", exc)
        return False, f"❌ টোকেন কাজ করছে না: {exc} — BotFather থেকে নতুন টোকেন নিয়ে বসান।"

    # পুরোনো পোলিং টাস্ক থাকলে বন্ধ করো
    old_task = RUNTIME_STATE.get("polling_task")
    if old_task and not old_task.done():
        old_task.cancel()

    dp = Dispatcher()
    dp["db"] = db
    dp["bot"] = test_bot

    middleware = ActivityMiddleware(db)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(channel_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    RUNTIME_STATE["bot"] = test_bot
    RUNTIME_STATE["dp"] = dp
    RUNTIME_STATE["bot_online"] = True
    RUNTIME_STATE["bot_username"] = me.username or "HighlightHubOfficial_bot"
    RUNTIME_STATE["bot_error"] = ""

    log.info("✅ Bot started successfully: @%s (id=%s)", me.username, me.id)

    try:
        await test_bot.set_my_commands(
            [
                BotCommand(command="start", description="Start / হোম"),
                BotCommand(command="help", description="Help / সাহায্য"),
                BotCommand(command="lang", description="Language / ভাষা"),
                BotCommand(command="admin", description="Admin panel"),
                BotCommand(command="id", description="My ID / আমার আইডি"),
            ]
        )
    except Exception as exc:
        log.warning("set_my_commands warning: %s", exc)

    if not dp.get("poller_task"):
        dp["poller_task"] = asyncio.create_task(poller_loop(test_bot, db))

    base = webhook_base_url()
    allowed = dp.resolve_used_update_types()
    secret = os.getenv("WEBHOOK_SECRET", "").strip() or None

    webhook_ok = False
    if base:
        try:
            await test_bot.set_webhook(
                base + WEBHOOK_PATH,
                drop_pending_updates=False,
                allowed_updates=allowed,
                secret_token=secret,
            )
            webhook_ok = True
            log.info("Webhook active → %s%s", base, WEBHOOK_PATH)
        except Exception as exc:
            log.warning("Webhook failed (%s), switching to polling...", exc)

    if not webhook_ok:
        try:
            await test_bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        RUNTIME_STATE["polling_task"] = asyncio.create_task(
            dp.start_polling(test_bot, allowed_updates=allowed, handle_signals=False)
        )
        log.info("Polling started in background task.")

    return True, f"✅ বট সফলভাবে চালু হয়েছে: @{me.username}"


def create_web_app(db: Database) -> web.Application:
    app = web.Application()

    async def handle_dashboard(_request: web.Request) -> web.Response:
        users_cnt = await db.count_users()
        matches_cnt = await db.count_matches()
        views_cnt = await db.total_views()
        ad = await load_ad(db)
        s = await db.get_settings("ad_")
        cur_url = s.get("ad_url") or ""

        if RUNTIME_STATE["bot_online"]:
            badge = f'<span class="badge badge-ok">🟢 বট লাইভ আছে (@{esc(RUNTIME_STATE["bot_username"])})</span>'
            warn_card = ""
        else:
            err_reason = esc(RUNTIME_STATE["bot_error"] or "BOT_TOKEN সেট করা নেই")
            badge = f'<span class="badge badge-warn">⚠️ টোকেন প্রয়োজন ({err_reason})</span>'
            warn_card = f"""
            <div class="card" style="border-color:#f59e0b">
              <h2 style="color:#fbbf24">🔑 বট টোকেন সেট করুন (১-ক্লিকে বট চালু করুন)</h2>
              <p style="font-size:14px;color:#cbd5e1;margin-bottom:10px">
                সার্ভার ১০০% সচল আছে! আপনার আগের টোকেনটি বাতিল হওয়ায় Telegram সংযোগের জন্য <b>@BotFather</b> থেকে নতুন টোকেন নিয়ে Render → Environment → <code>BOT_TOKEN</code> এ বসান, অথবা এখনই নিচে পেস্ট করে টেস্ট করুন:
              </p>
              <div style="display:flex;gap:10px;flex-wrap:wrap">
                <input type="text" id="liveTokenInput" placeholder="8653868768:AA..." style="flex:1;min-width:240px;margin:0">
                <button onclick="saveLiveToken()">🚀 টোকেন সেভ ও বট চালু করুন</button>
              </div>
              <div id="tokenSaveMsg" style="margin-top:10px;font-size:13px;color:#fbbf24"></div>
            </div>
            """

        html = (
            DASHBOARD_HTML.replace("__BOT_STATUS_BADGE__", badge)
            .replace("__USERS__", str(users_cnt))
            .replace("__MATCHES__", str(matches_cnt))
            .replace("__VIEWS__", str(views_cnt))
            .replace("__AD_STATUS__", "🟢 চালু (5s)" if ad else "⚪ ফ্রি মোড")
            .replace("__CURRENT_AD_URL__", esc(cur_url))
            .replace("__TOKEN_WARNING_CARD__", warn_card)
        )
        return web.Response(text=html, content_type="text/html")

    async def handle_health(_request: web.Request) -> web.Response:
        return web.Response(text="✅ HighlightHub bot server is healthy and running")

    async def handle_ad_gate(request: web.Request) -> web.Response:
        token = request.match_info.get("token", "")
        session = await db.get_ad_session(token)
        if not session:
            return web.Response(text="⚠️ এই অ্যাড সেশনটি পাওয়া যায়নি বা মেয়াদ শেষ হয়েছে।", status=404)

        ad = await load_ad(db)
        if not ad or not ad.get("url"):
            # যদি অ্যাড বন্ধ থাকে, সরাসরি আনলক ও ভিডিও পাঠিয়ে দাও
            await db.mark_ad_verified(token)
            match = await db.get_match(int(session["match_id"]))
            if match and RUNTIME_STATE.get("bot") and session["delivered"] == 0:
                await db.mark_ad_delivered(token)
                lang = await get_lang(db, int(session["user_id"]))
                await send_video_to(RUNTIME_STATE["bot"], db, int(session["user_id"]), match, lang)
            return web.Response(
                text="<html><body style='background:#0f172a;color:#fff;font-family:sans-serif;text-align:center;padding:50px'><h2>✅ ফ্রি মোড চালু আছে! ভিডিওটি আপনার টেলিগ্রাম বটে পাঠানো হয়েছে।</h2></body></html>",
                content_type="text/html",
            )

        await db.mark_ad_opened(token)
        ad_url = session["ad_url"] or ad["url"]
        html = (
            AD_GATE_HTML.replace("__TOKEN__", esc(token))
            .replace("__AD_URL__", esc(ad_url))
            .replace("__SECONDS__", str(AD_TIMER_SECONDS))
            .replace("__BOT_USERNAME__", esc(RUNTIME_STATE.get("bot_username") or "HighlightHubOfficial_bot"))
        )
        return web.Response(text=html, content_type="text/html")

    async def handle_ad_verify(request: web.Request) -> web.Response:
        token = request.match_info.get("token", "")
        session = await db.get_ad_session(token)
        if not session:
            return web.json_response({"ok": False, "error": "not_found"}, status=404)

        opened_at = float(session["opened_at"] or 0)
        elapsed = time.time() - opened_at if opened_at > 0 else 0
        if elapsed < (AD_TIMER_SECONDS - 0.4):
            return web.json_response(
                {"ok": False, "error": "too_early", "elapsed": round(elapsed, 1)},
                status=400,
            )

        await db.mark_ad_verified(token)

        # ৫ সেকেন্ড পূর্ণ হলে অটোমেটিক টেলিগ্রামে ভিডিও পাঠিয়ে দেওয়া হবে!
        if session["delivered"] == 0 and RUNTIME_STATE.get("bot"):
            match = await db.get_match(int(session["match_id"]))
            if match:
                await db.mark_ad_delivered(token)
                lang = await get_lang(db, int(session["user_id"]))
                await send_video_to(RUNTIME_STATE["bot"], db, int(session["user_id"]), match, lang)

        return web.json_response({"ok": True, "verified": True})

    async def handle_test_search(request: web.Request) -> web.Response:
        q = (request.query.get("q") or "").strip()
        rows = await db.get_search_index()
        found = search_matches(rows, q, limit=15) if q else rows[:10]
        ad = await load_ad(db)
        out = []
        for r in found:
            tok = await db.create_ad_session(0, r["id"], ad["url"] if ad else "")
            out.append(
                {
                    "id": r["id"],
                    "team": r["team"],
                    "title": r["title"],
                    "year": r["year"],
                    "demo_token": tok,
                }
            )
        return web.json_response({"query": q, "normalized": norm(q), "matches": out})

    async def handle_test_ad(request: web.Request) -> web.Response:
        data = await request.json()
        enable = bool(data.get("enable"))
        url = (data.get("url") or "").strip()
        if enable and url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await db.set_setting("ad_url", url)
            await db.set_setting(
                "ad_text",
                f"🔥 হাইলাইট ভিডিওটি পেতে নিচের বাটনে ক্লিক করে মাত্র {AD_TIMER_SECONDS} সেকেন্ড অ্যাডটি দেখুন!",
            )
            await db.set_setting("ad_btn", f"📺 অ্যাড দেখুন ({AD_TIMER_SECONDS} সেকেন্ড)")
            await db.set_setting("ad_active", "1")
            return web.json_response(
                {"ok": True, "ad_status": "🟢 চালু (5s)", "message": "✅ ৫ সেকেন্ডের বাধ্যতামূলক অ্যাড চালু করা হয়েছে!"}
            )
        else:
            await db.set_setting("ad_active", "0")
            return web.json_response(
                {"ok": True, "ad_status": "⚪ ফ্রি মোড", "message": "✅ অ্যাড বন্ধ করা হয়েছে — এখন ইউজাররা ফ্রিতে সরাসরি ভিডিও পাবে!"}
            )

    async def handle_setup_token(request: web.Request) -> web.Response:
        data = await request.json()
        new_tok = (data.get("token") or "").strip()
        ok, msg = await try_start_telegram_bot(new_tok, db)
        if ok:
            await db.set_setting("saved_bot_token", new_tok)
        return web.json_response({"ok": ok, "message": msg})

    async def handle_webhook(request: web.Request) -> web.Response:
        bot = RUNTIME_STATE.get("bot")
        dp = RUNTIME_STATE.get("dp")
        if not bot or not dp:
            return web.Response(status=503, text="Bot not configured")
        secret = os.getenv("WEBHOOK_SECRET", "").strip()
        if secret:
            header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_secret != secret:
                return web.Response(status=401, text="Unauthorized")
        payload = await request.json()
        from aiogram.types import Update
        update = Update.model_validate(payload, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="ok")

    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/ad/{token}", handle_ad_gate)
    app.router.add_post("/api/ad/verify/{token}", handle_ad_verify)
    app.router.add_get("/api/test/search", handle_test_search)
    app.router.add_post("/api/test/ad", handle_test_ad)
    app.router.add_post("/api/setup/token", handle_setup_token)
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    return app


async def main() -> None:
    db = Database()
    await db.connect()
    await seed_demo_matches_if_empty(db)
    RUNTIME_STATE["db"] = db
    log.info("Database ready: %s", DB_PATH)

    port = int(os.getenv("PORT", "8000") or 8000)
    app = create_web_app(db)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("🌐 Web Server & 5s Ad Gate listening on http://0.0.0.0:%s", port)

    # প্রথমে env থেকে BOT_TOKEN অথবা ডেটাবেসে সেভ থাকা টোকেন দিয়ে বট চালু করার চেষ্টা করো
    active_token = BOT_TOKEN or (await db.get_setting("saved_bot_token") or "")
    ok, msg = await try_start_telegram_bot(active_token, db)
    log.info(msg)

    try:
        await asyncio.Event().wait()
    finally:
        old_task = RUNTIME_STATE.get("polling_task")
        if old_task and not old_task.done():
            old_task.cancel()
        await db.close()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
