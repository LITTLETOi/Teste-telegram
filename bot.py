import logging
import datetime
import requests
import json
import asyncio
import nest_asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    filters,
)

nest_asyncio.apply()

# ========= CONFIG =========
BOT_TOKEN = "8191885274:AAFj8sZh4lClGedMRP80MDooMtIPE6rPo28"
API_URL_TEMPLATE = "https://likes.ffgarena.cloud/api/v2/likes?uid={uid}&amount_of_likes=100&auth=vortex"

ADMIN_IDS = [8183673253]
ALLOWED_GROUPS = [-4781844651]
vip_users = [8183673253]
DEFAULT_DAILY_LIMIT = 30

# ========= STATE =========
allowed_groups = set(ALLOWED_GROUPS)
group_usage = {}
group_limits = {}
last_reset_date = {}
user_data = {}
promotion_message = ""
command_enabled = True

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= HELPERS =========
async def get_user_name(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    try:
        user = await context.bot.get_chat(user_id)
        return user.full_name or f"User {user_id}"
    except:
        return f"User {user_id}"

def is_group(update: Update):
    return update.message.chat.type in ["group", "supergroup"]

def get_today():
    return datetime.date.today().strftime("%Y-%m-%d")

def reset_if_needed(group_id: int):
    today = datetime.date.today()
    if last_reset_date.get(group_id) != today:
        group_usage[group_id] = 0
        last_reset_date[group_id] = today

def get_limit(group_id: int):
    return group_limits.get(group_id, DEFAULT_DAILY_LIMIT)

def check_command_enabled(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not command_enabled and update.message.text != "/on":
            await update.message.reply_text("🚫 Commands are currently disabled.")
            return
        return await func(update, context)
    return wrapper

# ========= COMMANDS =========
@check_command_enabled
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Use /like <uid> to get Free Fire likes.")

@check_command_enabled
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📘 HELP MENU

🔹 Core Commands:
/like <uid> - Send likes
/check - Your usage today
/groupstatus - Group usage stats
/remain - Today's user count

🔹 VIP Management:
/setvip <user_id> - Add VIP
/removevip <user_id> - Remove VIP
/viplist - Show VIP users
/setpromotion <text> - Set promo msg

🔹 User Management:
/userinfo <user_id> - Get user details
/stats - Usage statistics
/feedback <msg> - Send feedback

🔹 System:
/status - Bot status
/on - Enable commands
/off - Disable commands
"""
    await update.message.reply_text(help_text)

@check_command_enabled
async def like(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return

    group_id = update.effective_chat.id
    if group_id not in allowed_groups:
        return

    reset_if_needed(group_id)
    used = group_usage.get(group_id, 0)
    limit = get_limit(group_id)

    if used >= limit:
        await update.message.reply_text("❌ Group daily like limit reached!")
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text("⚠️ Usage: /like <uid>")
        return

    processing_msg = await update.message.reply_text("⏳ Processing your request...")

    uid = args[0]
    user_id = update.effective_user.id
    today = get_today()
    is_vip = user_id in vip_users

    if not is_vip:
        user_info = user_data.get(user_id, {})
        if user_info.get("date") == today and user_info.get("count", 0) >= 1:
            await processing_msg.edit_text("⛔ You have used your free like today.")
            return
        user_data[user_id] = {"date": today, "count": user_info.get("count", 0)}

    try:
        response = requests.get(API_URL_TEMPLATE.format(uid=uid))
        data = response.json()
        logger.info(f"API response: {data}")
    except Exception as e:
        logger.error(f"API error: {e}")
        await processing_msg.edit_text("🚨 API Error! Try again later.")
        return

    if data.get("LikesGivenByAPI") == 0:
        await processing_msg.edit_text("⚠️ UID has already reached max likes today.")
        return

    required_keys = ["PlayerNickname", "UID", "LikesbeforeCommand", "LikesafterCommand", "LikesGivenByAPI"]
    if not all(key in data for key in required_keys):
        await processing_msg.edit_text("⚠️ Invalid UID or unable to fetch details.🙁 Please check UID or try again later.")
        logger.warning(f"Incomplete API response for UID {uid}: {data}")
        return

    if not is_vip:
        user_data[user_id]["count"] += 1
    group_usage[group_id] = group_usage.get(group_id, 0) + 1

    text = (
        f"✅ Like Sent Successfully!\n\n"
        f"👤 Name: {data['PlayerNickname']}\n"
        f"🆔 UID: {data['UID']}\n"
        f"🤡 Before: {data['LikesbeforeCommand']}\n"
        f"🗿 After: {data['LikesafterCommand']}\n"
        f"🎉 Given: {data['LikesGivenByAPI']}"
    )
    if promotion_message:
        text += f"\n\n📢 {promotion_message}"

    try:
        user_photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if user_photos.total_count > 0:
            photo_file = await user_photos.photos[0][-1].get_file()
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_file.file_id,
                caption=text,
                reply_to_message_id=update.message.message_id
            )
            await processing_msg.delete()
        else:
            await processing_msg.edit_text(text)
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await processing_msg.edit_text(text)

@check_command_enabled
async def setpromotion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in vip_users:
        await update.message.reply_text("⛔ Unauthorized")
        return
    global promotion_message
    promotion_message = " ".join(context.args)
    await update.message.reply_text("✅ Promotion message set!")

@check_command_enabled
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = get_today()
    user_info = user_data.get(user_id, {})
    user_date = user_info.get("date")
    count = user_info.get("count", 0)

    status = "UNLIMITED (VIP)" if user_id in vip_users else (
        f"{count}/1 ✅ Used" if user_date == today else "0/1 ❌ Not Used"
    )

    await update.message.reply_text(
        f"👤 DEAR {update.effective_user.first_name}, YOUR STATUS\n\n"
        f"🎯 FREE REQUEST: {status}"
    )

@check_command_enabled
async def groupstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    group_id = update.effective_chat.id
    count = group_usage.get(group_id, 0)
    await update.message.reply_text(
        f"📊 Group Usage Status\n\n"
        f"🆔 Group ID: {group_id}\n"
        f"✅ Likes used today: {count}/{get_limit(group_id)}\n"
        f"⏰ Reset: 4:30 AM daily"
    )

@check_command_enabled
async def remain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today()
    used_users = [uid for uid, data in user_data.items() if data.get("date") == today]
    await update.message.reply_text(
        f"📊 Today's Usage\n\n"
        f"✅ Users used likes: {len(used_users)}\n"
        f"📅 Date: {today}"
    )

@check_command_enabled
async def allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized command usage.")
        return
    try:
        gid = int(context.args[0]) if context.args else update.effective_chat.id
        allowed_groups.add(gid)
        await update.message.reply_text(f"✅ Group {gid} allowed.")
    except Exception as e:
        logger.error(f"Error in allow command: {e}")
        await update.message.reply_text("⚠️ Invalid group ID or usage. Use /allow or /allow <group_id>.")

@check_command_enabled
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized command usage.")
        return
    try:
        gid = int(context.args[0]) if context.args else update.effective_chat.id
        if gid not in allowed_groups:
            await update.message.reply_text(f"❌ Group {gid} is not in the allowed list.")
            return
        allowed_groups.discard(gid)
        await update.message.reply_text(f"❌ Group {gid} removed from allowed list.")
    except Exception as e:
        logger.error(f"Error in remove command: {e}")
        await update.message.reply_text("⚠️ Error removing group. Usage: /remove OR /remove <group_id>")

@check_command_enabled
async def groupreset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized command usage.")
        return
    group_usage.clear()
    await update.message.reply_text("✅ Group usage reset!")

@check_command_enabled
async def setremain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized command usage.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ Usage: /setremain <number>")
        return
    new_limit = int(context.args[0])
    group_id = update.effective_chat.id
    group_limits[group_id] = new_limit
    await update.message.reply_text(f"✅ Group limit set to {new_limit} likes per day.")

# ========= START BOT =========
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("like", like))
    application.add_handler(CommandHandler("setpromotion", setpromotion))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("groupstatus", groupstatus))
    application.add_handler(CommandHandler("remain", remain))
    application.add_handler(CommandHandler("allow", allow))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("groupreset", groupreset))
    application.add_handler(CommandHandler("setremain", setremain))
    logger.info("Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
