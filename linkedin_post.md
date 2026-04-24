# LinkedIn Post

---

I built an AI stock analyst that queries 4 different AI models every morning and emails me their top picks before the market opens.

Here's what it actually does:

Every day at 8 AM, the system pulls live data from 8 sources simultaneously — market indices, sector performance, Fear & Greed Index, pre-market movers, macro indicators (yields, crypto, commodities), the economic calendar, earnings reports, analyst upgrades, and Reddit sentiment. That full market briefing gets injected into Claude, ChatGPT, Grok, and Gemini — all at the same time.

Each model returns 5 stock picks in structured JSON: ticker, LONG or SHORT direction, a conviction-weighted allocation percentage, reasoning, and confidence level. The allocations have to sum to 100% — so if a model puts 40% on one name, it's really saying something.

At 6 PM, the system fetches end-of-day prices, scores each pick correct or incorrect (accounting for direction — a SHORT is only right if the stock fell), and updates a simulated $10,000 portfolio per model using their actual conviction weights. High conviction cuts both ways.

There's a live dashboard tracking accuracy and P&L for each model across any time window — all time, 1 month, 1 week, yesterday.

**Live dashboard:** https://ai-stock-analyst-production-868a.up.railway.app

The interesting part isn't just the picks — it's watching where the models agree and disagree. This morning, all four independently picked FCX LONG. But ChatGPT was bullish on Intel while Claude and Gemini both shorted it. Same data, opposite conclusions. End of day will tell us who was right.

I built this entirely by directing Claude as my technical partner — no prior experience deploying production Python apps. The system runs on Railway, stores data in SQLite, and sends email digests via Resend.

If you're a developer who built something similar, I'd genuinely love to compare notes.

---
