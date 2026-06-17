import json
import os
import sys
import urllib.error
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
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(return_value="application/json")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _gh_issue_response(body: str = "## [SpaceX IPO](https://example.com/spacex)\nSpaceX priced at $135."):
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


def _article_response(html: str = "<html><body><p>SpaceX IPO priced at $135 per share in Q2 2026.</p></body></html>"):
    resp = MagicMock()
    resp.read.return_value = html.encode()
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(return_value="text/html; charset=utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── _parse_digest_articles ──────────────────────────────────────────────────

def test_parse_digest_articles_extracts_urls(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    digest = (
        "## [SpaceX IPO](https://example.com/spacex)\nSome summary.\n\n"
        "## [OpenAI raises $10B](https://example.com/openai)\nAnother summary."
    )
    result = qa_responder._parse_digest_articles(digest)
    assert result == {
        "SpaceX IPO": "https://example.com/spacex",
        "OpenAI raises $10B": "https://example.com/openai",
    }


def test_parse_digest_articles_skips_anchor_links(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    # TOC lines use #item-N — should be skipped
    digest = (
        "1. [SpaceX IPO](#item-1)\n\n"
        "## [SpaceX IPO](https://example.com/spacex)\nReal URL."
    )
    result = qa_responder._parse_digest_articles(digest)
    assert result == {"SpaceX IPO": "https://example.com/spacex"}


def test_parse_digest_articles_empty_digest(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    assert qa_responder._parse_digest_articles("") == {}


# ── _identify_article ───────────────────────────────────────────────────────

def test_identify_article_returns_matching_title(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    titles = ["SpaceX IPO", "OpenAI raises $10B", "Google AI safety"]
    with patch("urllib.request.urlopen", return_value=_deepseek_response("SpaceX IPO")):
        result = qa_responder._identify_article("What happened with SpaceX?", titles)
    assert result == "SpaceX IPO"


def test_identify_article_returns_none_when_no_match(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    titles = ["SpaceX IPO", "OpenAI raises $10B"]
    with patch("urllib.request.urlopen", return_value=_deepseek_response("NONE")):
        result = qa_responder._identify_article("What is the weather today?", titles)
    assert result is None


def test_identify_article_returns_none_on_empty_titles(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen") as mock:
        result = qa_responder._identify_article("question", [])
    mock.assert_not_called()
    assert result is None


def test_identify_article_fuzzy_matches_close_title(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    # LLM returns slightly reformatted title
    titles = ["SpaceX IPO announced at $135"]
    with patch("urllib.request.urlopen", return_value=_deepseek_response("SpaceX IPO announced")):
        result = qa_responder._identify_article("SpaceX IPO?", titles)
    assert result == "SpaceX IPO announced at $135"


def test_identify_article_retries_on_429(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    call_count = [0]

    def mock_urlopen(req, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.HTTPError(url="", code=429, msg="rate limited", hdrs=None, fp=None)
        return _deepseek_response("SpaceX IPO")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("time.sleep"):
            result = qa_responder._identify_article("SpaceX?", ["SpaceX IPO"])
    assert call_count[0] == 2
    assert result == "SpaceX IPO"


def test_identify_article_returns_none_on_error(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen", side_effect=RuntimeError("network error")):
        result = qa_responder._identify_article("question", ["SpaceX IPO"])
    assert result is None


# ── _fetch_article ──────────────────────────────────────────────────────────

def test_fetch_article_returns_text(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen", return_value=_article_response()):
        result = qa_responder._fetch_article("https://example.com/spacex")
    assert "SpaceX" in result
    assert "$135" in result


def test_fetch_article_strips_script_tags(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    html = "<html><head><script>alert('xss')</script></head><body><p>Article body text.</p></body></html>"
    with patch("urllib.request.urlopen", return_value=_article_response(html)):
        result = qa_responder._fetch_article("https://example.com/article")
    assert "alert" not in result
    assert "Article body text" in result


def test_fetch_article_returns_empty_on_error(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        result = qa_responder._fetch_article("https://example.com/article")
    assert result == ""


def test_fetch_article_truncates_long_content(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    long_html = f"<html><body><p>{'x' * 20000}</p></body></html>"
    with patch("urllib.request.urlopen", return_value=_article_response(long_html)):
        result = qa_responder._fetch_article("https://example.com/article")
    assert len(result) <= qa_responder.MAX_ARTICLE_CHARS


# ── call_deepseek ──────────────────────────────────────────────────────────────

def test_call_deepseek_returns_content(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    with patch("urllib.request.urlopen", return_value=_deepseek_response("**Based on 'SpaceX IPO':** Priced at $135.")):
        result = qa_responder.call_deepseek("What happened with SpaceX?", "SpaceX IPO article content here.")
    assert "SpaceX" in result


def test_call_deepseek_includes_article_text_in_prompt(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    captured = []

    def mock_urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        return _deepseek_response("answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.call_deepseek("question", "digest", article_text="Full article content here.")

    user_content = captured[0]["messages"][1]["content"]
    assert "Full article content here" in user_content
    assert "primary source" in user_content


def test_call_deepseek_omits_article_section_when_empty(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    captured = []

    def mock_urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        return _deepseek_response("answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.call_deepseek("question", "digest", article_text="")

    user_content = captured[0]["messages"][1]["content"]
    assert "primary source" not in user_content


def test_call_deepseek_truncates_long_digest(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    long_digest = "x" * 15000
    captured = []

    def mock_urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        return _deepseek_response("answer")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.call_deepseek("question", long_digest)

    user_content = captured[0]["messages"][1]["content"]
    assert "truncated" in user_content
    assert len(user_content) < 15000 + 200


def test_call_deepseek_retries_on_429(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
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

SAMPLE_DIGEST = (
    "## [SpaceX IPO](https://example.com/spacex)\n"
    "SpaceX priced its IPO at $135 per share.\n\n"
    "## [OpenAI raises $10B](https://example.com/openai)\n"
    "OpenAI closed a $10B funding round."
)


def test_main_fetches_article_and_uses_in_answer(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    call_log = []

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        call_log.append(url)
        if "issues/42/comments" in url:
            return _gh_comment_response()
        if "deepseek" in url:
            payload = json.loads(req.data.decode())
            # Identify call returns article title; answer call returns the answer
            if payload.get("max_tokens") == 100:
                return _deepseek_response("SpaceX IPO")
            return _deepseek_response("**Based on 'SpaceX IPO':** IPO at $135.")
        if "example.com/spacex" in url:
            return _article_response()
        return _gh_issue_response(body=SAMPLE_DIGEST)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert any("example.com/spacex" in u for u in call_log), "Should have fetched the article URL"
    deepseek_calls = [u for u in call_log if "deepseek" in u]
    assert len(deepseek_calls) == 2, "Should make 2 DeepSeek calls (identify + answer)"


def test_main_falls_back_to_digest_when_article_fetch_fails(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "issues/42/comments" in url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        if "deepseek" in url:
            payload = json.loads(req.data.decode())
            if payload.get("max_tokens") == 100:
                return _deepseek_response("SpaceX IPO")
            return _deepseek_response("**Based on 'SpaceX IPO':** Digest-only answer.")
        if "example.com/spacex" in url:
            raise Exception("connection refused")
        return _gh_issue_response(body=SAMPLE_DIGEST)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "🤖" in posted_bodies[0]


def test_main_posts_answer_with_disclaimer(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        if "deepseek" in req.full_url:
            payload = json.loads(req.data.decode())
            if payload.get("max_tokens") == 100:
                return _deepseek_response("NONE")
            return _deepseek_response("**Based on 'SpaceX IPO':** Priced at $135.")
        return _gh_issue_response(body=SAMPLE_DIGEST)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "🤖" in posted_bodies[0]
    assert "verify" in posted_bodies[0].lower()


@pytest.mark.parametrize("title", [
    "Pull Request: fix typo",
    "Arc Reactor Announcement — not an arc digest",
])
def test_main_skips_non_digest_issue(monkeypatch, title):
    _mock_env(monkeypatch)
    import qa_responder
    monkeypatch.setattr(qa_responder, "ISSUE_TITLE", title)

    with patch("urllib.request.urlopen") as mock:
        qa_responder.main()
    mock.assert_not_called()


def test_main_skips_short_comment(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
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
        return _gh_issue_response(body="")

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
        return _gh_issue_response(body=SAMPLE_DIGEST)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "try again" in posted_bodies[0].lower()


# ── _load_arc_articles ─────────────────────────────────────────────────────────

ARC_TITLE = "Weekly Arc — 2026-06-09 to 2026-06-15"

SAMPLE_MEMORY = [
    {"title": "SpaceX IPO", "url": "https://example.com/spacex", "date": "2026-06-09", "entities": [], "issue_url": ""},
    {"title": "OpenAI raises $10B", "url": "https://example.com/openai", "date": "2026-06-12", "entities": [], "issue_url": ""},
    {"title": "Google AI safety", "url": "https://example.com/google", "date": "2026-06-15", "entities": [], "issue_url": ""},
    {"title": "Old news", "url": "https://example.com/old", "date": "2026-06-08", "entities": [], "issue_url": ""},
    {"title": "Future news", "url": "https://example.com/future", "date": "2026-06-16", "entities": [], "issue_url": ""},
]


def _write_memory(tmp_path, entries=None):
    p = tmp_path / "memory.json"
    p.write_text(json.dumps(entries if entries is not None else SAMPLE_MEMORY))
    return str(p)


def test_load_arc_articles_parses_date_range(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert set(result.keys()) == {"SpaceX IPO", "OpenAI raises $10B", "Google AI safety"}
    assert "Old news" not in result
    assert "Future news" not in result


def test_load_arc_articles_filters_by_week_boundary(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    # Entries exactly on week_start and week_end must be included (inclusive)
    entries = [
        {"title": "Start", "url": "https://example.com/start", "date": "2026-06-09", "entities": [], "issue_url": ""},
        {"title": "End", "url": "https://example.com/end", "date": "2026-06-15", "entities": [], "issue_url": ""},
        {"title": "Before", "url": "https://example.com/before", "date": "2026-06-08", "entities": [], "issue_url": ""},
        {"title": "After", "url": "https://example.com/after", "date": "2026-06-16", "entities": [], "issue_url": ""},
    ]
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path, entries))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert "Start" in result
    assert "End" in result
    assert "Before" not in result
    assert "After" not in result


def test_load_arc_articles_returns_empty_on_no_match(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    entries = [
        {"title": "Unrelated", "url": "https://example.com/x", "date": "2026-05-01", "entities": [], "issue_url": ""},
    ]
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path, entries))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert result == {}


def test_load_arc_articles_graceful_io_error(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    # Point to a nonexistent file
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", str(tmp_path / "nonexistent.json"))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert result == {}


def test_load_arc_articles_graceful_json_error(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    bad_file = tmp_path / "memory.json"
    bad_file.write_text("not valid json {{{{")
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", str(bad_file))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert result == {}


def test_load_arc_articles_filters_empty_title_url(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    entries = [
        {"title": "", "url": "https://example.com/a", "date": "2026-06-12", "entities": [], "issue_url": ""},
        {"title": "Valid", "url": "", "date": "2026-06-12", "entities": [], "issue_url": ""},
        {"title": "Good", "url": "https://example.com/good", "date": "2026-06-12", "entities": [], "issue_url": ""},
    ]
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path, entries))

    result = qa_responder._load_arc_articles(ARC_TITLE)
    assert result == {"Good": "https://example.com/good"}


# ── main() arc path ────────────────────────────────────────────────────────────

ARC_NARRATIVE = (
    "## Story Arc 1: Space Race\n\nThis week SpaceX and Blue Origin competed for orbital contracts.\n\n"
    "## Story Arc 2: AI Safety\n\nRegulators pushed for new AI transparency rules."
)


def test_main_arc_bad_title_posts_error_comment(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder
    monkeypatch.setattr(qa_responder, "ISSUE_TITLE", "Weekly Arc — badly formatted")

    posted_bodies = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        return _gh_issue_response(body=ARC_NARRATIVE)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "parse" in posted_bodies[0].lower() or "date range" in posted_bodies[0].lower()
    # Ensure no DeepSeek call was made (no answer posted)
    assert "arc digest" not in posted_bodies[0].lower()


def test_main_arc_path_empty_articles(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    monkeypatch.setattr(qa_responder, "ISSUE_TITLE", ARC_TITLE)
    # memory.json with no entries in the arc's week
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path, []))

    posted_bodies = []
    identify_calls = [0]

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        if "deepseek" in req.full_url:
            return _deepseek_response("Arc answer from narrative only.")
        return _gh_issue_response(body=ARC_NARRATIVE)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("qa_responder._identify_article", wraps=qa_responder._identify_article) as mock_identify:
            qa_responder.main()
            assert mock_identify.call_count == 0, "_identify_article should not be called when articles is {}"

    assert len(posted_bodies) == 1
    assert "arc digest" in posted_bodies[0]


def test_main_arc_path(monkeypatch, tmp_path):
    _mock_env(monkeypatch)
    import qa_responder
    monkeypatch.setattr(qa_responder, "ISSUE_TITLE", ARC_TITLE)
    monkeypatch.setattr(qa_responder, "MEMORY_PATH", _write_memory(tmp_path))

    posted_bodies = []
    deepseek_payloads = []

    def mock_urlopen(req, timeout=None):
        url = req.full_url
        if "issues/42/comments" in url:
            posted_bodies.append(json.loads(req.data.decode())["body"])
            return _gh_comment_response()
        if "deepseek" in url:
            payload = json.loads(req.data.decode())
            deepseek_payloads.append(payload)
            if payload.get("max_tokens") == 100:
                return _deepseek_response("SpaceX IPO")
            return _deepseek_response("**Based on 'SpaceX IPO':** Arc answer here.")
        if "example.com/spacex" in url:
            return _article_response()
        return _gh_issue_response(body=ARC_NARRATIVE)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    assert len(posted_bodies) == 1
    assert "arc digest" in posted_bodies[0]
    assert "today's digest" not in posted_bodies[0]  # D5: negative regression guard

    # Arc system prompt must be used (not daily prompt)
    answer_payload = next(p for p in deepseek_payloads if p.get("max_tokens") != 100)
    system_content = answer_payload["messages"][0]["content"]
    assert "arc digest" in system_content.lower()
    assert "daily news digest" not in system_content.lower()


def test_main_daily_uses_default_system_prompt(monkeypatch):
    _mock_env(monkeypatch)
    import qa_responder

    captured_payloads = []

    def mock_urlopen(req, timeout=None):
        if "issues/42/comments" in req.full_url:
            return _gh_comment_response()
        if "deepseek" in req.full_url:
            payload = json.loads(req.data.decode())
            captured_payloads.append(payload)
            if payload.get("max_tokens") == 100:
                return _deepseek_response("NONE")
            return _deepseek_response("Daily answer.")
        return _gh_issue_response(body=SAMPLE_DIGEST)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        qa_responder.main()

    # Identity check: system prompt must be exactly _SYSTEM_PROMPT (D8)
    answer_payload = next(p for p in captured_payloads if p.get("max_tokens") != 100)
    system_content = answer_payload["messages"][0]["content"]
    assert system_content == qa_responder._SYSTEM_PROMPT
