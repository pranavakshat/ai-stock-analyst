# LinkedIn Post

---

A week ago I built an AI stock analyst that asks 4 different AI models — Claude, ChatGPT, Gemini, and Grok — for their top stock picks every morning before the market opens. It scores them at the close, tracks each model's accuracy over time, and runs a simulated $10,000 portfolio for each one to see who would actually be making money.

Today it lost a full day of data. Recovering it taught me more than building it did.

The system runs on a free hosting service that wipes the database every time I push new code. To prevent data loss, I had set up automatic backups that save everything to a folder and commit it to GitHub before every restart. I'd been running this for almost a week and assumed it was working.

It wasn't. The backup function was silently failing every single time, for two days straight. The fix turned out to be one of those bugs that nobody warns you about: the hosting service strips a hidden folder from my code when it deploys, and that hidden folder is what makes the backup function know what to back up. Without it, the function thought there was nothing to save and quietly skipped its job.

I only found out when I pushed an unrelated update, the database wiped, and the most recent saved version was three days old. Two days of stock picks, accuracy scores, and portfolio data — gone.

So I rebuilt the backup system from scratch using a different approach that doesn't depend on that hidden folder existing. Tested it locally to make sure it actually worked this time. Pushed it. Watched the next backup successfully save to GitHub for the first time in days.

Then I rebuilt the lost data piece by piece. The hosting service still had log files showing which stocks each AI had picked. I had email screenshots showing which direction (bet up or bet down) and how confident each AI was. I cross-referenced the two, manually entered everything back into the system, and double-checked it against the original emails. The picks are restored. The reasoning text each AI wrote — explaining *why* they picked what they picked — is permanently lost, and every recovered entry is now marked "[Reconstructed]" so I never pretend otherwise.

While I was in there, I also redesigned the dashboard to look like a Bloomberg terminal. Dark theme, scrolling ticker tape across the top showing today's picks, live price updates every minute during market hours.

**Live dashboard:** https://ai-stock-analyst-production-868a.up.railway.app

The interesting part of building something like this isn't the AI calls — those are easy. It's everything that happens around them: making sure the system survives its own updates, recovering when it doesn't, and being honest about what got lost. That's where most of this week has gone.

Built with no prior production experience, directing Claude as a technical partner the entire way.

If you've built something similar, I'd love to compare notes.

---
