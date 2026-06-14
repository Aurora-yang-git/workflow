"""Tests for arc_digest.py — all tests run without network access (all HTTP mocked)."""
import json
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import arc_digest
from arc_digest import (
    MIN_ITEMS,
    build_arc_prompt,
    call_deepseek,
    load_week_entries,
    send_arc_dingtalk,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_ENTRIES = [
    {"date": "2026-06-06", "title": "OpenAI announces GPT-5", "url": "https://a.com/1"},
    {"date": "2026-06-07", "title": "Developers frustrated by GPT-5 pricing", "url": "https://a.com/2"},
    {"date": "2026-06-08", "title": "GPT-5 adoption exceeds expectations", "url": "https://a.com/3"},
    {"date": "2026-06-09", "title": "EU regulators scrutinize GPT-5 rollout", "url": "https://a.com/4"},
    {"date": "2026-06-10", "title": "OpenAI cuts GPT-5 price following backlash", "url": "https://a.com/5"},
    {"date": "2026-06-06", "title": "China restricts foreign AI models", "url": "https://b.com/1"},
    {"date": "2026-06-08", "title": "ByteDance launches domestic GPT-5 rival", "url": "https://b.com/2"},
    {"date": "2026-06-09", "title": "Alibaba follows with cloud AI push", "url": "https://b.com/3"},
    {"date": "2026-06-07", "title": "Climate summit opens in Geneva", "url": "https://c.com/1"},
    {"date": "2026-06-10", "title": "Summit concludes with emissions pledge", "url": "https://c.com/2"},
]


def _deepseek_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": text}}]
    }).encode()
    return resp


# ---------------------------------------------------------------------------
# 1. Prompt assembly — all titles and dates present, sorted oldest-first
# ---------------------------------------------------------------------------

def test_build_arc_prompt_includes_all_titles():
    prompt = build_arc_prompt(FAKE_ENTRIES)
    for entry in FAKE_ENTRIES:
        assert entry["title"] in prompt
        assert entry["date"] in prompt


def test_build_arc_prompt_sorted_by_date():
    prompt = build_arc_prompt(FAKE_ENTRIES)
    lines_block = prompt.split("Articles:\n", 1)[1]
    dates = [line.split(":")[0] for line in lines_block.strip().splitlines()]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# 2. Below-threshold guard — exits 0, does NOT call DeepSeek
# ---------------------------------------------------------------------------

def test_guard_below_threshold_skips_deepseek(tmp_path, monkeypatch):
    memory_file = tmp_path / "memory.json"
    entries = FAKE_ENTRIES[:3]  # only 3 entries < MIN_ITEMS
    memory_file.write_text(json.dumps(entries))
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        with patch("post_issue.create_issue") as mock_create:
            arc_digest.main()

    mock_urlopen.assert_not_called()
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# 3 & 4. At-threshold — DeepSeek called, create_issue called with arc text
# ---------------------------------------------------------------------------

def test_at_threshold_calls_deepseek_and_create_issue(tmp_path, monkeypatch):
    memory_file = tmp_path / "memory.json"
    memory_file.write_text(json.dumps(FAKE_ENTRIES))
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    monkeypatch.delenv("DINGTALK_WEBHOOK", raising=False)

    arc_body = "## GPT-5 Price War\nNarrative text here."
    with patch("urllib.request.urlopen", return_value=_deepseek_response(arc_body)):
        with patch("post_issue.create_issue", return_value="https://github.com/issues/42") as mock_create:
            arc_digest.main()

    mock_create.assert_called_once()
    call_title, call_body = mock_create.call_args[0]
    assert "Weekly Arc" in call_title
    assert "## GPT-5 Price War" in call_body


# ---------------------------------------------------------------------------
# 5. Empty memory.json → guard fires
# ---------------------------------------------------------------------------

def test_empty_memory_triggers_guard(tmp_path, monkeypatch):
    memory_file = tmp_path / "memory.json"
    memory_file.write_text("[]")
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        arc_digest.main()

    mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Entry missing 'title' key → "(no title)" in prompt, no KeyError
# ---------------------------------------------------------------------------

def test_missing_title_key_uses_fallback():
    entries = [{"date": "2026-06-10", "url": "https://example.com"}]
    prompt = build_arc_prompt(entries)
    assert "(no title)" in prompt


# ---------------------------------------------------------------------------
# 7. Guard fires → GITHUB_OUTPUT file contains correct keys
# ---------------------------------------------------------------------------

def test_guard_writes_github_output(tmp_path, monkeypatch):
    memory_file = tmp_path / "memory.json"
    memory_file.write_text(json.dumps(FAKE_ENTRIES[:2]))
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")

    output_file = tmp_path / "github_output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    arc_digest.main()

    content = output_file.read_text()
    assert "skipped=true" in content
    assert "skip_reason<<EOF" in content
    assert "only 2 entries" in content


# ---------------------------------------------------------------------------
# 8. URLError propagates — job fails loudly
# ---------------------------------------------------------------------------

def test_urlerror_propagates(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        with pytest.raises(urllib.error.URLError):
            call_deepseek("some prompt")


# ---------------------------------------------------------------------------
# 9. Empty choices → RuntimeError, create_issue NOT called
# ---------------------------------------------------------------------------

def test_empty_choices_raises(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    empty_resp = MagicMock()
    empty_resp.__enter__ = lambda s: s
    empty_resp.__exit__ = MagicMock(return_value=False)
    empty_resp.read.return_value = json.dumps({"choices": []}).encode()

    with patch("urllib.request.urlopen", return_value=empty_resp):
        with pytest.raises(RuntimeError, match="empty choices"):
            call_deepseek("some prompt")


# ---------------------------------------------------------------------------
# 10. Empty response text → RuntimeError before create_issue
# ---------------------------------------------------------------------------

def test_empty_response_text_raises(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    blank_resp = _deepseek_response("   ")

    with patch("urllib.request.urlopen", return_value=blank_resp):
        with pytest.raises(RuntimeError, match="empty arc text"):
            call_deepseek("some prompt")


# ---------------------------------------------------------------------------
# 11. Import smoke — arc_digest imports without exception (no env needed
#     because post_issue is imported lazily inside main())
# ---------------------------------------------------------------------------

def test_import_smoke():
    import importlib
    importlib.reload(arc_digest)


# ---------------------------------------------------------------------------
# 12. DINGTALK_WEBHOOK absent → DingTalk skipped, no exception, no HTTP call
# ---------------------------------------------------------------------------

def test_dingtalk_absent_skips_without_error(monkeypatch):
    monkeypatch.delenv("DINGTALK_WEBHOOK", raising=False)
    with patch("urllib.request.urlopen") as mock_urlopen:
        send_arc_dingtalk("https://github.com/issues/1", "arc text", "2026-06-15")
    mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# 13. json.JSONDecodeError → RuntimeError with MEMORY_PATH in message
# ---------------------------------------------------------------------------

def test_json_decode_error_includes_path(tmp_path, monkeypatch):
    memory_file = tmp_path / "memory.json"
    memory_file.write_text("{not valid json}")
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))

    with pytest.raises(RuntimeError, match=str(memory_file)):
        load_week_entries("2026-06-06", "2026-06-12")


# ---------------------------------------------------------------------------
# 14. Date filter boundary — inclusive on both ends, exclusive outside
# ---------------------------------------------------------------------------

def test_date_filter_boundary(tmp_path, monkeypatch):
    entries = [
        {"date": "2026-06-06", "title": "boundary start", "url": "https://a.com"},
        {"date": "2026-06-12", "title": "boundary end", "url": "https://b.com"},
        {"date": "2026-06-05", "title": "too early", "url": "https://c.com"},
        {"date": "2026-06-13", "title": "too late", "url": "https://d.com"},
    ]
    memory_file = tmp_path / "memory.json"
    memory_file.write_text(json.dumps(entries))
    monkeypatch.setattr(arc_digest, "MEMORY_PATH", str(memory_file))

    result = load_week_entries("2026-06-06", "2026-06-12")
    titles = [e["title"] for e in result]

    assert "boundary start" in titles
    assert "boundary end" in titles
    assert "too early" not in titles
    assert "too late" not in titles
