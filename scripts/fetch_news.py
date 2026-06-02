#!/usr/bin/env python3
"""Fetch a daily news digest and post it as a GitHub Issue."""

import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone

NEWS_API_KEY = os.environ["NEWS_API_KEY"].strip()
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"].strip()
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"].strip()  # owner/repo

TOPICS = [
    {"label": "Tech & AI",        "category": "technology"},
    {"label": "Science",          "category": "science"},
    {"label": "World & Politics", "category": "general"},
]

MAX_ARTICLES = 5


def fetch(category: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "category": category,
        "language": "en",
        "pageSize": MAX_ARTICLES,
        "apiKey": NEWS_API_KEY,
    })
    url = f"https://newsapi.org/v2/top-headlines?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read()).get("articles", [])


def articles_md(articles: list[dict]) -> str:
    if not articles:
        return "_No articles found._\n"
    lines = []
    for a in articles:
        title = a.get("title") or "Untitled"
        url = a.get("url", "")
        source = (a.get("source") or {}).get("name", "")
        description = a.get("description") or ""
        line = f"- [{title}]({url})"
        if source:
            line += f" — *{source}*"
        if description:
            line += f"\n  {description}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def build_body(sections: list[tuple[str, list[dict]]]) -> str:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    body = f"# Daily News Digest — {today}\n\n"
    for label, articles in sections:
        body += f"## {label}\n\n{articles_md(articles)}\n"
    body += "\n---\n*Powered by NewsAPI · Delivered by GitHub Actions*"
    return body


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
    sections = []
    for topic in TOPICS:
        try:
            articles = fetch(topic["category"])
        except Exception as exc:
            print(f"Warning: failed to fetch '{topic['label']}': {exc}")
            articles = []
        sections.append((topic["label"], articles))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = build_body(sections)
    create_issue(f"Daily News Digest — {today}", body)


if __name__ == "__main__":
    main()
