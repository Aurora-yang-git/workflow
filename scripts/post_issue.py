#!/usr/bin/env python3
"""Post today's Horizon summaries (EN + ZH) as a single GitHub Issue, then send DingTalk card."""

import glob
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"].strip()
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"].strip()
SUMMARY_DIR = os.environ.get("SUMMARY_DIR", "Horizon/data/summaries")
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "").strip()


def find_summary(lang: str, today: str) -> Optional[str]:
    pattern = os.path.join(SUMMARY_DIR, f"horizon-{today}-{lang}.md")
    files = glob.glob(pattern)
    return files[0] if files else None


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def create_issue(title: str, body: str) -> str:
    """Create a GitHub Issue and return its html_url."""
    if len(body) > 65000:
        body = body[:65000] + "\n\n*(truncated)*"
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues"
    payload = json.dumps({"title": title, "body": body}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    issue_url = result["html_url"]
    print(f"Issue created: {issue_url}")
    return issue_url


def send_dingtalk(issue_url: str, card_text: str, today: str) -> None:
    if not DINGTALK_WEBHOOK:
        print("Warning: DINGTALK_WEBHOOK not set — skipping DingTalk delivery")
        print("::warning::DINGTALK_WEBHOOK secret not configured — no DingTalk card was sent today")
        return
    payload = json.dumps({
        "msgtype": "actionCard",
        "actionCard": {
            "title": f"每日速递 Daily Digest — {today}",
            "text": card_text[:3000],
            "btnOrientation": "0",
            "btns": [{"title": "查看完整摘要 Read Full Digest", "actionURL": issue_url}],
        },
    }).encode()
    req = urllib.request.Request(
        DINGTALK_WEBHOOK, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DingTalk HTTP error {e.code}: {e.read().decode()[:200]}")
    if result.get("errcode", 0) != 0:
        raise RuntimeError(f"DingTalk error: {result}")
    print(f"DingTalk card sent: {result}")


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    en_file = find_summary("en", today)
    zh_file = find_summary("zh", today)

    if not en_file and not zh_file:
        raise FileNotFoundError(f"No summary files found in {SUMMARY_DIR}")

    sections = []
    if zh_file:
        print(f"Found ZH: {zh_file}")
        sections.append(read(zh_file))
    if en_file:
        print(f"Found EN: {en_file}")
        if sections:
            sections.append("\n\n---\n\n")
        sections.append(read(en_file))

    body = "".join(sections)
    issue_url = create_issue(f"每日速递 Daily Digest — {today}", body)

    # Write issue URL to file so memory_manager can pick it up
    with open("issue_url.txt", "w") as f:
        f.write(issue_url)

    card_content = read(zh_file) if zh_file else read(en_file)
    send_dingtalk(issue_url, card_content, today)


if __name__ == "__main__":
    main()
