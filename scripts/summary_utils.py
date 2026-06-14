"""Shared utilities for locating Horizon summary files."""

import glob
import os


def find_summary(summary_dir: str, lang: str, today: str) -> str | None:
    """Return path to today's summary for the given language, or None."""
    pattern = os.path.join(summary_dir, f"horizon-{today}-{lang}.md")
    files = glob.glob(pattern)
    return files[0] if files else None
