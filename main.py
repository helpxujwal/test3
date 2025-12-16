import os
import asyncio
import logging
import json
import re
import time
from datetime import datetime, timedelta, timezone
from threading import Thread
from flask import Flask, request, render_template_string, redirect, url_for, session
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.tl.types import ChannelParticipantsAdmins

# --- IMPORT SCRAPER ---
import scraper

# --- LOGGING SETUP ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
API_ID = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
USER_SESSION = os.environ.get("USER_SESSION", "")

# Web Dashboard Config
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")

# Support & Owner Links
SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP", "https://t.me/TushxEternal")
SUPPORT_CHANNEL = os.environ.get("SUPPORT_CHANNEL", "https://t.me/SarkariJobDiscussions")
OWNER_LINK = os.environ.get("OWNER_LINK", "https://t.me/Waitdaddy")

# 1. CRITICAL: Check if Session exists
if not USER_SESSION:
    logger.critical("❌ ERROR: 'USER_SESSION' Environment Variable is MISSING.")
    exit(1)

USER_SESSION = USER_SESSION.strip().replace("\n", "").replace(" ", "")
API_ID = int(API_ID) if API_ID.isdigit() else 0

# Source Channel
SOURCE_INPUT = os.environ.get("SOURCE_CHANNEL", "SarkariExam_info").strip()
if "t.me/" in SOURCE_INPUT:
    SOURCE_CHANNEL = SOURCE_INPUT.split("t.me/")[-1].strip("/")
else:
    SOURCE_CHANNEL = SOURCE_INPUT

LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]

# --- DATABASE ---
DB_FILE = "database.json"
SENT_MSGS = set()

# Default Ad Config
DEFAULT_AD = {
    "active": False,
    "content": "Advertise here!",
    "interval": 60,
    "limit": 0,
    "sent": 0,
    "last_sent": 0
}

def load_db():
    default_db = {"groups": {}, "users": [], "ads": DEFAULT_AD, "settings": {"last_support_promo": 0}}
    if not os.path.exists(DB_FILE):
        return default_db
    with open(DB_FILE, 'r') as f:
        try:
            data = json.load(f)
            if isinstance(data.get("groups"), list):
                new_groups = {}
                for gid in data["groups"]:
                    new_groups[str(gid)] = {"interval": 30, "last_post": 0, "active": True}
                data["groups"] = new_groups
            
            if "ads" not in data: data["ads"] = DEFAULT_AD
            if "settings" not in data: data["settings"] = {"last_support_promo": 0}
            return data
        except:
            return default_db

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f)

db = load_db()

# --- INITIALIZATION ---
logger.info("--- Starting Job Alert Bot ---")
try:
    user_client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
    bot_client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
except Exception as e:
    logger.critical(f"❌ Failed to initialize Telegram Clients: {e}")
    exit(1)

# --- FLASK APP ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

HTML_LOGIN = """
<!doctype html>
<title>Login</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#f0f2f5}form{background:white;padding:2rem;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}input{display:block;margin-bottom:1rem;padding:0.5rem;width:200px}button{background:#0088cc;color:white;border:none;padding:0.5rem 1rem;cursor:pointer;width:100%}</style>
<form method=post>
  <h3>Bot Dashboard</h3>
  <input type=password name=password placeholder="Enter Password" required>
  <button type=submit>Login</button>
</form>
"""

HTML_DASHBOARD = """
<!doctype html>
<title>Ad Manager</title>
<style>body{font-family:sans-serif;padding:2rem;max-width:800px;margin:0 auto;background:#f9f9f9}
.card{background:white;padding:1.5rem;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,0.05);margin-bottom:1rem}
label{display:block;margin-top:1rem;font-weight:bold}
input,textarea{width:100%;padding:0.5rem;margin-top:0.5rem;border:1px solid #ddd;border-radius:4px}
button{background:#28a745;color:white;border:none;padding:0.75rem 1.5rem;margin-top:1rem;cursor:pointer;border-radius:4px}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem}
.stat{text-align:center;background:#eef;padding:1rem;border-radius:4px}
</style>
<h1>📢 Ad Manager</h1>
<div class="stats card">
    <div class="stat"><h3>{{ groups }}</h3><small>Active Groups</small></div>
    <div class="stat"><h3>{{ users }}</h3><small>Active Users</small></div>
    <div class="stat"><h3>{{ ad_sent }} / {{ ad_limit }}</h3><small>Ads Sent</small></div>
</div>

<form method=post class="card">
    <h3>Configure Advertisement</h3>
    <label>Ad Content (HTML/Markdown supported)</label>
    <textarea name="content" rows="5">{{ ad_content }}</textarea>
    
    <label>Interval (Minutes)</label>
    <input type="number" name="interval" value="{{ ad_interval }}">
    
    <label>Max Sends (Limit)</label>
    <input type="number" name="limit" value="{{ ad_limit }}">
    
    <label>
        <input type="checkbox" name="active" style="width:auto" {% if ad_active %}checked{% endif %}> Enable Advertisement
    </label>
    
    <button type=submit>Update Settings</button>
</form>
"""

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        if request.form.get('password') == WEB_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('manager'))
        else:
            return "Invalid Password"
            
    if session.get('logged_in'): return redirect(url_for('manager'))
    return render_template_string(HTML_LOGIN)

@app.route('/manager', methods=['GET', 'POST'])
def manager():
    if not session.get('logged_in'): return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        db['ads']['content'] = request.form.get('content')
        db['ads']['interval'] = int(request.form.get('interval', 60))
        db['ads']['limit'] = int(request.form.get('limit', 0))
        db['ads']['active'] = 'active' in request.form
        save_db(db)
        return redirect(url_for('manager'))

    return render_template_string(HTML_DASHBOARD, 
        groups=len(db['groups']), 
        users=len(db['users']),
        ad_content=db['ads']['content'],
        ad_interval=db['ads']['interval'],
        ad_limit=db['ads']['limit'],
        ad_active=db['ads']['active'],
        ad_sent=db['ads']['sent']
    )

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- HELPER FUNCTIONS ---

async def is_admin(chat_id, user_id):
    """
    Robust Admin Check:
    1. Checks if user is Global Bot Owner (ADMIN_IDS)
    2. Checks if user is Anonymous Admin (Group ID = User ID)
    3. Fetches FULL Admin list from Telegram to verify user ID
    """
    if user_id in ADMIN_IDS:
        return True
    if user_id == chat_id:
        return True
    try:
        admins = await bot_client.get_participants(chat_id, filter=ChannelParticipantsAdmins)
        admin_ids = [admin.id for admin in admins]
        if user_id in admin_ids:
            return True
        chat = await bot_client.get_entity(chat_id)
        if hasattr(chat, 'creator') and chat.creator:
             pass
    except Exception as e:
        logger.warning(f"Admin check warning for {user_id} in {chat_id}: {e}")
    return False

def update_group(chat_id, action="add"):
    str_id = str(chat_id)
    if action == "add":
        if str_id not in db["groups"]:
            db["groups"][str_id] = {"interval": 30, "last_post": 0, "active": True}
            save_db(db)
            return True
    elif action == "remove":
        if str_id in db["groups"]:
            del db["groups"][str_id]
            save_db(db)
            return True
    return False

async def setup_bot_commands():
    try:
        public_commands = [
            types.BotCommand("start", "Start Alerts"),
            types.BotCommand("stop", "Stop Alerts"),
            types.BotCommand("set", "Set Interval"),
            types.BotCommand("fetch", "Fetch Latest Job (Scraper)")
        ]
        
        await bot_client(functions.bots.SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='en',
            commands=public_commands
        ))
        
        owner_commands = public_commands + [
            types.BotCommand("broadcast", "Broadcast All"),
            types.BotCommand("broadcastg", "Broadcast Groups"),
            types.BotCommand("broadcastp", "Broadcast Users")
        ]
        
        for admin_id in ADMIN_IDS:
            try:
                await bot_client(functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopePeer(types.InputPeerUser(admin_id, 0)),
                    lang_code='en',
                    commands=owner_commands
                ))
            except Exception as e:
                logger.error(f"Failed to set owner commands for {admin_id}: {e}")
            
        logger.info("✅ Bot commands updated.")
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")

async def get_user_info(user_id):
    try:
        u = await bot_client.get_entity(user_id)
        username = f"@{u.username}" if u.username else "No Username"
        return f"👤 **Name:** {u.first_name} {u.last_name or ''}\n🆔 **ID:** `{u.id}`\n🔗 **Username:** {username}"
    except:
        return f"🆔 **ID:** `{user_id}` (Info Hidden)"

# --- BOT HANDLERS ---

@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    chat_id = event.chat_id
    me = await bot_client.get_me()
    
    buttons = [
        [Button.url("📢 Support Channel", SUPPORT_CHANNEL), Button.url("👥 Support Group", SUPPORT_GROUP)],
        [Button.url("➕ Add to Group", f"https://t.me/{me.username}?startgroup=true")],
        [Button.url("👤 Owner", OWNER_LINK)]
    ]

    if event.is_private:
        if event.sender_id not in db["users"]:
            db["users"].append(event.sender_id)
            save_db(db)
            try:
                user_info = await get_user_info(event.sender_id)
                await bot_client.send_message(LOG_CHANNEL, f"🆕 **New User Started Bot**\n\n{user_info}")
            except: pass
        
        await event.respond(
            "👋 **Hello! I am the Job Alert Bot.**\n\n"
            "I forward alerts from **SarkariExam**.\n"
            "I can also scrape live jobs using `/fetch`.\n"
            "Add me to your group and **Promote to Admin**.",
            buttons=buttons
        )
    else:
        if not await is_admin(chat_id, event.sender_id):
            await event.respond("❌ **Permission Denied:** Only Group Admins (or Owner) can use this command.", buttons=None)
            return

        if await is_admin(chat_id, me.id):
            update_group(chat_id, "add")
            await event.respond(
                "✅ **Bot Active!**\n"
                "• Default Interval: 30 mins\n"
                "• Change: `/set 15` (min 10 mins)\n"
                "• Stop: `/stop`",
                buttons=buttons
            )
        else:
            await event.respond("⚠️ **Action Required:** Make me **Admin** to receive alerts.")

@bot_client.on(events.NewMessage(pattern='/set'))
async def set_interval(event):
    if event.is_private: return
    
    if not (await is_admin(event.chat_id, event.sender_id)):
        await event.respond("❌ Only Group Admins can change settings.")
        return

    try:
        args = event.text.split()
        if len(args) < 2:
            await event.respond("Usage: `/set 30` (minutes)")
            return
            
        mins = int(args[1])
        if mins < 1:
            await event.respond("⚠️ Minimum interval is 1 minute.")
            return
            
        str_id = str(event.chat_id)
        if str_id in db["groups"]:
            db["groups"][str_id]["interval"] = mins
            save_db(db)
            await event.respond(f"✅ Interval set to **{mins} minutes**.")
        else:
            await event.respond("⚠️ Bot not active. Type `/start` first.")
            
    except ValueError:
        await event.respond("❌ Please enter a valid number.")

@bot_client.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    if not event.is_private:
        if not (await is_admin(event.chat_id, event.sender_id)):
            await event.respond("❌ Only Group Admins can use this.")
            return
            
    if event.is_private:
        if event.sender_id in db["users"]:
             db["users"].remove(event.sender_id)
             save_db(db)
             await event.respond("🔕 Stopped.")
    else:
        update_group(event.chat_id, "remove")
        await event.respond("🔕 **Stopped.** Type `/start` to resume.")

@bot_client.on(events.ChatAction)
async def on_join(event):
    if event.user_added or event.user_joined:
        if event.user_id == (await bot_client.get_me()).id:
            chat = await event.get_chat()
            await bot_client.send_message(
                chat.id, 
                "👋 **Hi!** Promote me to **Admin** and type `/start`.",
                buttons=[Button.url("👤 Owner", OWNER_LINK)]
            )
            try:
                try:
                    invite = await bot_client(functions.messages.ExportChatInviteRequest(chat.id))
                    link = invite.link
                except: link = "No Link (Bot needs Admin)"
                
                added_by_info = "Unknown"
                if event.added_by:
                    added_by_info = await get_user_info(event.added_by)
                
                log_msg = (
                    f"➕ **Bot Added to Group**\n\n"
                    f"📛 **Group:** {chat.title}\n"
                    f"🆔 **Group ID:** `{chat.id}`\n"
                    f"🔗 **Link:** {link}\n\n"
                    f"👮 **Added By:**\n{added_by_info}"
                )
                await bot_client.send_message(LOG_CHANNEL, log_msg)
            except Exception as e:
                logger.error(f"Log Error: {e}")

# --- SCRAPER HANDLER ---

@bot_client.on(events.NewMessage(pattern='/fetch'))
async def fetch_handler(event):
    """Fetches the latest job from the website using scraper.py"""
    # Optional: Restrict to admins or specific users
    if not event.is_private and not await is_admin(event.chat_id, event.sender_id):
         await event.respond("❌ Only Admins can use this.")
         return

    msg = await event.respond("🔍 **Scanning Sarkari Result...**")
    
    # 1. Get List
    jobs = scraper.get_latest_jobs()
    if not jobs:
        await msg.edit("❌ Could not fetch jobs from website.")
        return

    # 2. Get Details of the very latest job
    latest_job = jobs[0]
    await msg.edit(f"📥 **Fetching details for:**\n`{latest_job['title']}`")
    
    details = scraper.get_job_details(latest_job['url'])
    
    if not details:
        await msg.edit("❌ Failed to parse details.")
        return

    # 3. Format Message
    response_text = f"🔥 **{details['title']}**\n\n"
    
    if details['dates']:
        response_text += "📅 **Dates:**\n" + "\n".join([f"• {x}" for x in details['dates'][:3]]) + "\n\n"
        
    if details['fees']:
        response_text += "💰 **Fees:**\n" + "\n".join([f"• {x}" for x in details['fees'][:3]]) + "\n\n"

    buttons = []
    for label, link in details['links'].items():
        buttons.append([Button.url(label, link)])

    await msg.delete()
    await event.respond(response_text, buttons=buttons)


# --- SCHEDULER & BROADCAST ---

@bot_client.on(events.NewMessage(pattern='/broadcast'))
async def broadcast_handler(event):
    if event.sender_id not in ADMIN_IDS: return
    if not event.reply_to_msg_id:
        await event.respond("Reply to a message to broadcast.")
        return
        
    reply_msg = await event.get_reply_message()
    command = event.text.split()[0]
    
    targets = []
    if command == "/broadcastg": targets = list(db["groups"].keys())
    elif command == "/broadcastp": targets = db["users"]
    else: targets = list(db["groups"].keys()) + db["users"]
    
    msg = await event.respond(f"🚀 Sending to {len(targets)} targets...")
    count = 0
    for chat_id in targets:
        try:
            await bot_client.send_message(int(chat_id), reply_msg)
            count += 1
            await asyncio.sleep(0.1)
        except: pass
    await msg.edit(f"✅ Sent to {count} recipients.")

async def global_scheduler():
    logger.info("⏳ Scheduler Started...")
    while True:
        try:
            now = time.time()
            ist_offset = timezone(timedelta(hours=5, minutes=30))
            today = datetime.now(ist_offset).date()
            recent_posts = []
            
            async for msg in user_client.iter_messages(SOURCE_CHANNEL, limit=20):
                if not msg.date: continue
                msg_date = msg.date.astimezone(ist_offset).date()
                if msg_date < today: break
                recent_posts.append(msg)
            
            recent_posts.reverse()

            for gid, settings in db["groups"].items():
                if not settings.get("active", True): continue
                last_post = settings.get("last_post", 0)
                interval_sec = settings.get("interval", 30) * 60
                
                if now - last_post >= interval_sec:
                    sent_something = False
                    for msg in recent_posts:
                        cache_key = f"{gid}_{msg.id}"
                        if cache_key in SENT_MSGS: continue
                        try:
                            await bot_client.send_message(int(gid), msg)
                            SENT_MSGS.add(cache_key)
                            sent_something = True
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            if "permission" in str(e).lower(): settings["active"] = False
                    
                    if sent_something: db["groups"][gid]["last_post"] = now
            
            ad = db.get("ads", DEFAULT_AD)
            if ad.get("active"):
                if now - ad.get("last_sent", 0) >= (ad["interval"] * 60):
                    if ad["sent"] < ad["limit"]:
                        for gid in db["groups"]:
                            try: await bot_client.send_message(int(gid), ad["content"], parse_mode='html')
                            except: pass
                        ad["sent"] += 1
                        ad["last_sent"] = now
            
            last_promo = db["settings"].get("last_support_promo", 0)
            if now - last_promo >= 86400:
                promo_text = f"📢 **Daily Reminder:**\nJoin our Support Group!\n{SUPPORT_GROUP}"
                for gid in db["groups"]:
                    try: await bot_client.send_message(int(gid), promo_text)
                    except: pass
                db["settings"]["last_support_promo"] = now
            
            save_db(db)
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Scheduler Error: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(user_client.connect())
        if not loop.run_until_complete(user_client.is_user_authorized()): raise Exception("Invalid USER_SESSION")
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)
    try: loop.run_until_complete(user_client(functions.channels.JoinChannelRequest(SOURCE_CHANNEL)))
    except: pass
    loop.run_until_complete(setup_bot_commands())
    loop.create_task(global_scheduler())
    loop.run_forever()
