"""Tests for summary_utils.find_summary and memory_manager dedup."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from summary_utils import find_summary
from memory_manager import dedup_summary, get_recent_urls


def test_find_summary_returns_todays_file(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / f"horizon-{today}-en.md").write_text("today's content")
    (tmp_path / "horizon-2026-06-01-en.md").write_text("stale content")

    result = find_summary(str(tmp_path), "en", today)
    assert result is not None
    assert today in result


def test_find_summary_ignores_stale_file(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / "horizon-2026-06-01-en.md").write_text("yesterday")

    result = find_summary(str(tmp_path), "en", today)
    assert result is None


def test_find_summary_returns_none_when_empty_dir(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = find_summary(str(tmp_path), "en", today)
    assert result is None


def test_find_summary_lang_filter(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / f"horizon-{today}-en.md").write_text("en")
    (tmp_path / f"horizon-{today}-zh.md").write_text("zh")

    en = find_summary(str(tmp_path), "en", today)
    zh = find_summary(str(tmp_path), "zh", today)

    assert en is not None and "en" in en
    assert zh is not None and "zh" in zh


_SUMMARY_TEMPLATE = """\
# Horizon Daily - 2026-06-03

> From 15 items, 2 important content pieces were selected

---

1. [Article One](#item-1) ⭐️ 8.0/10
2. [Article Two](#item-2) ⭐️ 7.0/10

---

<a id="item-1"></a>
## [Article One](https://example.com/one) ⭐️ 8.0/10

Body one.

**Tags**: `#AI`

---

<a id="item-2"></a>
## [Article Two](https://example.com/two) ⭐️ 7.0/10

Body two.

**Tags**: `#Science`

---
"""


def test_dedup_removes_seen_url():
    seen = {"https://example.com/one"}
    filtered, removed = dedup_summary(_SUMMARY_TEMPLATE, seen, lang="en")
    assert removed == 1
    assert "Article One" not in filtered
    assert "Article Two" in filtered
    assert "1. [Article Two]" in filtered


def test_dedup_no_op_when_nothing_seen():
    filtered, removed = dedup_summary(_SUMMARY_TEMPLATE, set(), lang="en")
    assert removed == 0
    assert filtered == _SUMMARY_TEMPLATE


def test_dedup_removes_both_articles():
    seen = {"https://example.com/one", "https://example.com/two"}
    filtered, removed = dedup_summary(_SUMMARY_TEMPLATE, seen, lang="en")
    assert removed == 2
    assert "Article One" not in filtered
    assert "Article Two" not in filtered


def test_get_recent_urls_filters_by_date():
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    recent_date = (today - timedelta(days=1)).isoformat()
    memory = [
        {"url": "https://old.com", "date": "2026-01-01"},
        {"url": "https://recent.com", "date": recent_date},
    ]
    recent = get_recent_urls(memory, days=3)
    assert "https://recent.com" in recent
    assert "https://old.com" not in recent
