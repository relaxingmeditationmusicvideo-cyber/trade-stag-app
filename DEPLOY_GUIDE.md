# Trade Stag — Free Deployment Guide

Deploy your app online for FREE using **Render** (backend) + **Vercel** (frontend).

---

## Prerequisites

- A **GitHub** account (free) — https://github.com/signup
- A **Render** account (free) — https://render.com (sign up with GitHub)
- A **Vercel** account (free) — https://vercel.com (sign up with GitHub)

---

## Step 1: Push Code to GitHub

1. Go to https://github.com/new
2. Create a new repository named `trade-stag`
3. Set it to **Private**
4. On your computer, open a terminal in the `trade-stag-app` folder and run:

```
git init
git add .
git commit -m "Initial commit - Trade Stag app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/trade-stag.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Step 2: Deploy Backend on Render

1. Go to https://dashboard.render.com/new/web-service
2. Click **"Connect a repository"** and select your `trade-stag` repo
3. Configure:
   - **Name:** `trade-stag-api`
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
4. Click **"Advanced"** and add these environment variables:
   - `JWT_SECRET` = (click "Generate" for a random value)
   - `PYTHON_VERSION` = `3.11.6`
5. Click **"Create Web Service"**
6. Wait 2-3 minutes for it to build and deploy
7. Copy your backend URL — it will look like: `https://trade-stag-api.onrender.com`

---

## Step 3: Deploy Frontend on Vercel

1. Go to https://vercel.com/new
2. Click **"Import"** and select your `trade-stag` repo
3. Configure:
   - **Framework Preset:** Create React App
   - **Root Directory:** `frontend`
4. Click **"Environment Variables"** and add:
   - `REACT_APP_API_URL` = `https://trade-stag-api.onrender.com` (your Render URL from Step 2)
5. Click **"Deploy"**
6. Wait 1-2 minutes — your app will be live at something like: `https://trade-stag.vercel.app`

---

## Step 4: Test It

1. Open your Vercel URL in a browser
2. You should see the Trade Stag landing page
3. Sign up for an account
4. The dashboard will show demo data initially

---

## Step 5: Enable Live Data (Optional)

To get real NSE 500 data:

1. Copy your `nse500_swing_analyzer_vikrant.py` file to the `backend/` folder as `analyzer.py`
2. Push to GitHub:
   ```
   git add backend/analyzer.py
   git commit -m "Add live analyzer"
   git push
   ```
3. Render will auto-redeploy
4. Trigger a scan by visiting: `https://trade-stag-api.onrender.com/api/scan` (POST request)

---

## Important Notes

- **Render free tier** sleeps after 15 min of inactivity — first request after sleep takes ~30 seconds
- **Vercel free tier** is generous — 100GB bandwidth/month
- For always-on backend, upgrade Render to $7/month Starter plan
- To use a custom domain, add it in Vercel dashboard > Settings > Domains

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend URL shows error | Check Render logs in dashboard |
| Frontend can't reach API | Verify REACT_APP_API_URL is correct in Vercel env vars |
| CORS errors | Backend already allows all origins — redeploy if needed |
| Signup/Login not working | Check JWT_SECRET is set in Render env vars |
