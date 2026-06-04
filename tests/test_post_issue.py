"""Tests for scripts/post_issue.py — find_summary stale-file guard."""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

# Set required env vars before importing post_issue
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_REPOSITORY", "test/repo")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import post_issue


def test_find_summary_returns_todays_file(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / f"horizon-{today}-en.md").write_text("today's content")
    (tmp_path / "horizon-2026-06-01-en.md").write_text("stale content")

    with patch.object(post_issue, "SUMMARY_DIR", str(tmp_path)):
        result = post_issue.find_summary("en", today)

    assert result is not None
    assert today in result


def test_find_summary_ignores_stale_file(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / "horizon-2026-06-01-en.md").write_text("yesterday")

    with patch.object(post_issue, "SUMMARY_DIR", str(tmp_path)):
        result = post_issue.find_summary("en", today)

    assert result is None


def test_find_summary_returns_none_when_empty_dir(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with patch.object(post_issue, "SUMMARY_DIR", str(tmp_path)):
        result = post_issue.find_summary("en", today)
    assert result is None


def test_find_summary_lang_filter(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (tmp_path / f"horizon-{today}-en.md").write_text("en")
    (tmp_path / f"horizon-{today}-zh.md").write_text("zh")

    with patch.object(post_issue, "SUMMARY_DIR", str(tmp_path)):
        en = post_issue.find_summary("en", today)
        zh = post_issue.find_summary("zh", today)

    assert en is not None and "en" in en
    assert zh is not None and "zh" in zh
