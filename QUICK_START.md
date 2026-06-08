# ⚡ Quick Start - Deploy in 10 Minutes

## 🎯 3 Simple Steps

### 1️⃣ Deploy to Render (5 min)

```bash
# Push to GitHub
cd "d:\telegram-bot - Copy"
git init
git add .
git commit -m "Initial commit"
git push -u origin main
```

**On Render.com:**
1. New → Web Service
2. Connect GitHub repo
3. Settings:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn webhook_server:app`
   - Instance: **Free**
4. Add environment variable:
   ```
   WEBHOOK_URL = https://YOUR-SERVICE.onrender.com/AAG8iYmRr7mj7pDJexuRuxbmyxx5je4Xc-8
   ```
5. Deploy!

---

### 2️⃣ Set Up TimerRobot (2 min)

1. Open **@TimerRobot** on Telegram
2. Send: `/new`
3. Send URL: `https://YOUR-SERVICE.onrender.com/health`
4. Send: `5` (ping every 5 minutes)

---

### 3️⃣ Test (1 min)

1. Open your bot on Telegram
2. Send: `/start`
3. ✅ Bot responds!

---

## 🔧 Files Created

| File | Purpose |
|------|---------|
| `webhook_server.py` | Webhook server for Render |
| `requirements.txt` | Python dependencies |
| `Procfile` | Render startup config |
| `setup_webhook.py` | Helper to set webhook URL |
| `DEPLOYMENT_GUIDE.md` | Full deployment guide |
| `.gitignore` | Git ignore file |

---

## 📞 Quick Commands

**Check health:**
```
https://YOUR-SERVICE.onrender.com/health
```

**Set webhook manually:**
```bash
python setup_webhook.py
```

**View Render logs:**
Dashboard → Your Service → Logs

---

## ⚠️ Important

- JSON files reset on redeploy (use Google Sheets for important data)
- Free tier: 750 hours/month (enough for 1 bot)
- TimerRobot keeps bot awake (pings every 5 min)
- Never commit `credentials.json` to GitHub

---

## 🐛 Bot Not Working?

1. Check Render logs
2. Test: `https://YOUR-SERVICE.onrender.com/health`
3. Verify `WEBHOOK_URL` env var
4. Restart service on Render

---

**Full guide:** See `DEPLOYMENT_GUIDE.md`
