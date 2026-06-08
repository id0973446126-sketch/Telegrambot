"""
Quick Webhook Setup Script
Run this after deploying to Render to set the webhook URL
"""

import requests
import sys

# Your bot token
BOT_TOKEN = "8974552549:AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8"

# Replace with your Render service URL
# Example: https://telegram-bot-xxxx.onrender.com
RENDER_URL = input("Enter your Render service URL (e.g., https://telegram-bot-xxxx.onrender.com): ").strip()

# Extract the token part after the colon
token_part = BOT_TOKEN.split(":")[1]

# Build webhook URL
WEBHOOK_URL = f"{RENDER_URL}/{token_part}"

print(f"\nSetting webhook to: {WEBHOOK_URL}")

# Set webhook
response = requests.get(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    params={"url": WEBHOOK_URL}
)

result = response.json()

if result.get("ok"):
    print("✅ Webhook set successfully!")
    print(f"\nHealth check URL: {RENDER_URL}/health")
    print("\nNow set up TimerRobot:")
    print(f"1. Open @TimerRobot on Telegram")
    print(f"2. Send: /new")
    print(f"3. Send URL: {RENDER_URL}/health")
    print(f"4. Send interval: 5 (minutes)")
else:
    print("❌ Failed to set webhook:")
    print(result)
    sys.exit(1)

# Verify webhook
print("\nVerifying webhook info...")
info_response = requests.get(
    f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
)
info = info_response.json()

if info.get("ok"):
    webhook_info = info["result"]
    print(f"URL: {webhook_info.get('url')}")
    print(f"Has pending updates: {webhook_info.get('pending_update_count', 0)}")
    print(f"Last error: {webhook_info.get('last_error_message', 'None')}")
else:
    print("❌ Failed to get webhook info")
