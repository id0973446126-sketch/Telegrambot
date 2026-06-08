# 🚀 Deploy Telegram Bot to Render + Webhook + TimerRobot

This guide will help you deploy your Telegram bot 24/7 using Render (free tier), webhook mode, and TimerRobot for uptime monitoring.

---

## 📋 What You'll Get

✅ **24/7 Uptime** - Bot runs continuously on Render's free tier  
✅ **Webhook Mode** - More efficient than polling for production  
✅ **Auto-Restart** - TimerRobot keeps your bot alive  
✅ **Free Hosting** - No cost deployment  
✅ **Health Monitoring** - Automatic health checks every 5 minutes  

---

## 🎯 Step-by-Step Deployment

### Step 1: Prepare Your Repository

1. **Initialize Git** (if not already done):
   ```bash
   cd "d:\telegram-bot - Copy"
   git init
   git add .
   git commit -m "Initial commit - Telegram bot with webhook support"
   ```

2. **Push to GitHub**:
   - Create a new repository on GitHub
   - Push your code:
     ```bash
     git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
     git branch -M main
     git push -u origin main
     ```

---

### Step 2: Deploy to Render

1. **Create Render Account**:
   - Go to https://render.com
   - Sign up with GitHub (recommended)

2. **Create New Web Service**:
   - Click **New +** → **Web Service**
   - Connect your GitHub repository
   - Configure:
     - **Name**: `telegram-bot` (or any name)
     - **Region**: Choose closest to you
     - **Branch**: `main`
     - **Root Directory**: Leave blank
     - **Runtime**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn webhook_server:app`
     - **Instance Type**: **Free**

3. **Add Environment Variables**:
   Click **Advanced** → **Add Environment Variable**:
   
   | Variable | Value |
   |----------|-------|
   | `WEBHOOK_URL` | `https://YOUR-SERVICE-NAME.onrender.com/YOUR_BOT_TOKEN_PART` |
   
   ⚠️ **Important**: You'll get the actual URL after deployment. For now, use a placeholder like:
   ```
   https://telegram-bot-XXXX.onrender.com/PLACEHOLDER
   ```

4. **Deploy**:
   - Click **Create Web Service**
   - Wait 2-5 minutes for deployment
   - Copy your service URL from Render dashboard (e.g., `https://telegram-bot-xxxx.onrender.com`)

---

### Step 3: Configure Webhook URL

1. **Get Your Bot Token Part**:
   - Your token: `8974552549:AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8`
   - Token part after colon: `AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8`

2. **Set Correct WEBHOOK_URL**:
   In Render dashboard → **Environment** → Edit `WEBHOOK_URL`:
   ```
   https://YOUR-SERVICE-NAME.onrender.com/AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8
   ```
   
   Replace `YOUR-SERVICE-NAME` with your actual Render service name.

3. **Redeploy**:
   - Render will automatically redeploy
   - Wait 2-3 minutes

---

### Step 4: Set Up TimerRobot (Keep Bot Alive)

Render's free tier **sleeps after 15 minutes of inactivity**. TimerRobot prevents this by pinging your bot every 5 minutes.

1. **Open TimerRobot**:
   - Go to: https://t.me/TimerRobot
   - Send `/start`

2. **Create New Timer**:
   - Send: `/new`
   - Bot will ask for URL
   - Send your health check URL:
     ```
     https://YOUR-SERVICE-NAME.onrender.com/health
     ```

3. **Set Interval**:
   - Send: `5` (ping every 5 minutes)
   - TimerRobot will confirm

4. **Activate**:
   - The timer starts automatically
   - You'll receive notifications if your bot goes down

✅ **Your bot is now running 24/7!**

---

## 🔍 Verification

### Test Your Bot:

1. **Open Telegram** → Find your bot
2. **Send**: `/start`
3. **Expected**: Bot responds with menu

### Check Health Endpoint:

Open in browser:
```
https://YOUR-SERVICE-NAME.onrender.com/health
```

Should return:
```json
{"status": "ok", "message": "Bot is running"}
```

### Check Render Logs:

- Go to Render dashboard
- Click your service → **Logs**
- Look for: `Webhook set to: https://...`

---

## 📊 Monitoring & Maintenance

### Render Dashboard:
- **URL**: https://dashboard.render.com
- View logs, metrics, and deployment history
- Manual restart if needed

### TimerRobot:
- Monitors your bot every 5 minutes
- Alerts you if bot is down
- Automatically wakes up sleeping instances

### Update Your Bot:
```bash
# Make changes to bot.py
git add .
git commit -m "Update bot features"
git push origin main
```
Render will **auto-deploy** on push to main branch.

---

## ⚠️ Important Notes

### Render Free Tier Limitations:
- ⏰ **750 hours/month** (enough for 1 service 24/7)
- 😴 **Sleeps after 15 min** of inactivity (TimerRobot prevents this)
- 🚀 **Cold start**: 30-60 seconds when woken up
- 💾 **Ephemeral storage**: JSON files reset on redeploy

### Data Persistence:
Your bot uses JSON files for storage:
- `users.json`
- `facebook_data.json`
- `support_messages.json`

**On Render, these files are temporary!** They reset on:
- Redeployment
- Instance restart
- After sleep cycle

**Solutions** (choose one):
1. **Keep using JSON** (data resets occasionally - acceptable for testing)
2. **Use Google Sheets** (you already do for FB data - recommended)
3. **Add database** (PostgreSQL/MongoDB - advanced)

### Security:
- ✅ Your BOT_TOKEN is safe in Render environment variables
- ✅ Webhook endpoint is unique to your bot
- ✅ Never commit `credentials.json` to GitHub
- ⚠️ Add `credentials.json` to `.gitignore` (already done)

---

## 🐛 Troubleshooting

### Bot Not Responding:
1. Check Render logs for errors
2. Verify WEBHOOK_URL is correct
3. Check TimerRobot is pinging `/health`
4. Try: `https://YOUR-URL.onrender.com/health` in browser

### Webhook Not Set:
```python
# Manually set webhook via Python script:
import requests
BOT_TOKEN = "YOUR_TOKEN"
WEBHOOK_URL = "https://YOUR-URL.onrender.com/TOKEN_PART"
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
```

### 500 Error in Logs:
- Check environment variables are set
- Verify `credentials.json` exists on Render
- Check all dependencies in `requirements.txt`

### TimerRobot Not Working:
- Ensure URL is: `https://YOUR-URL.onrender.com/health`
- Check interval is 5 minutes (not seconds)
- Verify Render service is running

---

## 🔄 Alternative: Keep Using Polling (Simpler)

If webhook is too complex, you can keep polling mode:

1. Change `webhook_server.py` line 107 to:
   ```python
   bot_app.run_polling(
       allowed_updates=Update.ALL_TYPES,
       drop_pending_updates=True,
       poll_interval=0.5,
       timeout=10,
   )
   ```

2. Remove `WEBHOOK_URL` environment variable
3. TimerRobot setup remains the same

⚠️ **Note**: Webhook is recommended for production, polling is easier for testing.

---

## 📞 Support

If you encounter issues:
1. Check Render logs first
2. Test health endpoint in browser
3. Verify TimerRobot configuration
4. Review this guide step-by-step

---

## ✅ Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Render account created
- [ ] Web service deployed
- [ ] `WEBHOOK_URL` environment variable set
- [ ] Bot responds to `/start` command
- [ ] Health endpoint returns `{"status": "ok"}`
- [ ] TimerRobot configured with 5-min interval
- [ ] TimerRobot monitoring active
- [ ] `credentials.json` NOT in Git repository

---

**Your bot is now running 24/7! 🎉**
