#!/usr/bin/env python3
# stdlib only — do not add third-party imports (uv sync installs nothing at repo root)
"""Weekly Story Arc Digest — reads memory.json, calls DeepSeek, posts GitHub Issue + DingTalk."""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MIN_ITEMS = 5


def load_week_entries(week_start: str, week_end: str) -> list:
    """Load memory.json and return entries within [week_start, week_end] inclusive."""
    if not os.path.exists(MEMORY_PATH):
        return []
    try:
        with open(MEMORY_PATH, encoding="utf-8") as f:
            memory = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse {MEMORY_PATH}: {e}") from e
    return [
        e for e in memory
        if e.get("date", "") >= week_start and e.get("date", "") <= week_end
    ]


def build_arc_prompt(entries: list) -> str:
    """Build DeepSeek prompt from memory entries sorted by date."""
    sorted_entries = sorted(entries, key=lambda e: e.get("date", ""))
    lines = "\n".join(
        f"{e.get('date', '(no date)')}: {e.get('title', '(no title)')}"
        for e in sorted_entries
    )
    return (
        "You are a news analyst. Here are news articles from this week's daily digest.\n"
        "Identify the 3 most interesting story arcs — groups of 2+ articles covering the same developing story.\n"
        "For each arc, write a narrative: how the story opened, what shifted, and where it stands now (3–5 sentences).\n"
        "If fewer than 3 distinct arcs exist in the data, return only the arcs that do exist — do not fabricate.\n\n"
        "Format your response as:\n"
        "## [Arc title]\n"
        "[3–5 sentence narrative]\n\n"
        "(repeat for each arc)\n\n"
        f"Articles:\n{lines}"
    )


def call_deepseek(prompt: str) -> str:
    """Call DeepSeek API and return arc narrative text."""
    api_key = os.environ["DEEPSEEK_API_KEY"]
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"DeepSeek returned empty choices: {result}")
    arc_text = choices[0]["message"]["content"]
    if not arc_text.strip():
        raise RuntimeError("DeepSeek returned empty arc text")
    return arc_text


def send_arc_dingtalk(issue_url: str, arc_text: str, run_date: str) -> None:
    """Send Weekly Arc DingTalk ActionCard. DINGTALK_WEBHOOK is optional."""
    webhook = os.environ.get("DINGTALK_WEBHOOK", "").strip()
    if not webhook:
        print("Warning: DINGTALK_WEBHOOK not set — skipping DingTalk delivery")
        print("::warning::DINGTALK_WEBHOOK secret not configured — no DingTalk arc card was sent")
        return
    payload = json.dumps({
        "msgtype": "actionCard",
        "actionCard": {
            "title": f"Weekly Arc — {run_date}",
            "text": arc_text[:3000],
            "btnOrientation": "0",
            "btns": [{"title": "Read Full Arc", "actionURL": issue_url}],
        },
    }).encode()
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DingTalk HTTP error {e.code}: {e.read().decode()[:200]}")
    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"DingTalk error: {result}")
    print(f"DingTalk arc card sent: {result}")


def main() -> None:
    # Lazy import: post_issue.py reads GITHUB_TOKEN at module level, so import
    # only when actually running (not during test collection of other test files).
    from post_issue import create_issue  # noqa: PLC0415

    run_date = datetime.now(timezone.utc).date()
    week_end = run_date
    week_start = run_date - timedelta(days=6)
    week_start_str = week_start.isoformat()
    week_end_str = week_end.isoformat()
    run_date_str = run_date.isoformat()

    entries = load_week_entries(week_start_str, week_end_str)
    print(f"Arc digest: {len(entries)} entries from {week_start_str} to {week_end_str}")

    if len(entries) < MIN_ITEMS:
        skip_reason = f"only {len(entries)} entries found this week (minimum: {MIN_ITEMS})"
        print(skip_reason)
        github_output = os.environ.get("GITHUB_OUTPUT", "")
        if github_output:
            with open(github_output, "a") as f:
                f.write("skipped=true\n")
                f.write(f"skip_reason<<EOF\n{skip_reason}\nEOF\n")
        github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if github_step_summary:
            with open(github_step_summary, "a") as f:
                f.write(f"## Arc Digest Skipped\n\n{skip_reason}\n")
        return

    prompt = build_arc_prompt(entries)
    print(f"Prompt: {len(prompt)} chars, {len(entries)} entries")

    arc_text = call_deepseek(prompt)

    issue_title = f"Weekly Arc — {week_start_str} to {week_end_str}"
    issue_url = create_issue(issue_title, arc_text)

    github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if github_step_summary:
        with open(github_step_summary, "a") as f:
            f.write(f"## Arc Digest Complete\n\n[View Issue]({issue_url})\n")

    send_arc_dingtalk(issue_url, arc_text, run_date_str)


if __name__ == "__main__":
    if os.environ.get("DRY_RUN") == "1":
        run_date = datetime.now(timezone.utc).date()
        week_end = run_date
        week_start = run_date - timedelta(days=6)
        entries = load_week_entries(week_start.isoformat(), week_end.isoformat())
        print(f"[DRY_RUN] {len(entries)} entries from {week_start} to {week_end}")
        if len(entries) < MIN_ITEMS:
            print(f"[DRY_RUN] Guard fires: {len(entries)} < {MIN_ITEMS}")
            sys.exit(0)
        prompt = build_arc_prompt(entries)
        print(f"[DRY_RUN] Prompt ({len(prompt)} chars):\n{prompt}")
    else:
        main()
