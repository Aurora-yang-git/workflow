import json
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _mock_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "key")
    monkeypatch.setenv("COMMENT_BODY", "What happened with SpaceX?")
    monkeypatch.setenv("ISSUE_NUMBER", "42")
    monkeypatch.setenv("ISSUE_TITLE", "每日速递 Daily Digest — 2026-06-14")


def _deepseek_response(content: str):
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _gh_issue_response(body: str = "## SpaceX IPO\nSpaceX priced at $135."):
    resp = MagicMock()
    resp.read.return_value = json.dumps({"body": body}).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _gh_comment_response():
    resp = MagicMock()
    resp.read.return_value = json.dumps({"html_url": "https://github.com/owner/repo/issues/42#issuecomment-1"}).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── call_deepseek ──────────────────────────────────────────────────────────────

def test_call_deepseek_returns_content(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen", return_value=_deepseek_response("**Based on 'SpaceX IPO':** Priced at $135.")):
        result = qa_responder.call_deepseek("What happened with SpaceX?", "SpaceX IPO article content here.")
    assert "SpaceX" in result


def test_call_deepseek_truncates_long_digest(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    long_digest = "x" * 15000
    captured_payload = []

    def mock_urlopen(req, timeout=None):
        captured_payload.append(json.loads(req.data.decode()))
        return _deepseek_response("answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.call_deepseek("question", long_digest)

    user_content = captured_payload[0]["messages"][1]["content"]
    assert "truncated" in user_content
    assert len(user_content) < 15000 + 200  # well under original length


def test_call_deepseek_retries_on_429(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    import urllib.error
    call_count = [0]

    def mock_urlopen(req, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.HTTPError(url="", code=429, msg="rate limited", hdrs=None, fp=None)
        return _deepseek_response("retried answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("time.sleep"):
            result = qa_responder.call_deepseek("q", "ctx")
    assert call_count[0] == 2
    assert "retried" in result


def test_call_deepseek_sends_system_prompt_with_citation_instruction(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    captured = []

    def mock_urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        return _deepseek_response("answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.call_deepseek("question", "digest content")

    system_content = captured[0]["messages"][0]["content"]
    assert "article" in system_content.lower()
    assert "same language" in system_content.lower()


# ── main() pipeline ────────────────────────────────────────────────────────────

def test_main_posts_answer_with_disclaimer(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            body = json.loads(req.data.decode())["body"]
            posted_bodies.append(body)
            return _gh_comment_response()
        if "deepseek" in req.full_url:
            return _deepseek_response("**Based on 'SpaceX IPO':** Priced at $135.")
        return _gh_issue_response()

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "🤖" in posted_bodies[0]
    assert "verify" in posted_bodies[0].lower()


def test_main_skips_non_digest_issue(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    # Module-level ISSUE_TITLE is read at import time — patch the attribute directly
    monkeypatch.setattr(qa_responder, "ISSUE_TITLE", "Pull Request: fix typo")

    with patch("urllib.request.urlopen") as mock:
        qa_responder.main()
    mock.assert_not_called()


def test_main_skips_short_comment(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    # Module-level COMMENT_BODY is read at import time — patch the attribute directly
    monkeypatch.setattr(qa_responder, "COMMENT_BODY", "ok")

    with patch("urllib.request.urlopen") as mock:
        qa_responder.main()
    mock.assert_not_called()


def test_main_handles_empty_digest_body(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        return _gh_issue_response(body="")  # empty digest

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "couldn't find" in posted_bodies[0]


def test_main_handles_deepseek_error_gracefully(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        if "deepseek" in req.full_url:
            raise RuntimeError("API down")
        return _gh_issue_response()

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "try again" in posted_bodies[0].lower()
