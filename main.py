import os
import re
import aiohttp
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    ContextTypes
)

TOKEN = "8342680845:AAEPXNrDqyCGk4OPXyeVItOsrSI-DfSg4UU"
WEBHOOK_URL = "https://telegram-temp-mail-bot-5kmo.onrender.com/webhook"

API = "https://api.mail.tm/"
user_accounts = {}    # chat_id → {email, password, token}


app = Flask(__name__)
bot_app = None


# ------------------------------
# Helper function for mail.tm API
# ------------------------------
async def mailtm_request(method, endpoint, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with aiohttp.ClientSession() as session:
        async with session.request(method, API + endpoint, json=data, headers=headers) as resp:
            try:
                return await resp.json()
            except:
                return {}


# ------------------------------
# Telegram Commands
# ------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📬 *Temporary Mail Bot*\n\n"
        "/generate – create mailbox\n"
        "/email – show your email\n"
        "/inbox – show your inbox\n"
        "/message <id> – open a message\n",
        parse_mode="Markdown"
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Get domain
    async with aiohttp.ClientSession() as session:
        async with session.get(API + "domains") as resp:
            domains = await resp.json()

    domain = domains["hydra:member"][0]["domain"]

    import random, string
    email = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + "@" + domain
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    # Create account
    await mailtm_request("POST", "accounts", {"address": email, "password": password})

    # Login
    token_data = await mailtm_request("POST", "token", {"address": email, "password": password})
    token = token_data.get("token")

    if not token:
        await update.message.reply_text("❌ Failed to generate email.")
        return

    user_accounts[chat_id] = {
        "email": email,
        "password": password,
        "token": token
    }

    await update.message.reply_text(
        f"📧 *Your Email:*\n`{email}`",
        parse_mode="Markdown"
    )


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in user_accounts:
        await update.message.reply_text("❌ Use /generate first.")
        return

    await update.message.reply_text(
        f"📧 Your Email:\n`{user_accounts[chat_id]['email']}`",
        parse_mode="Markdown"
    )


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in user_accounts:
        await update.message.reply_text("❌ Use /generate first.")
        return

    token = user_accounts[chat_id]["token"]
    messages = await mailtm_request("GET", "messages", token=token)

    inbox_list = messages.get("hydra:member", [])

    if not inbox_list:
        await update.message.reply_text("📭 Inbox empty.")
        return

    text = "📬 *Inbox:*\n\n"
    for msg in inbox_list:
        text += (
            f"🆔 `{msg['id']}`\n"
            f"📌 From: `{msg['from']['address']}`\n"
            f"✉ Subject: {msg['subject']}\n"
            "———————————————\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in user_accounts:
        await update.message.reply_text("❌ Use /generate first.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /message <id>")
        return

    msg_id = context.args[0]
    token = user_accounts[chat_id]["token"]

    msg = await mailtm_request("GET", f"messages/{msg_id}", token=token)

    if "id" not in msg:
        await update.message.reply_text("❌ Message not found.")
        return

    content = msg.get("text", "")
    if not content and msg.get("html"):
        content = msg["html"][0]

    otp_match = re.findall(r"\b\d{4,8}\b", content)
    otp_text = f"\n\n🔐 OTP: `{otp_match[0]}`" if otp_match else ""

    await update.message.reply_text(
        f"📬 *Message:*\n\n"
        f"📌 From: `{msg['from']['address']}`\n"
        f"✉ Subject: {msg['subject']}\n\n"
        f"{content}{otp_text}",
        parse_mode="Markdown"
    )


# -----------------------------------
# Flask: Receive Telegram Webhook
# -----------------------------------

@app.post("/webhook")
async def webhook():
    update_data = request.get_json(force=True)
    update = Update.de_json(update_data, bot_app.bot)
    await bot_app.process_update(update)
    return "ok", 200


# -----------------------------------
# Start Webhook Application
# -----------------------------------

async def setup(application):
    await application.bot.set_webhook(WEBHOOK_URL)


def run():
    global bot_app

    bot_app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("generate", generate))
    bot_app.add_handler(CommandHandler("email", email))
    bot_app.add_handler(CommandHandler("inbox", inbox))
    bot_app.add_handler(CommandHandler("message", message))

    bot_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=WEBHOOK_URL,
        post_init=setup
    )


if __name__ == "__main__":
    run()
