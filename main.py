"""
Async Webhook Server for Telegram Bot - Production Ready
Uses uvicorn with async support for proper webhook handling
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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

# FastAPI app
app = FastAPI()

# Webhook configuration
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 10000))

# Bot application instance - Initialize at module level
request_obj = HTTPXRequest(
    connect_timeout=20.0,
    read_timeout=20.0,
    write_timeout=20.0,
    pool_timeout=20.0,
)

bot_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .request(request_obj)
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


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "message": "Bot is running"}


@app.post(f"/{BOT_TOKEN.split(':')[1]}")
async def webhook(request: Request):
    """Webhook endpoint for Telegram updates"""
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, bot_app.bot)
        await bot_app.process_update(update)
        return JSONResponse(content={"status": "ok"}, status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


# Set webhook on startup
@app.on_event("startup")
async def setup_webhook():
    """Set webhook when app starts"""
    if WEBHOOK_URL:
        try:
            await bot_app.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL not set!")
