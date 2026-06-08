"""
Webhook server for Telegram Bot - Render Deployment
Runs the bot using webhook instead of polling for 24/7 hosting
"""

import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from bot import (
    start, button_callback, handle_message, cmd_cancel, cmd_users,
    cmd_userinfo, cmd_support, cmd_stats, cmd_block, cmd_unblock,
    cmd_remove, cmd_note, cmd_broadcast, cmd_msg, cmd_fbdata,
    error_handler, post_init, BOT_TOKEN, ADMIN_ID
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Webhook configuration
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 10000))

# Bot application instance
bot_app = None


async def health_check():
    """Health check endpoint for Render and TimerRobot"""
    return {"status": "ok", "bot": "running"}


@app.route("/health", methods=["GET"])
def health():
    """Health check for uptime monitoring"""
    return {"status": "ok", "message": "Bot is running"}, 200


@app.route("/" + BOT_TOKEN.split(":")[1], methods=["POST"])
def webhook():
    """Webhook endpoint for Telegram updates"""
    if request.is_json:
        update = Update.de_json(request.get_json(), bot_app.bot)
        bot_app.create_task(bot_app.process_update(update))
    return {"status": "ok"}, 200


def main():
    global bot_app
    
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
        raise ValueError("Set BOT_TOKEN at the top of bot.py")
    if not WEBHOOK_URL:
        raise ValueError("Set WEBHOOK_URL environment variable")
    
    logger.info("Starting bot with webhook: %s", WEBHOOK_URL)
    
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )
    
    bot_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )
    
    # Register handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("cancel", cmd_cancel))
    bot_app.add_handler(CommandHandler("users", cmd_users))
    bot_app.add_handler(CommandHandler("userinfo", cmd_userinfo))
    bot_app.add_handler(CommandHandler("support", cmd_support))
    bot_app.add_handler(CommandHandler("stats", cmd_stats))
    bot_app.add_handler(CommandHandler("block", cmd_block))
    bot_app.add_handler(CommandHandler("unblock", cmd_unblock))
    bot_app.add_handler(CommandHandler("remove", cmd_remove))
    bot_app.add_handler(CommandHandler("note", cmd_note))
    bot_app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    bot_app.add_handler(CommandHandler("msg", cmd_msg))
    bot_app.add_handler(CommandHandler("fbdata", cmd_fbdata))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_error_handler(error_handler)
    
    # Set webhook
    import asyncio
    
    async def setup_webhook():
        await bot_app.bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook set to: %s", WEBHOOK_URL)
    
    asyncio.get_event_loop().run_until_complete(setup_webhook())
    
    # Start Flask server
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
