# 🚀 Setup Guide — Start Here
### No coding experience needed. Follow every step in order.

---

## What is this thing?

You have a program that, every morning at 5 AM, automatically asks 5 AI models (Claude, ChatGPT, Grok, Gemini, and Copilot) for their top 5 stock picks of the day. It then:
- **Emails you** a clean summary
- **Tracks which AI was right** over time
- **Shows a dashboard** at a website you can check anytime

Think of it like having 5 AI analysts on your payroll, and a scoreboard showing who's actually good.

---

## Before you start — What you'll need

- A Mac or Windows computer
- About 45 minutes
- A Gmail account (you probably already have one)
- Credit cards are NOT needed — all the AI APIs have free tiers

---

---

# PART 1 — Install the tools on your computer

---

## Step 1 — Install Python

Python is the programming language this app is written in. You need to install it once.

**On Mac:**
1. Go to: **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.12.x"** button
3. Open the file that downloads (it ends in `.pkg`)
4. Click through the installer (just keep clicking Continue → Install)
5. Done ✅

**On Windows:**
1. Go to: **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.12.x"** button
3. Open the `.exe` file that downloads
4. ⚠️ On the FIRST screen, check the box that says **"Add Python to PATH"** (this is important!)
5. Click **"Install Now"**
6. Done ✅

---

## Step 2 — Open Terminal (the black command window)

This is the app where you type commands to control your computer. It looks intimidating but you're just going to copy and paste things into it.

**On Mac:**
- Press `Command + Space`, type `Terminal`, press Enter

**On Windows:**
- Press the Windows key, type `Command Prompt`, press Enter
- (Or search for `cmd`)

A black or white window will open. This is normal. Don't close it.

---

## Step 3 — Navigate to the project folder

The project files are sitting in your Documents folder. You need to tell Terminal to "go" to that folder.

Copy and paste this command into Terminal, then press **Enter**:

**On Mac:**
```
cd "/Users/pnav/Documents/Claude/Projects/AI Stock Analyst Agent — Multi-Model Daily Tracker"
```

**On Windows:**
```
cd "C:\Users\pnav\Documents\Claude\Projects\AI Stock Analyst Agent — Multi-Model Daily Tracker"
```

Nothing exciting will happen — that's fine. The cursor just moves to a new line.

---

## Step 4 — Set up a virtual environment

This creates a private "bubble" for the app's tools so they don't interfere with anything else on your computer.

Copy and paste these commands **one at a time**, pressing Enter after each:

```
python -m venv venv
```

Then:

**On Mac:**
```
source venv/bin/activate
```

**On Windows:**
```
venv\Scripts\activate
```

You'll see `(venv)` appear at the start of the line. That means it worked. ✅

---

## Step 5 — Install the app's dependencies

Dependencies are helper packages the app needs. This is like installing apps inside your bubble.

Copy and paste this, then press Enter:

```
pip install -r requirements.txt
```

You'll see a lot of text scrolling by. This is normal. Wait for it to finish (takes 1-3 minutes). You'll know it's done when the cursor comes back.

---

---

# PART 2 — Get your API keys (passwords for each AI)

---

This is the most important part. An "API key" is like a password that lets the app talk to each AI service. You need one for each service.

Open the `.env.example` file in your project folder — it's a text file. You can open it with any text editor (Notepad on Windows, TextEdit on Mac). Then create a **copy of it** named `.env` (no ".example" at the end). You'll fill in the values below.

> **How to create the .env file:**
> - Find `.env.example` in your project folder
> - Make a copy of it
> - Rename the copy to just `.env`
> - Open `.env` in a text editor

---

## Key 1 — Claude (Anthropic)

1. Go to: **https://console.anthropic.com**
2. Create a free account (or log in)
3. Click **"API Keys"** in the left sidebar
4. Click **"Create Key"**
5. Give it any name (e.g., "stock agent")
6. Copy the key — it starts with `sk-ant-...`
7. In your `.env` file, replace `sk-ant-...` on the `ANTHROPIC_API_KEY=` line with your key

---

## Key 2 — ChatGPT (OpenAI)

1. Go to: **https://platform.openai.com/api-keys**
2. Create a free account (or log in)
3. Click **"+ Create new secret key"**
4. Give it any name
5. Copy the key — it starts with `sk-...`
6. You'll need to add a small amount of credit ($5 minimum) — go to **Billing** → **Add payment method**. The app uses roughly $0.01–0.05 per day.
7. In your `.env` file, fill in `OPENAI_API_KEY=`

---

## Key 3 — Gemini (Google)

1. Go to: **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key — it starts with `AIza...`
5. In your `.env` file, fill in `GOOGLE_API_KEY=`

Free tier is generous — no credit card needed for normal usage. ✅

---

## Key 4 — Grok (xAI)

1. Go to: **https://console.x.ai**
2. Sign in with your X (Twitter) account
3. Click **"API Keys"** → **"Create API Key"**
4. Copy the key — it starts with `xai-...`
5. In your `.env` file, fill in `XAI_API_KEY=`

---

## Key 5 — Copilot (Microsoft Azure) — Optional, can skip for now

This one is more complex because it requires an Azure account. If you want to skip Copilot for now, that's totally fine — the other 4 models will still work. Just leave the `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOY` lines blank.

**If you want Copilot:**
1. Go to: **https://portal.azure.com** and create a free Microsoft account
2. Search for **"Azure OpenAI"** and create a resource
3. Inside the resource, go to **"Keys and Endpoint"** — copy the key and endpoint URL
4. Then go to **"Model deployments"** → **"Deploy model"** → choose `gpt-4o`
5. Fill in all three `AZURE_OPENAI_*` lines in your `.env` file

---

## Key 6 — Gmail (for sending emails)

You can't use your normal Gmail password here. You need a special "App Password."

**Step A — Turn on 2-Step Verification (if not already on):**
1. Go to: **https://myaccount.google.com/security**
2. Find **"2-Step Verification"** and turn it on
3. Follow the steps (usually just add your phone number)

**Step B — Create an App Password:**
1. Go to: **https://myaccount.google.com/apppasswords**
2. In the "App name" field, type: `Stock Agent`
3. Click **"Create"**
4. Google will show you a **16-character password** like `abcd efgh ijkl mnop`
5. Copy it (spaces included are fine)

**Step C — Fill in your .env file:**
```
GMAIL_ADDRESS=your.email@gmail.com
GMAIL_APP_PASS=abcd efgh ijkl mnop
EMAIL_RECIPIENT=pranav.akshat.2@gmail.com
```

---

## What your .env file should look like when done

```
APP_SECRET_KEY=any-random-words-here-like-pizza-monkey-42
DEBUG=false
PORT=5000
DATABASE_PATH=data/predictions.db

ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
GOOGLE_API_KEY=AIzaxxxxxxxxxxxxxxxx
XAI_API_KEY=xai-xxxxxxxxxxxxxxxx

AZURE_OPENAI_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOY=gpt-4o

GMAIL_ADDRESS=your.email@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
EMAIL_RECIPIENT=pranav.akshat.2@gmail.com

MORNING_HOUR=5
MORNING_MINUTE=0
EVENING_HOUR=18
EVENING_MINUTE=0
TIMEZONE=America/New_York

STARTING_PORTFOLIO_VALUE=10000
```

Save the file when done.

---

---

# PART 3 — Run the app

---

## Step 6 — Start the app

Go back to your Terminal window (the one where you typed commands earlier — make sure you still see `(venv)` at the start of the line).

Type this and press Enter:

```
python app.py
```

You'll see something like:
```
INFO — Database initialised at data/predictions.db
INFO — Scheduler started.
* Running on http://0.0.0.0:5000
```

**The app is now running! Don't close this Terminal window — it needs to stay open.**

---

## Step 7 — Open the dashboard

Open your web browser (Chrome, Safari, etc.) and go to:

**http://localhost:5000**

You'll see the dashboard with 4 tabs: Today's Picks, Accuracy, Portfolio, and History.

---

## Step 8 — Test it right now (don't wait until 5 AM!)

Click the **"▶ Run Morning Job"** button at the top right of the dashboard.

This will:
1. Ask all 5 AIs for their stock picks
2. Save them to the database
3. Send you an email with the results

It takes about 30–60 seconds. Check your inbox — you should get an email!

Then click **"🌙 Run Evening Job"** to simulate what happens at 6 PM (fetches today's actual stock prices and scores the predictions).

After that, click the **Accuracy** and **Portfolio** tabs — they'll have data now.

---

---

# PART 4 — Put it on the internet (so it runs automatically 24/7)

---

Right now the app only runs when your computer is on and the Terminal window is open. To make it run automatically every morning at 5 AM, you need to host it on a server. Railway is the easiest free option.

---

## Step 9 — Put your code on GitHub (free code storage)

GitHub is like Google Drive but for code. Railway will pull your code from here.

1. Go to **https://github.com** and create a free account
2. Click **"New repository"** (the green button or `+` at the top right)
3. Name it `ai-stock-analyst`
4. Leave it as **Private** (so your API keys are safer)
5. Click **"Create repository"**

Now, in your Terminal (still in the project folder with `(venv)` active):

```
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/ai-stock-analyst.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username.

> ⚠️ The `.env` file is in `.gitignore` — it will NOT be uploaded to GitHub. Your API keys are safe.

---

## Step 10 — Deploy to Railway

1. Go to **https://railway.app** and sign in with your GitHub account
2. Click **"New Project"**
3. Click **"Deploy from GitHub repo"**
4. Select `ai-stock-analyst`
5. Railway will detect the `railway.toml` file and start building

**Now add your secret keys:**
1. In Railway, click on your project
2. Click **"Variables"** in the left sidebar
3. Click **"Add Variable"** for each line in your `.env` file
4. Copy every `KEY=value` pair from your `.env` into Railway

5. Click **"Deploy"**

After 2-3 minutes, Railway will give you a URL like:
`https://ai-stock-analyst-production.up.railway.app`

That's your live dashboard! Bookmark it.

> **Free tier note:** Railway's free tier gives you $5/month of credit. This app uses roughly $0.50–1.00/month of Railway compute. The AI API calls are separate costs (very small — pennies per day).

---

---

# PART 5 — Ongoing use

---

## What happens automatically (once deployed)

| Time | What happens |
|------|------|
| 5:00 AM ET | App asks all 5 AIs for stock picks → saves to database → emails you |
| 6:00 PM ET | App fetches actual stock prices → scores which picks were right → updates portfolio simulation |

You don't need to do anything. Just check your email each morning and the dashboard whenever you want.

---

## Changing the email time

Open `.env` and change:
```
MORNING_HOUR=5    ← change this number (0-23, in your timezone)
MORNING_MINUTE=0
TIMEZONE=America/New_York
```

Common timezones: `America/Los_Angeles`, `America/Chicago`, `Europe/London`, `Asia/Kolkata`

---

## Backup your data

To export everything to spreadsheet files, run this in Terminal:

```
python backup.py
```

This creates a `backups/` folder with CSV files you can open in Excel.

---

## If something goes wrong

**"No picks" showing in dashboard:** Your API keys might be wrong. Double-check the `.env` file — no spaces around the `=` sign, no quotes needed.

**Email not arriving:** Make sure you used a Gmail App Password (the 16-character one), not your regular Gmail password. Check your spam folder too.

**The app crashed:** Look at the Terminal for a red error message. The most common cause is a typo in the `.env` file.

**Still stuck?** Just ask — bring the error message and I'll fix it.

---

*Built with Claude, April 2026*
