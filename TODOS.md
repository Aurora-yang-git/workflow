# TODOS — Deferred from /autoplan review (2026-06-03)

## From CEO Review

- [ ] **Horizon JSON intermediate file** — Export scored items as `horizon-{date}.json` alongside markdown summaries. Lets `memory_manager.py` use `ContentItem.ai_tags` directly instead of parsing markdown, making entity extraction format-change resilient. Medium effort; revisit if entity extraction starts returning empty sets.

- [ ] **News memory topic trends** — After 30+ days of memory entries, surface recurring entities as a weekly "trending topics" digest. Low complexity once memory has data.

## From Eng Review

- [ ] **Deduplicate issues on re-trigger** — Before `create_issue`, query open issues for title prefix `"每日速递 Daily Digest — {today}"`. Skip creation if one exists. Requires one GitHub API GET before the POST. Low complexity, low urgency (manual re-triggers are rare).

- [ ] **Shared `find_summary` helper** — Unify the date-based summary discovery pattern between `post_issue.py` and `memory_manager.py` into a small shared utility. Currently two separate patterns; alignment matters if Horizon filename format changes.

- [ ] **Unit tests for new scripts** — Critical missing coverage:
  - `parse_items_from_summary` against real Horizon markdown output (regex against actual format)
  - `find_followup` with Jaccard overlap at threshold = 2 (exact boundary test)
  - `find_summary` when stale prior-day files exist
  - `commit_memory` concurrent run / non-fast-forward path (can mock `subprocess`)

## From DX Review

- [ ] **Document Horizon setup in Quick Start** — Add one line: "Ensure the `Horizon/` directory is present (if using as a submodule: `git submodule update --init`)". Blocks first-run success for anyone cloning fresh.

- [ ] **`continue-on-error` observability** — The memory step fails silently with a yellow warning icon. Consider a follow-up step that checks `steps.memory.outcome` and posts a GitHub step summary annotation if the memory step failed, so failures don't compound across days unnoticed.
