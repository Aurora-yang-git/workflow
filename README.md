# Daily News Companion

A personal AI news digest that runs entirely on GitHub Actions — no servers, no hosting, no cost beyond API calls.

Every morning it fetches and scores the day's tech news, posts a bilingual (中文/English) summary as a GitHub Issue, and sends a curated card to DingTalk. On Sundays it writes a narrative of the week's top story arcs. It remembers past stories to flag follow-ups, and answers questions you leave in issue comments.

## System flowchart

```
                        ┌─────────────────────────────────────────────────┐
                        │             GitHub Actions (cron)               │
                        └───────────────────┬─────────────────────────────┘
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               │  Daily — 8 AM UTC          │          Sunday — 10 AM UTC │
               ▼                            │                             ▼
  ┌────────────────────────┐                │           ┌─────────────────────────┐
  │   Horizon (DeepSeek)   │                │           │    arc_digest.py        │
  │  HackerNews · Reddit   │                │           │  reads memory.json      │
  │  RSS · NewsAPI         │                │           │  → DeepSeek             │
  └──────────┬─────────────┘                │           │  "top 3 story arcs      │
             │ summaries/                   │           │   this week"            │
             ▼                              │           └──────────┬──────────────┘
  ┌──────────────────────┐                  │                      │ arc narrative
  │  memory_manager.py   │                  │                      ▼
  │  · dedup             │           ┌──────┴──────────────────────────────┐
  │  · entity extract    │           │         post_issue.py               │
  │  · follow-up annot.  │──────────▶│  create GitHub Issue (EN + ZH)      │
  └──────────────────────┘           │  send DingTalk ActionCard           │
             │                       └──────────────────────────────────────┘
             │ commit                               │
             ▼                                      │ Issue URL
  ┌──────────────────────┐              ┌───────────▼───────────┐
  │   memory.json        │              │   GitHub Issues tab    │
  │  (365-day rolling)   │              │   (public or private)  │
  └──────────────────────┘              └───────────┬───────────┘
                                                    │ user leaves comment
                                                    ▼
                                        ┌───────────────────────┐
                                        │  qa-responder.yml     │
                                        │  (on: issue_comment)  │
                                        └──────────┬────────────┘
                                                   │
                                                   ▼
                                        ┌───────────────────────┐
                                        │   qa_responder.py     │
                                        │  1. fetch issue body  │
                                        │  2. DeepSeek:         │
                                        │     · find article    │
                                        │     · cite + answer   │
                                        │     · bilingual reply │
                                        └──────────┬────────────┘
                                                   │ bot reply comment
                                                   ▼
                                        ┌───────────────────────┐
                                        │  GitHub Issue thread  │
                                        └───────────────────────┘
```

## Features

| Feature | Schedule | Description |
|---|---|---|
| **Daily digest** | 8 AM UTC daily | Horizon (DeepSeek) aggregates HackerNews, Reddit, RSS, NewsAPI → bilingual GitHub Issue + DingTalk card |
| **Story memory** | After each digest | Tracks entities 365 days, annotates follow-ups so you know when a story continues |
| **Weekly arc** | 10 AM UTC Sunday | Narrative of the 3 most interesting story arcs from the past 7 days |
| **Q&A responder** | On comment | Comment a question on any digest issue → bot cites the relevant article and answers; extends beyond the digest with general knowledge |

## Setup

### 1. Fork or clone this repo

```bash
git clone https://github.com/Aurora-yang-git/workflow
```

The `Horizon/` AI framework directory is committed in the repo — no submodule setup needed.

### 2. Set GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Source |
|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | [platform.deepseek.com](https://platform.deepseek.com) |
| `DINGTALK_WEBHOOK` | No | DingTalk group → Add robot → Webhook URL |
| `NEWS_API_KEY` | No | [newsapi.org](https://newsapi.org) (broadens sources) |
| `GITHUB_TOKEN` | Built-in | No action needed |

`DINGTALK_WEBHOOK` is optional — if not set, the workflow logs a warning and skips the card.

### 3. Trigger the first run

Actions → **Daily News Digest** → **Run workflow**

The GitHub Issue appears in your Issues tab within ~5 minutes. The DingTalk card arrives at the same time if the webhook is configured.

## Workflows

### `news-digest.yml` — Daily at 8 AM UTC

1. Horizon fetches and DeepSeek-scores the last 24 hours of news
2. `memory_manager.py` deduplicates, extracts entities, annotates follow-ups
3. `post_issue.py` creates the bilingual GitHub Issue and sends the DingTalk ActionCard
4. `memory_manager.py` commits the updated `memory.json` back to the repo

### `weekly-arc.yml` — Sunday at 10 AM UTC

Reads the past 7 days from `memory.json`, sends all article titles to DeepSeek, and asks it to identify and narrate the 3 most significant story arcs. Posts the result as a GitHub Issue and sends a DingTalk ActionCard. Skips silently if fewer than 5 articles were collected that week.

### `qa-responder.yml` — On issue comment

Triggers when an `OWNER`, `COLLABORATOR`, or `MEMBER` comments on a digest or arc issue. `qa_responder.py`:
- Fetches the full issue body as context
- Asks DeepSeek to identify the relevant article, cite it by title, and answer
- Adds a "🔍 goes beyond today's digest" note for extended questions
- Replies in the same language as the question

Security guards: ignores bot comments (loop guard), PR review comments, and non-member commenters.

## Project structure

```
.github/workflows/
  news-digest.yml       # Daily digest pipeline
  weekly-arc.yml        # Sunday arc narrative
  qa-responder.yml      # Issue comment Q&A

scripts/
  post_issue.py         # Create GitHub Issue + send DingTalk card
  memory_manager.py     # Entity extraction, follow-up annotation, memory commit
  arc_digest.py         # Weekly arc narrative generator
  qa_responder.py       # Context-grounded Q&A responder
  summary_utils.py      # Shared summary file finder
  memory.json           # Rolling 365-day story memory (committed by Actions)

tests/
  test_post_issue.py
  test_memory_manager.py
  test_arc_digest.py
  test_qa_responder.py

Horizon/
  data/config.github.json   # Production config (sources, scoring, languages)
  data/summaries/           # Generated markdown summaries (EN + ZH)
```

## Debugging

**DingTalk card didn't arrive**
1. Check the Actions run log for `DingTalk card sent:` or `::warning::DINGTALK_WEBHOOK`
2. Verify the webhook secret is set and the bot is still in the DingTalk group
3. Trigger manually: Actions → Daily News Digest → Run workflow

**Story threading not showing follow-ups**
- Requires ≥ 2 shared entities between today's story and a past memory entry
- Check the Actions log for `Entity extraction: 0 entities` — the Horizon tag format may have changed
- Memory builds from day 1; threading starts appearing on day 2

**Weekly arc skipped**
- The arc requires at least 5 articles in `memory.json` from the past 7 days
- Check the `weekly-arc.yml` run → "Report skip reason" step for the exact count
- Trigger manually after seeding memory: Actions → Weekly Arc Digest → Run workflow

**Q&A bot not responding**
1. Check the `Digest Q&A Responder` workflow run log
2. Common causes: `DEEPSEEK_API_KEY` expired, comment from a bot, comment on a PR (not an issue), commenter is not OWNER/COLLABORATOR/MEMBER

## Required secrets

```
DEEPSEEK_API_KEY   — AI scoring, arc narrative, and Q&A (required)
DINGTALK_WEBHOOK   — morning card + Sunday arc card (optional)
NEWS_API_KEY       — NewsAPI source (optional, broadens coverage)
GITHUB_TOKEN       — issue creation, Q&A replies, memory commits (built-in)
```
