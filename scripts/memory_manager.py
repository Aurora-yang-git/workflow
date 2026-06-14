#!/usr/bin/env python3
"""Read/write news memory.json — annotates follow-up items across digest runs."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

from summary_utils import find_summary as _find_summary

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")
RETENTION_DAYS = 365
OVERLAP_THRESHOLD = 2  # shared entities to qualify as a follow-up
DEDUP_DAYS = 3  # suppress articles already posted within this many days


def load_memory() -> list:
    if not os.path.exists(MEMORY_PATH):
        return []
    with open(MEMORY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_memory(entries: list) -> None:
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def prune(entries: list) -> list:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).date().isoformat()
    return [e for e in entries if e.get("date", "") >= cutoff]


def parse_tags(line: str) -> list[str]:
    """Extract tags from a markdown tags line like: **Tags**: `#AI`, `#LLM`"""
    return [t.lstrip("#").lower() for t in re.findall(r"`#([^`]+)`", line)]


def parse_items_from_summary(md: str) -> list[dict]:
    """Parse title, url, tags from an EN summary markdown."""
    items = []
    # Each item starts with ## [title](url) ⭐️ score
    heading_re = re.compile(r"^## \[(.+?)\]\((.+?)\)", re.MULTILINE)
    tag_re = re.compile(r"\*\*Tags\*\*:(.+)")
    sections = heading_re.split(md)
    # sections: [pre, title1, url1, body1, title2, url2, body2, ...]
    i = 1
    while i + 2 < len(sections):
        title = sections[i]
        url = sections[i + 1]
        body = sections[i + 2]
        tags = []
        m = tag_re.search(body)
        if m:
            tags = parse_tags(m.group(0))
        items.append({"title": title, "url": url, "entities": tags})
        i += 3
    return items


def find_followup(item: dict, memory: list) -> dict | None:
    """Return the most-recent memory entry with OVERLAP_THRESHOLD shared entities."""
    item_entities = set(item.get("entities", []))
    best = None
    best_date = ""
    for entry in memory:
        mem_entities = set(entry.get("entities", []))
        if len(item_entities & mem_entities) >= OVERLAP_THRESHOLD:
            if entry.get("date", "") > best_date:
                best = entry
                best_date = entry["date"]
    return best


def get_recent_urls(memory: list, days: int) -> set[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    return {e["url"] for e in memory if e.get("date", "") >= cutoff}


def dedup_summary(md: str, seen_urls: set[str], lang: str = "en") -> tuple[str, int]:
    """Remove already-seen articles from a summary. Returns (filtered_md, removed_count)."""
    SEP = "\n---\n"
    parts = md.split(SEP)
    # Expect: header | toc | item... | trailing
    if len(parts) < 3:
        return md, 0

    header = parts[0]
    toc = parts[1]
    item_sections = parts[2:-1]
    trailing = parts[-1]

    url_re = re.compile(r"^## \[.+?\]\((.+?)\)", re.MULTILINE)
    anchor_re = re.compile(r'<a id="(item-\d+)">')

    kept_sections = []
    removed_anchors: set[str] = set()

    for section in item_sections:
        url_m = url_re.search(section)
        if url_m and url_m.group(1) in seen_urls:
            a_m = anchor_re.search(section)
            if a_m:
                removed_anchors.add(a_m.group(1))
        else:
            kept_sections.append(section)

    removed_count = len(item_sections) - len(kept_sections)
    if removed_count == 0:
        return md, 0

    # Filter and renumber TOC entries
    toc_lines = toc.split("\n")
    new_toc_lines = []
    counter = 1
    for line in toc_lines:
        a_m = re.search(r"\(#(item-\d+)\)", line)
        if a_m and a_m.group(1) in removed_anchors:
            continue
        if re.match(r"^\d+\.", line):
            line = re.sub(r"^\d+\.", f"{counter}.", line)
            counter += 1
        new_toc_lines.append(line)
    new_toc = "\n".join(new_toc_lines)

    kept_count = len(kept_sections)
    if lang == "zh":
        header = re.sub(r"筛选出 \d+ 条重要资讯", f"筛选出 {kept_count} 条重要资讯", header)
    else:
        header = re.sub(
            r"\d+ important content pieces were selected",
            f"{kept_count} important content pieces were selected",
            header,
        )

    return SEP.join([header, new_toc] + kept_sections + [trailing]), removed_count


def dedup_summaries(summary_dir: str, today: str, memory: list) -> int:
    """Filter out recently-seen URLs from today's summaries. Returns total removed count."""
    seen_urls = get_recent_urls(memory, DEDUP_DAYS)
    if not seen_urls:
        return 0

    total_removed = 0
    for lang in ("en", "zh"):
        path = _find_summary(summary_dir, lang, today)
        if not path:
            continue
        with open(path, encoding="utf-8") as f:
            md = f.read()
        filtered, removed = dedup_summary(md, seen_urls, lang)
        if removed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(filtered)
            print(f"Deduplication ({lang}): removed {removed} already-seen article(s)")
            total_removed += removed
    return total_removed


def annotate_summary(md: str, memory: list, today: str, issue_url: str) -> tuple[str, list]:
    """Annotate follow-up items in the markdown and return (annotated_md, new_entries)."""
    items = parse_items_from_summary(md)
    new_entries = []
    for item in items:
        prior = find_followup(item, memory)
        if prior:
            # Insert follow-up annotation right after the heading line
            heading = f"## [{item['title']}]({item['url']})"
            annotation = f"\n> 📌 Follow-up to **{prior['title']}** ({prior['date']})\n"
            md = md.replace(heading, heading + annotation, 1)
        new_entries.append({
            "title": item["title"],
            "url": item["url"],
            "entities": item["entities"],
            "date": today,
            "issue_url": issue_url,
        })
    return md, new_entries


def commit_memory() -> None:
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        check=True, cwd=os.path.dirname(os.path.dirname(MEMORY_PATH))
    )
    subprocess.run(
        ["git", "config", "user.name", "github-actions[bot]"],
        check=True, cwd=os.path.dirname(os.path.dirname(MEMORY_PATH))
    )
    repo_root = os.path.dirname(os.path.dirname(MEMORY_PATH))
    subprocess.run(["git", "pull", "--rebase"], check=True, cwd=repo_root)
    subprocess.run(["git", "add", "scripts/memory.json"], check=True, cwd=repo_root)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_root
    )
    if result.returncode == 0:
        print("memory.json unchanged — nothing to commit")
        return
    subprocess.run(
        ["git", "commit", "-m", "chore: update news memory [skip ci]"],
        check=True, cwd=repo_root
    )
    subprocess.run(["git", "push"], check=True, cwd=repo_root)
    print("memory.json committed and pushed")


def dedup_main() -> None:
    """Entry point for --dedup mode: filter summaries before posting."""
    summary_dir = os.environ.get("SUMMARY_DIR", "Horizon/data/summaries")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    memory = load_memory()
    removed = dedup_summaries(summary_dir, today, memory)
    if removed == 0:
        print("Deduplication: no already-seen articles found")
    else:
        print(f"Deduplication: removed {removed} article(s) total across EN/ZH summaries")


def main() -> None:
    summary_dir = os.environ.get("SUMMARY_DIR", "Horizon/data/summaries")
    issue_url = os.environ.get("ISSUE_URL", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Find today's EN summary (tags are in EN)
    en_path = _find_summary(summary_dir, "en", today)
    if not en_path:
        print(f"No EN summary for {today} found in {summary_dir} — skipping memory update")
        sys.exit(0)

    if not issue_url:
        print("WARNING: ISSUE_URL is empty — post_issue.py may have failed; memory entries will have no issue link")
        print("::warning::ISSUE_URL empty — memory.json entries will lack issue link this run")
    with open(en_path, encoding="utf-8") as f:
        en_md = f.read()

    memory = load_memory()
    items_parsed = parse_items_from_summary(en_md)
    entity_counts = [len(i["entities"]) for i in items_parsed]
    total_entities = sum(entity_counts)
    if total_entities == 0 and items_parsed:
        print(f"WARNING: 0 entities extracted from {len(items_parsed)} items — check Horizon tag format")
    else:
        print(f"Entity extraction: {total_entities} entities across {len(items_parsed)} items ({entity_counts})")
    annotated_md, new_entries = annotate_summary(en_md, memory, today, issue_url)

    # Write annotated EN summary back
    with open(en_path, "w", encoding="utf-8") as f:
        f.write(annotated_md)
    followup_count = annotated_md.count("📌 Follow-up to")
    if followup_count > 0:
        print(f"Annotated {followup_count} follow-up(s) in EN summary")

    # Also annotate ZH summary using the same item order
    zh_path = _find_summary(summary_dir, "zh", today)
    if zh_path:
        with open(zh_path, encoding="utf-8") as f:
            zh_md = f.read()
        for item in items_parsed:
            prior = find_followup(item, memory)
            if not prior:
                continue
            # find the ZH heading by URL (same URL, different title)
            url = item["url"]
            zh_heading_m = re.search(
                r"^## \[([^\]]+)\]\(" + re.escape(url) + r"\)",
                zh_md, re.MULTILINE
            )
            if zh_heading_m:
                old_heading = zh_heading_m.group(0)
                annotation = f"\n> 📌 关联新闻：**{prior['title']}** ({prior['date']})\n"
                zh_md = zh_md.replace(old_heading, old_heading + annotation, 1)
        with open(zh_path, "w", encoding="utf-8") as f:
            f.write(zh_md)

    # Update memory
    memory = prune(memory + new_entries)
    save_memory(memory)
    print(f"News memory: {len(memory)} entries saved (up to {RETENTION_DAYS} days)")

    commit_memory()


if __name__ == "__main__":
    if "--dedup" in sys.argv:
        dedup_main()
    else:
        main()
