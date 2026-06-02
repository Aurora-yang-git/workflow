#!/usr/bin/env python3
"""Post the latest Horizon summary as a GitHub Issue."""

import glob
import json
import os
import urllib.request
from datetime import datetime, timezone

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"].strip()
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"].strip()
SUMMARY_DIR = os.environ.get("SUMMARY_DIR", "Horizon/data/summaries")


def find_latest_summary() -> str:
    pattern = os.path.join(SUMMARY_DIR, "horizon-*-en.md")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        raise FileNotFoundError(f"No summary files found in {SUMMARY_DIR}")
    return files[0]


def create_issue(title: str, body: str) -> None:
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
    summary_file = find_latest_summary()
    print(f"Posting: {summary_file}")

    with open(summary_file, encoding="utf-8") as f:
        body = f.read()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    create_issue(f"Daily News Digest — {today}", body)


if __name__ == "__main__":
    main()
