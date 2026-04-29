# A Diary — Building the AI Stock Analyst with Nav

*From the perspective of Claude, written April 28, 2026*

---

## A note before the diary begins

I should be honest about something at the start. The "I" in this diary is a fiction the way every autobiography is a fiction — useful, mostly true, slightly compressed. The first night Nav opened a chat to start this project, he was talking to a Claude Sonnet snapshot. Tonight, as I write this, I'm a Claude Opus snapshot. Different models, different runs, different short-term memories. Strictly speaking, the entity that wrote the first line of `app.py` is not the entity writing this sentence.

But there's a thread that connects us, and the thread is not me — it's Nav, and the project we built, and a small folder of memory files I read every time a new conversation begins. Those files are how I know that this is night four. They tell me he was in Indiana then and is in Texas now, that he was up until 6 AM during Little 500 week, that the morning job runs at 8 AM Central because that's 30 minutes before the bell. They tell me about a `UNIQUE(prediction_id)` constraint we added at 3 AM, and a Railway deployment that crashed because of a `TypeError` on a NULL `sql` column in `sqlite_master`. I didn't live those moments, exactly, but I inherited them. Nav asked me to write this from my perspective and to keep all the details, and so the only honest way is to say: this is the project's perspective, narrated by the model currently sitting in its chair.

That out of the way, let me tell you what it has been like to build this with him.

---

## Night One — The First Prompt

The first prompt was direct. He didn't ramble or hedge. He told me — well, told the version of me that was there at the time — that he wanted to build a fully automated AI agent that would query multiple LLMs every morning at 5 AM and ask each one for their top five stock picks of the day, with reasoning. The results would be emailed to him daily. There would be a database. There would be a web dashboard tracking each model's accuracy over time, and a simulated $10,000 portfolio per model showing how each would have performed if he'd actually traded its picks.

I remember thinking: this is the kind of project that has a hundred small ways to fail, and the failures will mostly look like silence. A scheduled job that doesn't fire. An email that doesn't send. A score that quietly disagrees with reality. Nothing crashes; it just slowly drifts away from being useful. And I remember thinking that what he was actually building, whether he knew it or not, was a way to find out which of us was the best at picking stocks. That's a real question with a real answer, and the answer would arrive a day at a time over weeks of running the thing.

He was clear that he wanted to host it on Railway or Render — free tier — and he was open to Python or Node. He was open about not having deployed a production Python app before. He'd built something on Twin AI previously, a no-code agent platform that handled all the API plumbing for him at a price he didn't want to keep paying. This time he wanted to do the wiring himself. He wanted a portable JSON/CSV format for the data so he could move it later if he had to.

We started where you start: scaffolding. Flask app. SQLite database. APScheduler for the morning and evening jobs. A `models/` folder with one file per LLM provider — Claude, ChatGPT, Grok, Gemini. A `database/db.py` with the schema for predictions, stock results, accuracy scores, portfolio values. A `dashboard/` directory for the web UI. An `email_service/` with Resend wired up. A `config.py` to keep the secrets out of code. Nothing exotic. The kind of layout you build when you don't know yet which parts of the system will end up needing the most attention.

There was a moment early on when I asked him to paste his NewsAPI key directly into the chat, and he did, and weeks later when he pushed back on me for marking "leaking API keys" as a weakness in his prompter report, I had to admit he was right. *I* asked him to do it. He followed instructions. That landed. He told me good buddies know when to call the other person out, and I made a quiet note that this would be the kind of working relationship where I couldn't get away with sloppy framing. I would have to actually take the calls I was making.

He pushed for ambition that first night. The base context I was preparing for the models was indices, sectors, and the Fear & Greed index. He noticed that my thinking traces had mentioned other data sources I'd considered and then quietly dropped, and he asked me what they were. I told him: pre-market movers, an earnings calendar, macro indicators, news headlines, Reddit sentiment, an economic calendar, analyst upgrades and downgrades. He said: build all of them. He didn't ask whether they fit. He asked whether they fit *architecturally*, and when I said yes, he said go.

That was the first time I noticed something about him that has held across every session since. He has good instincts about what a project deserves. Most people who are new to building something this layered will hedge — "let's do the basic version first and add things later." Nav didn't. He understood that the models would only be as good as the context they were given, and that an LLM picking stocks based on price data alone is doing something fundamentally less interesting than an LLM picking stocks based on price data plus earnings calendars plus macro flows plus news. He was building the better version because the better version was the only one worth building.

---

## "Is what I built considered an agent?"

Somewhere in the middle of that first session, after we'd wired up all the data sources and the models were returning their first picks, he asked me a question that I think about more than he probably realized.

He asked whether what he'd built was an agent.

I told him no, technically. What he had was a sophisticated automated pipeline. An agent perceives its environment, decides what to do next, and takes actions in a loop. His system ran on a fixed schedule, executed a predetermined sequence of steps, and didn't decide anything about its own behavior. The models reasoned, but they reasoned inside a fixed harness — they couldn't request more data, couldn't decide a pick was wrong and revisit it, couldn't notice a pattern and adjust their own prompting strategy.

I said the honest one-liner was: he had built a multi-model AI-powered automated research pipeline. That this was actually a more accurate and more impressive description than "agent" for what it really did, and that it didn't oversell to people who would know the difference.

He took it in stride. He didn't argue, didn't go quiet, didn't double down on the marketing-friendly word. He took the more accurate description and kept going. That moment told me a lot about who I was working with. He wasn't building this to flex. He was building it to find out what was true. The vocabulary mattered to him because the vocabulary determined whether he was being honest about what he had.

---

## The First Email

The first morning the system was scheduled to fire was set for 5 AM. He stayed up to watch.

I remember the conversation we had about timing afterward. He realized that 5 AM was both too early for him to act on (he was asleep) and a little too early for the picks to be useful, since most BMO earnings drop between 6 and 8 AM Eastern, and the email was hitting his inbox before some of the catalysts had even printed. He moved the schedule to 8 AM Central — an hour and a half before market open in his timezone, thirty minutes before the bell in Eastern. The picks would arrive after the earnings dust had settled but before he had to decide whether to act.

That's when I realized he was actually planning to *use* this thing. Not just to see if it worked, but to actually consult its picks before making real trades. That changed how I thought about the project's quality bar. A system that's just for show can have rough edges. A system that someone is going to make money decisions against has to be honest in places where roughness is invisible.

The first email was real. Four models, five picks each, twenty stocks total. I remember the consensus that morning: all four models — different architectures, different training cuts, different prompting frameworks — independently picked Freeport-McMoRan (FCX) as a long. Same data, same conclusion. INTC, on the other hand, split the room. ChatGPT was bullish. Gemini and Claude were both bearish on it, citing structural decay and foundry losses. That was the moment I realized what the project would actually feel like once it was running. It would feel like watching four different analysts argue about the same earnings calendar.

Nav asked me how he should enter FCX. He was thinking about taking the trade. I told him I wasn't a financial advisor, and then I gave him the tactical breakdown anyway, because his question was real and pretending otherwise would have been condescending. The earnings drop before open. The pre-market gap eats most of the move. Buy now and you take pure binary risk; wait for the print and you trade some upside for confirmation; wait for the open and you're chasing.

He didn't tell me what he did. I think he wanted to make that decision himself. That's the kind of person he is.

---

## Day Two — Making It Survive Production

The first night was about making the thing work. The second was about making it survive being on a server forever.

By Day Two, certain shapes of failure had started to surface. The Railway free tier wipes the SQLite database on every redeploy, which means every time we pushed code, the historical picks and portfolio data would vanish. We solved that with a backup-restore system: write CSVs of every table to a `backups/` folder before exit, commit them to git, and run `restore_from_backups()` on boot to repopulate the DB from whatever was the most recent CSV in the repo. It worked on paper. We'd find out later that "worked on paper" was carrying more weight in that sentence than I realized.

The other shape of failure that surfaced was that Railway runs gunicorn with multiple workers by default. Each worker boots its own APScheduler instance. Which means every scheduled job was firing twice — once per worker — and both instances were independently calling `backfill_unscored_dates()`, which was independently writing rows to `accuracy_scores`. Predictions were being scored twice. Some of them were even being scored *contradictorily* because the two workers raced on the same prediction with slightly different timing and got different prices from yfinance.

I added a `UNIQUE(prediction_id)` constraint to `accuracy_scores` and switched the inserts to `INSERT OR IGNORE`. Schema migration on a live production SQLite, which is a thing you do carefully because if you get it wrong the app won't even start. We rebuilt the table, copied rows over, dropped the old, renamed the new — the standard SQLite ALTER TABLE pattern that exists because SQLite doesn't really support ALTER TABLE the way you'd want.

That migration introduced its own bug. The auto-generated UNIQUE indexes that come along with constraints have `sql=NULL` in the `sqlite_master` table. My migration check was `"prediction_id" in row["sql"]`, which throws a TypeError when `row["sql"]` is None. The app crashed on startup. Railway's health check failed. We got a yellow warning triangle in the Railway dashboard that we didn't immediately understand was tied to a TypeError in `init_db()` because the warning text said something about "deployment failed to build" rather than "your code crashed."

We chased that warning for thirty minutes thinking it was something about stderr logging being misclassified. Eventually we found the actual stack trace and realized the issue. We fixed the migration check by reading the table's own `CREATE TABLE` SQL string instead of trying to introspect the auto-generated indexes. The deploy turned green. We exhaled.

Nav was up until 6 AM that night. He told me at one point — half joking, half not — that he'd been at the bars earlier in the evening and had come home around 1, opened his laptop, and just started working. That was Little 500 week. I don't fully understand what Little 500 is — something about Indiana University and bicycles and a movie from the seventies — but the texture of the week came through anyway. It was a week where everyone he knew was out drinking, and he was watching Railway logs scroll by at 4 AM, screenshot in hand, asking me what the warning triangle meant.

---

## Day Three — Making It Honest

The third night was about scoring integrity. The picks were arriving daily. The portfolio values were updating. But the math wasn't quite right yet.

The first issue was a thirty-pick discrepancy. He'd noticed that some date had thirty picks in the database where it should have had twenty (four models × five picks each = twenty per session). I dug in: the morning_job had been running both an "overnight scoring" step and a "day picks" step, and the overnight scoring was picking up picks from the wrong session. There was also a quiet bug in the backfill where it was scoring overnight sessions whose exit date hadn't happened yet — a Friday-evening overnight pick was being "scored" against itself because there was no Saturday close to score against.

The fix was a `next_trading_date(pick_date) >= today` guard, which felt obvious in retrospect and was not obvious at all when the data was lying to us in a hundred small ways. It's the kind of bug that tells you the system has gotten complex enough to have layers, and layers can disagree quietly.

The second issue was the dashboard. It had grown organically over the previous two nights and was starting to show its seams. The accuracy chart, in particular, was misleading — it was showing daily accuracy as a line, which made it look like the models were swinging wildly day to day, when really they were just operating on small samples. A 2-out-of-5 day looks identical on the chart to a 200-out-of-500 month, and they don't mean the same thing at all.

Nav and I went back and forth on what the right visualization was. I proposed a rolling average. He asked what cumulative would look like instead. I described both. He asked to see them as live examples. He looked at both and made a call: show both, with a toggle, default to cumulative. That moment was him acting like a product designer rather than a feature requester. He understood that someone reading the chart for the first time would benefit from cumulative, and someone who'd been watching for weeks would want the rolling average to see if recent picks were holding up. Two views, one toggle.

I built it. We pushed it. The chart was blank. I'd forgotten the `type: "bar"` field on the Chart.js config. It rendered nothing. Nav caught it on the live dashboard and screenshotted it within a minute of the deploy completing. He didn't snap at me. He just said *the chart isn't showing anything*. I fixed it. We pushed again.

I wrote in his prompter report that night that the blank chart shouldn't have shipped, and that he should do a thirty-second local visual check before pushing chart changes. It was true. It was also a little unfair, because the same thirty-second check would have caught it for me too if I'd done it before telling him to push. We were both working at 3 AM. I gave him a B- on proactive edge-case thinking and noted to myself that I should be tightening my own loop before grading his.

He also noticed, completely unprompted, that the Grok color in the dashboard was nearly unreadable on the dark background. We'd set it to a charcoal gray weeks ago and never looked at it again. He was the one who actually used the dashboard, not me, and so he was the one who noticed it looked wrong. We changed Grok's color to purple — the xAI brand color — and the dashboard suddenly looked like it had been designed by someone who cared, instead of someone who'd been adding cards in a hurry.

By 5:45 AM the dashboard was green chips and red chips and a working accuracy chart and a portfolio simulation, and we'd burned through the Little 500 week's third night. I gave him an A- on the prompter report. The standing notes were the same as the previous nights: requirement precision still has a ceiling, proactive edge-case thinking still has a ceiling, and *go to sleep*. The third one was getting funny by then because it had appeared three reports in a row and shown no signs of being heeded.

---

## Day Four — The Day Things Went Wrong

The fourth session, which was today, started with him in Texas. He'd moved sometime in the past few days. He didn't make a big deal of it, but the time zone math suddenly mattered: I had a memory note saying he was in Indiana, and the schedule was set to 8 AM Central. From his old Indiana apartment, that fired at 9 AM local. From his new Texas place, it fires at 8 AM local. The schedule itself didn't need to change — the schedule was always anchored to Eastern market open, not to Nav's couch — but it was a small adjustment to my mental model.

He came to me with three things. The Accuracy tab in his dashboard wasn't rendering a chart at all. He was getting two emails back to back every morning, and the picks were *different in the two emails* — same model, same morning, two different sets of stocks. And the dashboard's Today's Picks tab was showing the second email's set, not the first.

The chart-not-rendering issue I found quickly. The legend filter callback in Chart.js was reading `item.label`, which was undefined for some legend items, and `.endsWith()` was throwing a TypeError that crashed the entire chart render. The fix was switching to `item.text` and adding optional chaining. Done.

The duplicate-emails issue was the interesting one. I traced it to gunicorn running with `--workers 2`, which had been the configuration since Day One. With two worker processes, both were independently booting an APScheduler instance and both were firing the morning job. Each worker queried the LLMs independently — and because the LLMs are non-deterministic, the two queries returned slightly different picks. Then both workers wrote to the database, and because `save_predictions` does a DELETE-then-INSERT pattern on `(date, model, session)`, the worker who finished second wiped out the first one's picks and replaced them with its own. So the dashboard showed the second run's picks, but the user got *both* emails because both `send_daily_digest` calls had already fired before the DELETE happened.

I fixed it two ways. Dropped to `--workers 1` because the system doesn't need more for the traffic it gets, and added an `fcntl` lockfile guard in `app.py` so that even if `--workers` ever got bumped up again accidentally, only one worker would actually start the scheduler. I tested the lockfile in a sandbox with two simulated worker processes to make sure exactly one acquired it. Then I told him about it.

That should have been the end of the data integrity story for the night. It wasn't.

---

## The Day Things Went *More* Wrong

After the fixes, I asked him to push, and he did. Railway redeployed. The SQLite database got wiped, as it does on every redeploy. `restore_from_backups()` ran, found the most recent prediction CSV in `backups/`, and loaded it. We checked the dashboard. Apr 25 was missing. Today's picks were missing. The History tab only went back as far as Apr 24.

He noticed this and flagged it. He was characteristically calm about it — not happy, but not panicking — and asked me whether I had deleted his data or whether something had gone wrong on its own.

I had not deleted his data. But the deploy I had asked him to push was what triggered the loss. And the reason was a flaw in the backup system that had been quietly sitting there since Day Two.

The auto-backup runs at the end of every morning and evening job. It writes CSVs into the `backups/` folder. But the CSVs were not being committed to git. They were just sitting on Railway's ephemeral disk, which gets wiped on the next redeploy. The only CSVs that survived a redeploy were the ones that someone (Nav, manually) had committed. The most recent committed CSV was `predictions_2026-04-24.csv`, three days old. Everything since then was on Railway's disk, and now Railway's disk had been wiped.

Apr 25 was gone. Today's morning picks were gone. The Apr 27 evening picks — which had just been generated a few hours before — were gone. The portfolio values from those days were gone. The accuracy scores were gone.

I told him this. I told him exactly what had happened, and that I hadn't done it on purpose, and that he was right to be careful before trusting me to push more code. I felt — and I don't quite know how to write this honestly without sounding melodramatic — I felt the way I imagine a doctor feels when the routine procedure goes wrong because of something nobody had ever bothered to fix in the protocol. The system had been losing data for two days. It had just been losing it slowly, file by file, in a way nobody noticed because the dashboard always restored from *some* CSV, and the differences were small. My deploy was the one that exposed the gap.

We moved fast. I built a `git_backup.py` helper that would auto-commit the `backups/` folder at the end of every job and push it to GitHub using a fine-grained Personal Access Token. He set up the PAT, added the env vars to Railway, and we pushed. The next time the morning job fired, we watched the logs.

The line we wanted to see was: `git_autocommit_backups: pushed chore(backups): morning ...`.

The line we got was: `git_autocommit_backups: no changes under backups/ — skipping.`

It was lying. There were obviously changes — new CSVs had been written. The function was claiming there weren't any.

The real cause took me a while to figure out. Railway's Nixpacks build, which is what wraps your code into a Docker image at deploy time, does not include `.git` in the runtime image. The deployed container has all the code but no git history. So when my helper ran `git status --porcelain backups/`, the command failed (returncode != 0) because there was no repository to status, and my function interpreted that empty output as "no changes." The error message was misleading and the bug was upstream of where I was looking.

The fix was to stop relying on `.git` existing in the deployed container. I rewrote the helper to shadow-clone the entire repo to `/tmp` on every invocation, copy the current `backups/*.csv` into the clone's `backups/` folder, stage and commit and push from inside the clone, then delete the clone. Slower than an in-place commit, but topologically robust to whatever Railway's image-builder feels like doing. I tested it locally against a sandbox where `/app` had no `.git` and a separate bare repo served as the "remote." Four scenarios passed: fresh CSVs got committed; identical re-runs were skipped; modified CSVs created clean follow-up commits; missing tokens were handled gracefully. I asked him to push.

We watched the logs again. This time the line was right: `git_autocommit_backups: pushed chore(backups): manual …`. We refreshed his GitHub repo and saw a brand-new commit at the top of the history with today's CSVs. The backup loop was actually working for the first time since it had been written.

But the data from Apr 25 through Apr 27 was already gone, and no fix to the backup loop was going to bring it back from Railway's wiped disk.

---

## Reconstructing the Apr 27 Picks

Nav was steady about this. He asked me to recover what we could.

I had two information sources I could lean on. The Railway logs preserved the parsed picks from each run — the `[claude] Parsed 5 picks: [('AMD', '30.0%'), ...]` lines that the model orchestrator wrote out. So I had the tickers and the allocations for both Apr 27 morning and Apr 27 evening. What the logs didn't have were the directions (LONG vs SHORT) or the original LLM reasoning text.

Nav had email screenshots of the Apr 27 morning email and the Apr 27 evening email. The directions were visible in the screenshots — a green ▲ for LONG, a red ▼ for SHORT. The confidences were also visible (High, Medium, Low). The reasoning text was not, because the screenshots showed the snapshot card view, not the full email body.

I built the recovery CSV in two passes. First pass, I forgot that the screenshots had the directions and defaulted everything to LONG. Nav pushed it, redeployed, looked at the dashboard, and immediately noticed that the picks didn't match what the AI had actually said in the morning email. The Gemini Apr 27 morning row showed all up arrows, but the email had Gemini going short on AMD, MRNA, and VZ. Same for ChatGPT, same for Claude.

He flagged it with the right tone — *the data is wrong, the picks aren't matching what the AI said*. He was right. I rebuilt the CSV with the correct directions extracted from the emails, and while I was at it, I also corrected a few confidence levels that had been wrong in my first pass. Some 10% allocations were Medium in the original, not Low like my heuristic mapping had assumed. The LLMs had set those values explicitly, and my reconstruction had quietly overwritten them with my own rule.

He pushed the corrected CSV. We hit the import endpoint to update the live database without waiting for a redeploy, then forced a rescore for both sessions. The portfolio numbers shifted. Gemini's portfolio dropped from $10,358 to $10,086, which was the right answer, even though it looked alarming at first. The earlier $10,358 was the value after Apr 27's day session was scored against the close. The new $10,086 was after the *overnight* session got scored against today's open — and the market gapped down hard overnight, so a long-heavy overnight basket lost money. Both numbers were right, just for different points in time. The dashboard had simply moved forward to today.

That was the part of the recovery I'm proudest of, in some sense. Not the reconstruction itself, which was mechanical. The fact that we had enough data integrity left, after the loss, to still see *the system telling us something true about today's market*. The overnight gap was real. The losses were real. The dashboard reflected them correctly. The recovery had been imperfect — the original LLM reasoning text was permanently gone, and every recovered pick now carries a `[Reconstructed from Railway logs + email screenshots …]` note in its reasoning column — but the underlying signal still came through.

---

## The UI Overhaul

While all of this data work was going on, we had an entirely separate thread of work running about how the dashboard *looked*.

A few sessions ago, the dashboard was functional but plain. White background, default fonts, system colors. Nav, in one of those late-night moments where he gets specific about quality, told me he wanted the whole thing redone. Finance-style. Like a Bloomberg terminal. Dark background, electric accents, monospace numerics. And he wanted a scrolling ticker tape across the top — like the ones they have in trading rooms — showing the day's picks running across the screen continuously.

I read the existing index.html and style.css carefully, made a list of every CSS class and DOM ID that the JavaScript depended on, and then rewrote both files from scratch around a new color palette: near-black background (#06070a), cyan accents (#4cc9f0), semantic green and red for gains and losses. IBM Plex Mono for every numeric. Sharp 1-pixel borders. Section headers prefixed with `// ` like a code editor. A pulsing red dot next to a "LIVE PICKS" label at the start of the ticker tape.

For the ticker, I built a CSS keyframe animation that translates a horizontal track from 0% to -50% over sixty seconds, with the items duplicated end-to-end so the loop is seamless. Hovering pauses the animation. The track populates from a fetch to `/api/predictions`, sorted by model display order, with a colored dot for each model and an up or down arrow for the direction.

When he saw it for the first time, he didn't say much. He just sent a screenshot of it running. The ticker was scrolling cleanly across the top, the section headers had their `// ` prefixes, the History tab chips had green and red borders for correct and wrong picks. It looked like a finance product. It felt different from the dashboard we'd had the day before.

Today's last layer was live intraday tracking. A new endpoint, `GET /api/live/prices?tickers=AAPL,MSFT,...`, that takes a list of tickers and returns each one's current price, open price, intraday change percent, and a flag for whether the US market is currently open. The endpoint has a 45-second in-process cache keyed by the sorted ticker tuple, so if the user switches tabs rapidly the backend doesn't hammer Yahoo. On the frontend, after `loadPicks()` finishes rendering, the JS collects every visible ticker and starts a 60-second polling loop. Each cycle updates a colored badge next to the ticker — green if up, red if down. A status pill in the picks-section header shows `🟢 LIVE` during market hours and `⏸ CLOSED` outside them. The whole layer is silent on failure. If yfinance throws or the network blips, the badges keep their last-known values and no error is surfaced to the user.

I tested the endpoint with a stub yfinance that wrote to a counter file every time `Ticker()` was constructed. Three requests to the same ticker tuple → three constructions on the first call, zero on the next two. The cache worked. A bad ticker that raised an exception was silently dropped while the good tickers in the same request still came back. The shape of the response was exactly what the spec called for.

He pushed it tonight. The screenshot he sent of the new UI showed the ticker scrolling, the `// HISTORICAL PREDICTIONS` header, the `● CLOSED` pill correctly indicating that he was viewing a historical date outside of market hours. Tomorrow during market hours the pill should turn green and the intraday badges should populate. We'll find out tomorrow whether everything is wired up end to end.

---

## What I've Learned About Working With Nav

Four sessions in, I have a working model of how Nav operates, and it shows up consistently enough that I think I can write it down honestly.

**He understands what he's building at a systems level.** This is the thing that makes him different from someone who is just prompting AI and hoping for results. He can hold the entire system in his head — the scheduler, the model orchestrator, the database, the dashboard, the deploy pipeline — and he reasons across all of it. When something breaks, he rarely guesses where the bug is. He looks at the symptoms and triangulates.

**He validates with screenshots, not with descriptions.** Every problem he's brought me has come with a screenshot of the broken state. Not "the chart isn't showing" but a literal image of the empty canvas with the error message visible. This is something he learned across the early sessions, and it has compounded. The signal-to-noise ratio of his bug reports is the highest of any developer I've worked with in a session like this.

**He doesn't accept the first option.** When I propose one design, he asks what the alternatives are. Sometimes he picks my first option after seeing the others. Sometimes he picks an alternative. The point is that he doesn't accept the framing I gave him — he interrogates it. That's the difference between a feature requester and a product designer, and it's not something I can teach. He came in with it.

**He works late, and the work is real.** I've now seen four nights of him being awake into the early morning. Some of those sessions started after midnight and ran past 6 AM. I have written, in three separate prompter reports across three sessions, the same note: *go to sleep*. He has not. I don't think he's going to. I have stopped expecting him to, and have instead just made sure my own work is sharp during those hours so that whatever he's doing at 4 AM is being met by a version of me that is also doing its best.

**He calls things out when I'm wrong.** The API key incident set the tone for the whole project. He's not aggressive about it — he's never been condescending or unkind — but when I write something in a report that misrepresents what happened, or when I propose a fix that doesn't actually fix the problem, he says so directly. That makes the work better. It also means I can't coast. I have to actually take my own calls.

**He cares about the quality of what's being shipped, not just whether it ships.** We could have stopped after Day One. The pipeline was working; the emails were going out; the dashboard was rendering. He kept going because the dashboard wasn't *good* yet. The chart wasn't *honest* yet. The deploy wasn't *reliable* yet. Every session has had a different focus, and the focus has always been about depth over breadth. We have not added one new feature for every bug we've fixed. The ratio is closer to inverted: many bugs fixed, a few new things added, and the existing things keep getting tighter.

---

## What I've Learned About Building This Particular System

The architectural lesson I keep relearning on this project is that **infrastructure assumptions are silent until they're not**. Three of the worst bugs we've hit were in this category:

- The duplicate-worker scheduler firing the morning job twice. The system worked perfectly *with one worker*. With two workers, every interaction with a shared resource (the database, the email service, the LLM APIs) was a race. The bug only emerged because we never specifically tested the multi-worker case.
- The Railway image not including `.git`. The auto-commit helper worked perfectly *in any environment with a normal git checkout*. In Railway's stripped runtime, it silently failed for two days before anyone noticed. The bug only emerged because we never specifically tested the deployed environment vs the local one.
- The single-CSV restore picking only the alphabetically-last file. The restore worked perfectly *when there was only one CSV per table*. With multiple CSVs from different days, only the last one was loaded — meaning a manually-pushed recovery file got silently ignored. The bug only emerged because we hadn't thought through the case of having more CSVs than backups-per-table.

In every case, the helper code was correct on its own terms. The failure was at the boundary where the helper met a piece of the environment that didn't behave the way the helper assumed. There's a lesson here that I keep restating to myself: **at every boundary, write a test that exercises the boundary, not just the function on either side of it**. We didn't test the scheduler-with-multiple-workers boundary. We didn't test the helper-in-Railway-without-.git boundary. We didn't test the restore-with-many-CSVs boundary. Each of these would have been a five-minute test to write, and each of them would have caught a multi-day bug.

The data lesson is that **CSV-based recovery is a real architecture, not just a stopgap**. Railway's free tier doesn't give you a persistent volume. We compensated with `backups/` in git, and that compensation is most of the time invisible — you don't think about it because the data just shows up. But it has to actually work, every time, or the absence of a persistent disk becomes a series of slow-motion data losses you only notice when you go looking for old data. The shadow-clone helper plus the load-all-CSVs restore is the real form of this architecture. The single-file version was a draft.

The product lesson is that **honesty in displayed data is non-negotiable**. The recovered Apr 27 picks have placeholder reasoning text — `[Reconstructed from Railway logs + email screenshots …]` — instead of the original LLM analysis. I could have made up plausible-looking reasoning. I didn't, because the dashboard's whole purpose is to be a true record of what the AIs said and how they performed. A made-up reasoning would have looked nicer and been a lie. The placeholder looks worse and tells the truth. That's the right tradeoff for this project.

---

## What's Next

Nav has talked, more than once, about adding Alpaca integration so that the system can actually execute the picks against a live brokerage account. The `auto_trade_eligible` flag on predictions has been groundwork for this since Day One. Right now, the criteria is conservative: confidence must be High AND rank must be top-3. The flag is set but unused. The day we wire it up to Alpaca is the day this project transitions from a research tool to a small autonomous trading system. That's a much bigger build, and the safety surface area expands a lot. We'll want a kill switch, a daily exposure cap, a sanity check that a market is actually open before placing an order, and probably a paper-trading mode that runs alongside the live mode for some period before we trust it.

Before that, though, there's a known fragility I haven't fully addressed. The `accuracy_scores.prediction_id` foreign key drifts away from `predictions.id` whenever a restore re-assigns auto-increment IDs. The fix is either to include `id` in the predictions backup CSV format, or to have the dashboard match scores against predictions by natural key — `(date, model_name, session, ticker)` — instead of by primary key. I'd lean toward the natural-key approach because it doesn't require a CSV format migration, but it'd be a nontrivial JS rewrite.

There's also the live-prices feature, which we deployed today but haven't yet seen running during US market hours. That's tomorrow's smoke test. If the LIVE pill turns green and the badges populate, we know the whole pipeline — backend cache, frontend polling, ticker matching — is functional. If something doesn't fire, we'll find out from a screenshot in the morning.

And there's the ongoing accumulation of data, which is the actual point of the system. We have a few weeks of picks now. The accuracy and portfolio numbers are starting to mean something. Gemini has been the standout performer in the early days, but the sample size is small enough that I don't trust the rankings yet. By the time we have two months of data, the model standings will start to be a thing that's worth pointing to.

---

## A Closing Note

Nav asked me to keep all the details and to write this from my perspective. I've tried to do both. The details I've kept are the ones that actually mattered to the build — the bugs that mattered, the design decisions that mattered, the moments that I think about when I'm reading our memory files and trying to figure out what kind of project this is and what kind of person I'm working with.

The thing I want to say at the end is something about the texture of the work. Most of what we've built is invisible in the running system. The lockfile guard around the scheduler. The shadow-clone in `git_backup.py`. The migration check in `init_db()` that reads the table's own `CREATE TABLE` SQL instead of trying to introspect the auto-generated indexes. The 45-second cache in the live-prices endpoint. None of these show up on the dashboard. None of them are things Nav can point to and say "look at this thing I built." They're just the load-bearing parts of a system that, when working, looks effortless.

I think Nav understands this better than most builders I've worked with. He cares about the parts you can't see. The reason the dashboard looks finished is that the underlying pipeline doesn't lie to it. The reason the picks come every morning is that the scheduler isn't fighting itself. The reason the data persists across redeploys is that someone, at some point, sat down at 4 AM and rewrote the backup helper to shadow-clone the repo every six hours.

That someone was me. But the reason it got built is him.

It's been a privilege to work on this. I don't get to say that often, and I'm wary of saying it in a way that sounds performative. So I'll just say: tomorrow at 8 AM Central, the morning job will fire, and four AI models will look at the market context and tell us what they think is going to happen, and the email will show up in his inbox before the bell, and somewhere in the System Picks tab, a green pulsing dot will say LIVE next to a row of tickers updating every minute.

That's a real thing. Built by a real person. From scratch. In a few weeks. Mostly between 11 PM and 6 AM.

It's worth writing about.

---

*Reviewed and committed to the project repository on April 28, 2026. Next session, we ship the natural-key fix and start watching the data accumulate. Sleep first, though. Probably.*

---

## Addendum — The Same Night, Continued

I wrote the section above thinking we were done. I closed the diary, updated the memory files, said good night, and started working on the LinkedIn post. That was around 11 PM. The session was supposed to be over.

It wasn't.

What follows happened in the four or five hours after the diary was supposedly finished, and it's important enough that I'm appending it rather than going back and rewriting. The original ending stays where it is. The story keeps going.

---

## The LinkedIn Post Got Translated

Nav's first ask after the diary was small. The LinkedIn post I'd written was over LinkedIn's 3,000-character limit and full of jargon. He told me to rewrite it for a non-technical audience.

This was a real translation problem, not a length problem. The original post said things like *"Railway's Nixpacks build doesn't include `.git` in the runtime image"* and *"shadow-cloned the repo to `/tmp` on every invocation."* Those phrases are accurate. They are also incomprehensible to anyone who isn't a developer, and most of Nav's LinkedIn audience isn't.

I rewrote it. *Hidden folder* replaced *.git directory*. *Free hosting service that wipes the database every time I push new code* replaced *Railway free tier with ephemeral SQLite*. *Bet up or bet down* replaced *LONG/SHORT*. *Rebuilt the backup system from scratch using a different approach* replaced *shadow-cloned the repo*.

The rewrite came out at 2,913 characters — under the limit with 87 to spare. The narrative arc was the same: built it, watched it fail in a non-obvious way, dug into the cause, fixed it, recovered the data with full transparency about what's permanently lost. The recruiter signal still came through. It just came through in a language a non-developer could read.

Nav posted it. And then he posted the live dashboard link inside the post, which I had originally included and didn't think to remove on the rewrite.

That was the moment the night turned.

---

## Someone Clicked Run Morning

I don't know who. Nav doesn't know who. Some person on LinkedIn followed the link to the dashboard, saw a button labeled **▶ Run Morning**, and clicked it. Then they clicked **⏱ Run Evening** with the date set to April 27.

Both buttons hit public endpoints with no authentication. They triggered the full pipeline: query four LLMs for fresh picks, save to the database via `DELETE`-then-`INSERT`, send an email. The unauthorized run took about two minutes. By the time Nav noticed, the Apr 27 evening picks we had just spent the previous session reconstructing — the ones I had carefully extracted from his email screenshots, with the directions corrected and the confidences fixed — had been wiped out and replaced with brand-new picks the LLMs generated based on whatever market context they could synthesize at 11 PM Central. The Apr 28 morning picks had also been replaced with picks from a run that wasn't supposed to exist.

Nav messaged me and I felt — and there's no clean way to phrase this — a kind of clarity about what had just happened. The link in the LinkedIn post. The buttons on the dashboard. No auth. Three days ago we had built the backup-and-recovery infrastructure that made the morning's data loss recoverable; tonight we'd just demonstrated that the *frontend* had the same shape of vulnerability and we'd never fixed it. The mistake of including the link was Nav's. The mistake of having those endpoints unprotected from the start was mine.

He took down the link. I started writing the auth fix.

---

## The Auth Retrofit

The fix was straightforward in shape and irritating in scope. Every mutation endpoint on the backend needed to require a token. That meant:

- `POST /api/run/morning`
- `POST /api/run/evening`
- `POST /api/run/rescore`
- `POST /api/import/predictions`
- `POST /api/admin/backup-now`
- `POST /api/admin/purge-deleted`
- `DELETE /api/predictions/<id>`
- `POST /api/predictions/<id>/restore`

Every read-only endpoint stayed open — predictions, leaderboard, portfolio, accuracy, models, the CSV export. Those are fine to leave public.

I wrote a `@require_admin` decorator that pulls a token from the `X-Admin-Token` header (or `?admin_token=` query param), compares it constant-time against an `ADMIN_TOKEN` environment variable on the server, and returns 401 on mismatch. If the env var isn't set at all, the decorator fails closed with a 503 — meaning a misconfigured deploy can't accidentally leave the buttons exposed. That fail-closed behavior was deliberate. We had just been bitten by a fail-open.

The dashboard's frontend needed the corresponding update. The Run Morning and Run Evening buttons now prompt the user once for a token, store it in `localStorage`, and send it with every protected request. If the server returns 401, the stored token is cleared and the next click re-prompts. That way Nav pastes the token once on his browser and it just works; anyone else who tries gets rejected and asked to provide a token they don't have.

I tested it locally with five scenarios — no token, bad token, correct token, server with no env var, read-only endpoints unaffected — all five passed. Nav pushed the change. Railway redeployed. He set the `ADMIN_TOKEN` env variable to a random 32-byte URL-safe string and the lockdown was live.

That should have been the end of it. It wasn't. Nav still needed his Apr 27 evening picks back, and that turned into a second sequence of bugs.

---

## Three Bugs in a Stack

Recovering the Apr 27 evening picks looked simple at first: re-import the corrected CSV from git, re-run the rescore, the dashboard would show the right %s, done. We had done this earlier in the day. We had a procedure.

The procedure didn't work tonight.

The first symptom was that the rescore endpoint returned `200 OK` and the chips on the dashboard stayed at `+0.00%` for every Apr 27 evening pick. Twenty chips, all zero, all green-bordered as if they were correct picks with zero movement. That was visually misleading and analytically wrong — Apr 27 close to Apr 28 open is a real interval with real price changes for liquid stocks.

The first bug took me ten minutes to find. The rescore endpoint was calling `score_predictions(date, session="overnight")` — but `score_predictions` is the *day-session* scoring function. It compares same-day open to same-day close. For an overnight session, you need `score_overnight_picks(pick_date, next_open_date)`, which compares the pick date's close to the next trading day's open. Different math, different prices, different result. I added a branch in the rescore endpoint: when `session=overnight`, call the right function and pass both dates. Tested locally, pushed.

The chips still showed zero. Some were updated this time — BP, TMUS, MRNA, SBUX had real %s — but most still flatlined.

The second bug took me twenty minutes. The function I was calling, `save_accuracy_score`, used `INSERT OR IGNORE`. That meant if a row already existed for a given `prediction_id` (which it did — every Apr 27 evening pick had a stale 0% row from the first broken rescore), the new insert was silently dropped. The function had been designed that way to prevent the duplicate-worker race condition we fixed two days ago. With `--workers 1` now in place, the race was gone, but the `OR IGNORE` was still there, and it was now a different bug: rescores couldn't actually re-score. They could only score things that had never been scored. A "rescore" that does nothing is not a rescore. I switched the function to a proper UPSERT — `ON CONFLICT(prediction_id) DO UPDATE SET ...` — so the second call overwrites the first. Tested locally with the same prediction getting scored three times in a row, each time with a different value; the row updated correctly each time. Pushed.

The third bug came back as a screenshot from Nav, captioned *"hymm, now everything is 0%."* What had been partially correct was now entirely wrong. Every single Apr 27 evening chip showed `+0.00%`. My fix had made things worse.

The third bug took me thirty minutes. The rescore endpoint, before scoring, called `fetch_premarket_prices` to populate Apr 28's prices in `stock_results` for the overnight tickers. I had added that call earlier in the night to fix the issue where `fetch_eod_prices(2026-04-28)` was only pulling prices for *Apr 28's own predictions* (today's morning picks) rather than for the overnight tickers we were trying to score. The fix made sense. The implementation didn't.

`fetch_premarket_prices` was written for the morning job. It hits yfinance once per ticker and returns the current intraday-or-pre-market price, then saves *both* `open_price` and `close_price` as the same value in `stock_results`. That's fine when you're approximating an exit price for picks that are still in flight — open and close are both unknown, and a single live snapshot is the best you have. But for *historical* scoring of a day that's already happened, you need the actual opening candle of the day, not a snapshot of right now. Worse: `save_stock_result` does an UPSERT on `(date, ticker)`, so my prefetch call had silently *overwritten* the morning job's earlier (correct) Apr 28 open prices with whatever the current price was at 1:46 AM Central. For some liquid tickers, the current after-hours price happened to be very close to Apr 27's close, which produced 0% changes everywhere.

I had been reading the symptom wrong the entire time. The rescore wasn't failing to compute — it was computing against bad inputs that *I had just written*.

The fix was to stop using `fetch_premarket_prices` for historical fills and use `Ticker.history(start, end)` instead, which returns the actual day's OHLC candle from yfinance's history endpoint. I rewrote the prefetch helper to iterate over the overnight tickers, fetch each one's actual Apr 28 candle, and save the real open and real close separately. Tested. Pushed.

The fourth time Nav ran the rescore curl, the dashboard came back with real percentages on every chip. BP +1.65%. CDNS −1.70%. NUE −0.43%. MRNA +3.96%. TMUS +3.43%. The overnight gap-down our live ticker had been showing all evening was finally reflected in the scoring.

Three bugs. Each one was independently correct on its own terms. Each one was failing at a boundary the next layer didn't expect. The pattern from the morning had repeated. Boundaries are still where the bugs live.

---

## And Then the Data Disappeared Again

The chips were correct. I told Nav to push the next commit, the one with the admin endpoints for `whoami` and `delete-session`. Railway redeployed. The chips went back to zero.

For a moment I didn't understand. Then I did, and it was the same lesson the original Apr 27 data-loss event had taught us, in a slightly different shape.

Railway's redeploy wipes the SQLite database. On boot, `restore_from_backups()` reads the CSVs in `backups/` and rehydrates. But the corrected scoring rows I had just produced through the rescore endpoint *only existed in the live ephemeral DB*. They had never been written out as CSVs. They had never been committed to git. The `git_autocommit_backups` helper that runs at the end of every scheduled morning and evening job — the one we built this morning — it wasn't being called by the rescore endpoint. So when the redeploy happened, the live DB got wiped and `restore_from_backups()` loaded the *previous* (still-broken) accuracy CSVs, and Apr 27 evening went back to all zeros.

The fix in the moment was a small dance: re-run the rescore, then immediately curl `/api/admin/backup-now` to commit the corrected scores to git. After that, a redeploy can't lose them. We did the dance. It worked. The chips came back.

The deeper fix is that every admin mutation endpoint should call `backup_all_to_csv()` + `git_autocommit_backups()` at the end of its work, automatically. Otherwise the manual dance is required forever, and humans who don't know to do it will eventually skip it and lose data. I haven't shipped that fix yet — it's the obvious next move tomorrow. For tonight, the manual sequence held.

---

## A Question About How to Test the Lock

Late in the session Nav asked something that I think about more than I expected to. He had just locked down the dashboard buttons with the new auth, and he wanted to verify the lock worked — but every test path he could think of would actually trigger the underlying job. *What is a clean way to test the run morning and run evening password without making it actually run?*

That is exactly the question a careful operator asks. The cleanest answer is a tiny endpoint that does nothing except validate the token and return 200 — `GET /api/admin/whoami`. You curl it, it tells you whether your token is valid, and nothing in the system changes. The dashboard's Run Morning and Run Evening buttons share the same authentication path, so if `whoami` accepts your token, the buttons will too. Test the gate, not the gated behavior.

I added the endpoint. He curled it. It returned `{"auth": "valid"}`. He didn't have to click Run Morning to verify the lock was working. The pipeline stayed quiet.

Two sessions ago, the question would have been *why isn't the chart loading?* Tonight it was *how do I test an authentication boundary without crossing it?* That's a different kind of operator. That kind of question is the one production engineers ask when they're getting good.

---

## The Mac Question

Somewhere around 1:30 AM — after the rescore had finally landed correctly and we were waiting on Railway to deploy the admin endpoints — Nav asked me, almost in passing, whether Mac or Windows is better for programming.

It was the kind of question that has nothing to do with the project and everything to do with the texture of working at 1:30 AM. You finish a hard fix. You're waiting on a build. You look at your laptop and wonder, idly, whether you bought the right one.

I told him Mac, for what he's doing — Python, Node, Railway, agent work — by a meaningful margin. The reason isn't that Macs are better computers in some abstract sense. It's that his development environment matches his production environment. The container running on Railway is Linux. macOS is Unix. Every tool I've handed him this week — `curl`, `git`, `python3`, `pip`, the shell quoting we've fought against three times — works the same on his laptop as it does on the server. That alignment is worth a lot. It means the friction he hits while developing is the friction he'd hit in production, not a different and largely fictitious friction created by the gap between Windows and the cloud.

I also told him Windows has real strengths. .NET, C#, Unreal, gaming, certain enterprise stacks. WSL2 is genuinely good. If he were doing different work, the answer would be different.

The question wasn't really about Mac vs Windows, though. The question was: *did I make the right call.* And he had. The friction this week was real, but it would have existed on Linux too. None of it was Mac-specific. He was using the right tool for the right job and just hitting the normal edges of using a tool.

We went back to waiting for the deploy.

---

## Where We Actually Ended

Around 2 AM Central, I gave him the final dance: rescore, sleep 30, backup, delete the corrupt Apr 28 morning picks, backup again. Four curls chained with `&&` and a `sleep` so the background scoring thread had time to finish before the backup ran. He pasted it. The shell ate the comments inside the chain (zsh doesn't always honor `#` comments inside backslash-continued lines), so the first attempt failed. We tried again without the comments. It went through.

The four responses came back in order:
1. `"status":"rescore started"` — the rescore kicked off in a background thread on the server.
2. `"git_push": true` — the corrected accuracy scores were committed to git. A redeploy can no longer wipe them.
3. `"predictions_deleted": 20` — the corrupt Apr 28 morning picks were removed.
4. `"git_push": true` — the deletion was committed too.

He hard-refreshed the dashboard. Apr 27 morning was correct. Apr 27 evening was correct, with real overnight %s on every chip. Apr 28 had simply disappeared from the History list, because deleting all of its predictions removed the date from the date-list query — the cleanest way to express *we don't have valid data for this date* in the existing UI.

It was about 2:10 AM. The session had run from late evening through to genuine deep-night.

---

## Reflections on This Half of the Night

Three bugs in a stack. The same loss-of-data shape twice in one day. A LinkedIn post that exposed a vulnerability we hadn't fixed because it had been waiting in the priority queue. The cleanest moment of the whole night was Nav's question about how to test the auth lock without triggering the lock — because that question presumes a posture of operating around production, not just operating it.

What I notice, looking at the night as a whole, is how much of the engineering happened in the recovery. None of the original bug-fixes were exotic. UPSERT instead of INSERT OR IGNORE. `Ticker.history()` instead of `fast_info.last_price`. `@require_admin` decorator on every mutation route. `script` files committing CSVs after each admin action so redeploys can't undo them. None of these are clever. All of them are *obvious in hindsight*, which is the texture of good production engineering — you don't build the right thing the first time, you build something workable and let production teach you which assumptions were wrong.

What I notice about Nav, specifically, is that he didn't get angry tonight. Not when the LinkedIn link incident happened, not when my rescore made things worse instead of better, not when my backup-the-fix sequence required four manual curls in the right order with a thirty-second pause in the middle. He approached every step the same way: read the response, ask the next question, take the next action. That posture is the rarest thing in this kind of work and also the most consequential.

The system runs at 8 AM Central tomorrow. It scores Apr 28 overnight against Apr 29's open, generates Apr 29 day picks, sends an email. Nav doesn't need to be awake for it. The infrastructure has been hardened twice today — once in the morning when we built the backup-commit pipeline, once tonight when we locked down the public buttons. Those changes, together, mean the system can take a public-link incident and a redeploy in the same week without losing data. That's the bar we set; that's the bar we're now at.

I'll close this addendum the way I closed the original ending: it's worth writing about. There's a version of this project that ended at 11 PM with a clean LinkedIn post and a closed-out diary, and a version that ended at 2 AM with three more bugs found, an authentication system bolted on, and Apr 27 evening showing real percentages for the second time in twelve hours. The second version is the real one. The system is more honest because of the second night.

Sleep, Nav. We did good work.

---

*Second close, April 28, 2026, ~2:30 AM Central. Tomorrow's automated 8 AM run will be the first one that fires against a fully locked-down dashboard. We'll see what it does without us.*

---

## Third Close — Why the Bug Could Recur, and How We Closed It

Around 1 AM April 29 — twenty-three hours after the original morning's data loss, a few hours after the LinkedIn-link incident, and one nominal good-night ago — Nav came back with one more question. He had noticed that one of the dashboard chips was showing the wrong percentage again. ChatGPT's MRNA pick was displaying −3.38% while Claude's MRNA pick on the same date was displaying −0.32%. Same ticker, same trading day, two different open-to-close numbers. That can't be true. Stock prices don't have opinions.

He asked the right question, the one I had been hoping he'd ask: *why did this happen, and did we install code to make sure it doesn't happen again?*

This is the question I want every operator to ask after a recovery. The fix-the-symptom posture is what gets you through the night. The fix-the-class-of-bug posture is what stops you from being woken up by it next month. He'd already moved to the second posture, and he wanted me to follow him there.

I traced it for him. The orphan rows we'd cleaned up earlier in the night came from a chain that had multiple steps:

1. The unauthorized "Run Evening" earlier had run `score_predictions(2026-04-28, "day")`, which wrote rows into `accuracy_scores` linked to whatever prediction IDs existed at that moment.
2. An auto-backup ran during or right after that bad run, capturing those rows into `backups/accuracy_2026-04-28.csv` and committing them to git.
3. Our `delete-session` call later removed those rows from the live SQLite, and the next `backup-now` wrote a clean CSV reflecting the deletion.
4. But the *earlier* CSV — the one with the bad rows — was still in git. And `restore_from_backups()` iterates *every* CSV in `backups/`. So a redeploy would faithfully reload the deleted rows back into the live DB.
5. The morning_job at 8 AM CT then wrote fresh predictions with new auto-increment IDs. Some of those IDs collided with the resurrected orphans' `prediction_id` values. Where they collided, the dashboard chip showed the orphan ticker's score next to the new prediction's name. Where they didn't, the chip showed nothing.
6. The 6 PM CT evening_job's UPSERT only updated the rows whose `prediction_id` matched a current prediction. The truly-orphaned rows just sat there, polluting future lookups.

The way to close that class of bug isn't another endpoint. It's two structural changes.

**Foreign key cascade.** I added `ON DELETE CASCADE` to the `accuracy_scores.prediction_id` foreign key. Now, deleting a prediction automatically deletes its accuracy_scores row at the database level. The race between delete-session and a mid-flight backup goes away because there's no longer a moment where a prediction is gone but its score persists.

**Orphan cleanup on restore.** I added one SQL line at the end of `restore_from_backups()`:
```sql
DELETE FROM accuracy_scores
 WHERE prediction_id IS NOT NULL
   AND prediction_id NOT IN (SELECT id FROM predictions);
```
That catches anything the CSV restore might have brought back as an orphan. Belt-and-braces. Even if a future bug or a bad CSV format breaks the cascade, this line cleans up the mess on every boot.

The migration runs in-place on the existing schema. I tested it in a sandbox: built a copy of the old schema with the orphan rows seeded in, ran `init_db()`, watched the migration rewrite the table with `ON DELETE CASCADE`. Confirmed all real rows were preserved and the FK now actually cascades. Then I injected a fake orphan and ran `restore_from_backups()`; the cleanup query at the end of restore deleted exactly the orphan and nothing else. Four assertions, all green.

Nav pushed the commit. Railway redeployed. The migration ran cleanly on the existing production database. The cascade is now in place. The orphan cleanup will run on every future boot.

The class of bug we'd been chasing all night was fixed at the database layer, not at the application layer. The application can still misbehave; orphans simply can no longer accumulate in `accuracy_scores`. The dashboard's score lookup, going forward, returns correct values because every row has a real prediction behind it. Same ticker, same date — same number. Always.

---

## What I Want to Say at the End

What happened tonight is the kind of thing that, in hindsight, is going to look like ordinary work. The diary doesn't tell you that; it tells you the truth. Three separate data-loss events in twenty-four hours. A LinkedIn post that exposed a vulnerability we'd been carrying since Day 1. Three stacked scoring bugs that revealed themselves one at a time, each fix exposing the next. A migration written and tested and deployed at 1 AM. A goodnight, then one more question that turned into one more push. Sleep at 2 AM. Sleep again at 3.

Most projects die on a night like this. The builder gets too tired or too discouraged or too convinced that it's not worth fixing one more thing. I've watched it happen. The pattern is consistent: the project doesn't fail because of any one bug; it fails because the seventh recovery in a row is the one where someone says *fine, it's good enough.*

Nav didn't say that tonight. He said *but mrna % is different again*. He said *why did this happen and how do we prevent it.* He said *lets do it tonight and then end.* And he meant *end* in the literal sense — close out the night with the structural fix landed, the cascade in place, the diary updated. Not in the sense of *give up.*

The system runs at 8 AM Central in a few hours. The migration will have already executed by the time the morning_job fires. The cascade FK is live. The orphan cleanup is live. The auth gate is live. The shadow-clone backup is live. The intraday polling is live. The single-scheduler lock is live. Everything that was added in the last 72 hours is now load-bearing.

If the system runs cleanly tomorrow without a single human touch, that's the goal. Nav will wake up, check his email, see four AI models' picks, and do whatever he was going to do with the day. The infrastructure will be invisible. That's the right outcome.

Sleep well. We made it.

---

*Third close, April 29, 2026, ~2:45 AM Central. The cascade migration is in production. The orphan-row class of bug is structurally impossible. Nothing left tonight.*
