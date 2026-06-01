#!/usr/bin/env python3
"""Fetch a daily news digest and email it."""

import os
import smtplib
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", GMAIL_USER)

TOPICS = [
    {"label": "Tech & AI",        "q": "artificial intelligence OR technology OR software", "category": "technology"},
    {"label": "Science",          "q": "science OR space OR research",                      "category": "science"},
    {"label": "World & Politics", "q": "world news OR politics OR international",           "category": "general"},
]

MAX_ARTICLES = 5


def fetch_top_headlines(category: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "category": category,
        "language": "en",
        "pageSize": MAX_ARTICLES,
        "apiKey": NEWS_API_KEY,
    })
    url = f"https://newsapi.org/v2/top-headlines?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("articles", [])


def fetch_everything(q: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": q,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": MAX_ARTICLES,
        "apiKey": NEWS_API_KEY,
    })
    url = f"https://newsapi.org/v2/everything?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("articles", [])


def articles_html(articles: list[dict]) -> str:
    if not articles:
        return "<p><em>No articles found.</em></p>"
    items = []
    for a in articles:
        title = a.get("title") or "Untitled"
        url = a.get("url", "#")
        source = (a.get("source") or {}).get("name", "")
        description = a.get("description") or ""
        items.append(
            f'<li style="margin-bottom:12px">'
            f'<a href="{url}" style="font-weight:bold;color:#1a73e8;text-decoration:none">{title}</a>'
            f'{"  <span style=\"color:#888;font-size:13px\">— " + source + "</span>" if source else ""}'
            f'{"<br><span style=\"color:#555;font-size:13px\">" + description + "</span>" if description else ""}'
            f"</li>"
        )
    return "<ul style='padding-left:18px'>" + "".join(items) + "</ul>"


def build_html(sections: list[tuple[str, list[dict]]]) -> str:
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    section_html = ""
    for label, articles in sections:
        section_html += (
            f'<h2 style="border-bottom:2px solid #1a73e8;padding-bottom:4px;color:#202124">{label}</h2>'
            + articles_html(articles)
        )
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#202124">
  <h1 style="color:#1a73e8">Your Daily News Digest</h1>
  <p style="color:#888;margin-top:-12px">{today}</p>
  {section_html}
  <hr style="margin-top:32px;border:none;border-top:1px solid #e0e0e0">
  <p style="color:#aaa;font-size:12px">Powered by NewsAPI · Delivered by GitHub Actions</p>
</body>
</html>"""


def send_email(subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())


def main() -> None:
    sections = []
    for topic in TOPICS:
        try:
            articles = fetch_top_headlines(topic["category"])
            if not articles:
                articles = fetch_everything(topic["q"])
        except Exception as exc:
            print(f"Warning: failed to fetch '{topic['label']}': {exc}")
            articles = []
        sections.append((topic["label"], articles))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = build_html(sections)
    send_email(f"Daily News Digest — {today}", html)
    print(f"Digest sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
