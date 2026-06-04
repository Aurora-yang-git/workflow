"""Tests for scripts/memory_manager.py — parse_items_from_summary and find_followup."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from memory_manager import find_followup, parse_items_from_summary

# Minimal but realistic Horizon EN summary fixture (matches actual output format)
SAMPLE_EN_MD = """\
# Horizon Daily - 2026-06-03

> From 15 items, 2 important content pieces were selected

---

1. [Microsoft Unveils MAI Models](#item-1) ⭐️ 8.0/10
2. [Quantum Randomness Breakthrough](#item-2) ⭐️ 8.0/10

---

<a id="item-1"></a>
## [Microsoft Unveils MAI Models](https://example.com/mai) ⭐️ 8.0/10

Microsoft announced two new models using a Mixture of Experts architecture.

**Tags**: `#AI`, `#LLM`, `#Microsoft`, `#efficiency`

---

<a id="item-2"></a>
## [Quantum Randomness Breakthrough](https://example.com/quantum) ⭐️ 8.0/10

Physicists achieved perfect randomness using quantum entanglement.

**Tags**: `#quantum physics`, `#randomness`, `#cryptography`

---
"""


# --- parse_items_from_summary ---

def test_parse_items_count():
    items = parse_items_from_summary(SAMPLE_EN_MD)
    assert len(items) == 2


def test_parse_items_titles():
    items = parse_items_from_summary(SAMPLE_EN_MD)
    assert items[0]["title"] == "Microsoft Unveils MAI Models"
    assert items[1]["title"] == "Quantum Randomness Breakthrough"


def test_parse_items_urls():
    items = parse_items_from_summary(SAMPLE_EN_MD)
    assert items[0]["url"] == "https://example.com/mai"
    assert items[1]["url"] == "https://example.com/quantum"


def test_parse_items_entities_first_item():
    items = parse_items_from_summary(SAMPLE_EN_MD)
    entities = items[0]["entities"]
    # parse_tags lowercases all entity names
    assert "ai" in entities
    assert "llm" in entities
    assert "microsoft" in entities
    assert "efficiency" in entities


def test_parse_items_entities_second_item():
    items = parse_items_from_summary(SAMPLE_EN_MD)
    entities = items[1]["entities"]
    assert "quantum physics" in entities
    assert "randomness" in entities
    assert "cryptography" in entities


def test_parse_items_empty_document():
    assert parse_items_from_summary("") == []


def test_parse_items_no_tags_section():
    md = "## [Title](https://example.com/x) ⭐️ 7.0/10\n\nSome content.\n\n---\n"
    items = parse_items_from_summary(md)
    assert len(items) == 1
    assert items[0]["entities"] == []


# --- find_followup ---

def test_find_followup_two_shared_entities_matches():
    item = {"entities": ["ai", "llm", "microsoft"]}
    memory = [{"title": "Prior", "date": "2026-06-01", "entities": ["ai", "llm", "regulation"]}]
    result = find_followup(item, memory)
    assert result is not None
    assert result["title"] == "Prior"


def test_find_followup_one_shared_entity_no_match():
    item = {"entities": ["ai", "healthcare"]}
    memory = [{"title": "Prior", "date": "2026-06-01", "entities": ["ai", "regulation"]}]
    assert find_followup(item, memory) is None


def test_find_followup_exact_threshold_two_matches():
    item = {"entities": ["ai", "llm"]}
    memory = [{"title": "Prior", "date": "2026-06-01", "entities": ["ai", "llm"]}]
    assert find_followup(item, memory) is not None


def test_find_followup_picks_most_recent_entry():
    item = {"entities": ["ai", "llm"]}
    memory = [
        {"title": "Older", "date": "2026-05-01", "entities": ["ai", "llm"]},
        {"title": "Newer", "date": "2026-05-20", "entities": ["ai", "llm"]},
    ]
    assert find_followup(item, memory)["title"] == "Newer"


def test_find_followup_empty_memory():
    assert find_followup({"entities": ["ai", "llm"]}, []) is None


def test_find_followup_empty_item_entities():
    memory = [{"title": "Prior", "date": "2026-06-01", "entities": ["ai", "llm"]}]
    assert find_followup({"entities": []}, memory) is None
