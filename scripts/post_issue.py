#!/usr/bin/env python3
"""Post today's Horizon summaries (EN + ZH) as a single GitHub Issue."""

import glob
import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Optional

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"].strip()
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"].strip()
SUMMARY_DIR = os.environ.get("SUMMARY_DIR", "Horizon/data/summaries")


def find_summary(lang: str) -> Optional[str]:
    pattern = os.path.join(SUMMARY_DIR, f"horizon-*-{lang}.md")
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def create_issue(title: str, body: str) -> None:
    # GitHub Issues have a 65536-character body limit
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
    print(f"Issue created: {result['html_url']}")


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    en_file = find_summary("en")
    zh_file = find_summary("zh")

    if not en_file and not zh_file:
        raise FileNotFoundError(f"No summary files found in {SUMMARY_DIR}")

    sections = []
    if zh_file:
        print(f"Found ZH: {zh_file}")
        sections.append(read(zh_file))
    if en_file:
        print(f"Found EN: {en_file}")
        # Separate the two language sections with a divider
        if sections:
            sections.append("\n\n---\n\n")
        sections.append(read(en_file))

    body = "".join(sections)
    create_issue(f"每日速递 Daily Digest — {today}", body)


if __name__ == "__main__":
    main()
