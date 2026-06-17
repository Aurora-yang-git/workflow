# TODOS — Deferred from /autoplan review (2026-06-03)

## From CEO Review

- [ ] **Horizon JSON intermediate file** — Export scored items as `horizon-{date}.json` alongside markdown summaries. Lets `memory_manager.py` use `ContentItem.ai_tags` directly instead of parsing markdown, making entity extraction format-change resilient. Medium effort; revisit if entity extraction starts returning empty sets.

- [ ] **News memory topic trends** — After 30+ days of memory entries, surface recurring entities as a weekly "trending topics" digest. Low complexity once memory has data.

## From Eng Review

- [x] **Deduplicate issues on re-trigger** — `find_existing_issue()` added to `post_issue.py`; queries open issues before creating, skips if today's issue already exists.

- [x] **Shared `find_summary` helper** — Extracted to `scripts/summary_utils.py`; both `post_issue.py` and `memory_manager.py` now import from it.

- [x] **Unit tests for new scripts** — 17 tests passing across `test_memory_manager.py` and `test_post_issue.py`, covering `parse_items_from_summary`, `find_followup` (including boundary at threshold=2), and `find_summary` stale-file guard.

## From DX Review

- [ ] **Document Horizon setup in Quick Start** — Add one line: "Ensure the `Horizon/` directory is present (if using as a submodule: `git submodule update --init`)". Blocks first-run success for anyone cloning fresh.

- [x] **`continue-on-error` observability** — Added `Report memory step outcome` step to `news-digest.yml`; on memory failure it emits a `::warning::` annotation and writes to `$GITHUB_STEP_SUMMARY`.

## From Arc Digest Autoplan (2026-06-12)

- [ ] **Bilingual arc output** — Arc narrative is English-only. A second DeepSeek call with a translation prompt would produce a ZH version for Chinese-first readers. Deferred: requires second API call per week (~$0.0003 extra); revisit when EN arc quality is validated over 4+ weeks.

- [ ] **`memory.json` entry count in arc issue body** — Add a footer line to the Weekly Arc GitHub Issue: "Based on N articles from {week_start} to {week_end}." Makes arc scope transparent to readers without opening the Actions log.

- [ ] **`actions/checkout@v6` in news-digest.yml** — The daily workflow uses `actions/checkout@v6` which does not exist in the GitHub Actions marketplace (latest stable is `@v4`). Fix: change `news-digest.yml` line 21 from `@v6` to `@v4`. Low risk, no behavior change.

- [ ] **Arc quality feedback loop** — When the minimum-items guard fires 3+ consecutive weeks, emit a `::warning::` annotation suggesting the Horizon pipeline may have failed. Currently silent degradation.

## From Q&A Context Grounding Autoplan (2026-06-14)

- [ ] **Multi-issue Q&A memory** — Answer questions using context from this week's AND past digest issues. Requires fetching multiple issue bodies or reading `memory.json`. Deferred: current single-digest approach covers 95% of questions.

- [ ] **DingTalk Q&A reply** — Support Q&A via DingTalk (not just GitHub Issue comments). Requires a DingTalk webhook inbound listener. Significant infra change; defer until DingTalk engagement warrants it.

- [x] **Weekly Arc Q&A** — Extend Q&A responder to answer questions on `Weekly Arc` issues too. Implement arc-aware context: parse date range from title, load matching entries from memory.json, run same identify+fetch pipeline as daily Q&A. Shipped 2026-06-17; 37 tests passing.

- [ ] **Per-article URL citation** — Include the source article URL in Q&A replies. Requires storing URLs in the issue body (currently not present in structured form). Revisit when digest format includes per-article links.

- [x] **`actions/checkout@v6` in qa-responder.yml** — Fixed to `@v4` atomically with arc Q&A feature (2026-06-17).
