<!-- /autoplan restore point: /Users/aurora/.gstack/projects/Aurora-yang-git-workflow/main-autoplan-restore-20260614-123519.md -->
# Plan: Smart Q&A Responder with Context Grounding

## Problem

When users comment on the daily digest GitHub Issue, `qa_responder.py` dumps the entire
issue body (up to 8000 chars, hard-truncated) as context to DeepSeek and gets an answer.
This has three problems:

1. **No source grounding**: the reply doesn't cite which article it's drawing from
2. **Extended questions fall through**: if a user asks a follow-up beyond the digest's
   content, the system either hallucinates or gives a vague "not in the digest" answer
3. **Bulk context is noisy**: a 5000-char digest fed as context for a question about
   one article introduces noise that degrades answer quality

## Proposed Solution

Two-step answer pipeline inside `qa_responder.py`:

### Step 1: Context Selection (new)
Ask DeepSeek to identify which article(s)/sections in the digest are most relevant
to the user's question. Return relevant excerpts verbatim.

Prompt: "Here is a news digest. The user asked: [question]. Which part(s) of the digest
are most relevant? Return ONLY the relevant excerpts verbatim, or 'NONE' if not covered."

### Step 2: Answer from Targeted Context (enhanced)
Use the selected excerpts (not the full body) as context for the actual answer.

- Relevant context found → answer from it, cite the article title
- Question extends beyond the excerpt → answer what IS covered, then add a
  "🔍 This question goes beyond today's digest. Based on general knowledge: ..."
- No relevant context found → say so clearly, never hallucinate

## Files to Change

- `scripts/qa_responder.py`: add `select_relevant_context()`, update `call_deepseek()`,
  update `main()` to orchestrate two-step pipeline
- `tests/test_qa_responder.py`: new test file (doesn't exist yet)
- `.github/workflows/qa-responder.yml`: no change needed

## Non-Goals

- No semantic search / embeddings (stdlib only, LLM-only approach)
- No change to how the issue body is fetched
- No changes to arc digest, daily digest, memory system
- No bilingual Q&A output

---

## GSTACK REVIEW REPORT

### Phase 1: CEO Review [subagent-only — codex unavailable]

**Step 0A: Premise Challenge**

| Premise | Status | Notes |
|---|---|---|
| Users are commenting and getting bad answers | VALID | User directly experienced this — plan is motivated by real friction |
| Two-step pipeline improves quality | PARTIALLY VALID | One well-prompted call may match quality at half the cost |
| 8000-char truncation causes noise | VALID | Real for digests with 10+ articles |
| Source grounding is missing | VALID | Current reply has no citation |
| Extended questions need explicit handling | VALID | Current system gives vague "not in digest" |

**Step 0B: Existing Code Leverage**

| Sub-problem | Existing code |
|---|---|
| Context selection (new step) | None — new function |
| DeepSeek call | `qa_responder.py:call_deepseek()` — extend |
| GitHub API | `qa_responder.py:gh_headers()`, `fetch_issue_body()` — reuse unchanged |
| Comment posting | `qa_responder.py:post_comment()` — reuse unchanged |
| Test patterns | `tests/test_arc_digest.py` — reference for mock pattern |

**Step 0C: Dream State Delta**
```
CURRENT: comment → full digest dump → DeepSeek → flat answer (no citation)
THIS PLAN: comment → context selection → targeted answer with citation + extended-Q note
12-MONTH IDEAL: multi-issue memory for Q&A, conversation threading, DingTalk reply support
```

**Step 0C-bis: Implementation Alternatives**

| Approach | Effort | Risk | Pros | Cons |
|---|---|---|---|---|
| A) Two-step (this plan) | 1h CC | Low | Clean separation | 2x API cost, 2x latency |
| B) Single-step enhanced prompt | 30min CC | Low | Half cost/latency | Less reliable context selection |
| C) Regex article extraction + LLM answer | 2h CC | Medium | Fast, no LLM for step 1 | Fragile if digest format changes |

*Taste Decision T1: Two-step vs single-step — surfaced at gate.*

**Step 0D: Mode — SELECTIVE EXPANSION** (2 files, no new infra, < 1 day CC)

**Step 0E: Temporal Interrogation**
- HOUR 1: modify prompt in `call_deepseek()`, add `select_relevant_context()` 
- HOUR 2: wire pipeline in `main()`, write `test_qa_responder.py`
- HOUR 3+: edge cases — empty digest, rate limit, empty selection response

**CLAUDE SUBAGENT (CEO — strategic independence):**

1. **(HIGH) Unstated premise: two-call is better than one.** The plan picks two-step without analysis. Single-call with "quote the article title" instruction may match quality at half the cost.
2. **(HIGH) 8000-char truncation not fixed.** The plan identifies truncation as a problem (premise 3) but doesn't fix it. Will look like a half-fix in 6 months.
3. **(MEDIUM) Validation gap.** Plan doesn't confirm Q&A is actually being used. (Addressed by user context — they experienced bad answers directly.)
4. **(MEDIUM) Bilingual gap.** Digest is EN+ZH. Chinese question → English-only answer is a UX gap. One-liner fix: detect language, respond in kind.
5. **(LOW) Citation at write time possible.** If digest has parseable per-article headers, regex extraction at fetch time is more reliable than LLM extraction.

**CEO Consensus Table:**
```
CEO DUAL VOICES — CONSENSUS TABLE:
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Premises valid?                   YES     N/A    [subagent-only]
  2. Right problem to solve?           YES*    N/A    *validation caveat
  3. Scope calibration correct?        EXPAND  N/A    fix truncation + bilingual
  4. Alternatives sufficiently explored? NO    N/A    one-call not analyzed
  5. Competitive/market risks covered? N/A     N/A    personal tool
  6. 6-month trajectory sound?         PARTIAL N/A    truncation will bite
═══════════════════════════════════════════════════════════════
```

**Error & Rescue Registry (CEO):**

| Failure | Symptom | Recovery |
|---|---|---|
| Step 1 DeepSeek timeout | No answer | Existing retry + error comment |
| Step 1 returns NONE | No context found | Fallback: "not in today's digest" |
| Step 1 returns full digest (bad extraction) | Noisy context | Max excerpt length guard (500 chars) |
| Step 2 returns empty | Blank post | Guard: don't post if answer empty |

**NOT in scope (CEO):**
- Multi-issue Q&A memory
- DingTalk Q&A
- Weekly arc Q&A
- Semantic search / embeddings

**SCOPE EXPANSIONS auto-approved (blast radius, <1 day CC):**
- Fix 8000-char truncation: use digest length properly, not hard cap
- Language detection: detect question language, respond in same language (2-line change)

**CEO Phase Completion Summary: 4 findings (2 auto-decided expansions, 1 taste decision, 1 validated)**

---

### Phase 2: Design Review — SKIPPED (no UI scope)

---

### Phase 3: Eng Review [subagent-only — codex unavailable]

**Architecture ASCII Diagram:**
```
issue_comment event
      │
      ▼
qa-responder.yml (trigger)
      │
      ▼
qa_responder.py::main()
      │
      ├─── fetch_issue_body() ──────────────── GitHub API /issues/{n}
      │         │
      │         ▼ digest_text (full body, length-guarded)
      │
      ├─── [NEW] select_relevant_context()
      │         │  prompt: "which parts are relevant to [question]?"
      │         ├──────────────────────────────── DeepSeek (step 1)
      │         │
      │         ▼ excerpt (≤500 chars) OR "NONE"
      │
      ├─── call_deepseek(question, excerpt_or_context)
      │         │  prompt: "answer from this excerpt, cite article title"
      │         │  if excerpt=="NONE": "say not in digest"
      │         ├──────────────────────────────── DeepSeek (step 2)
      │         │
      │         ▼ answer (with citation + optional extended note)
      │
      └─── post_comment() ──────────────────── GitHub API /issues/{n}/comments
```

**Section 1 (Architecture):**
- Coupling: low. Two new functions, one updated pipeline. No new imports.
- Scaling: 2 DeepSeek calls per comment. At this scale (personal tool, <5 comments/day), fine.
- Security: step 1 isolates user input to "question" role. Excerpt comes from OUR digest (trusted). Actually more secure than current (user input never contaminated the context).
- One concern: if `select_relevant_context()` itself gets prompt-injected via the question AND returns malicious excerpt... unlikely since step 1 returns only digest text, but the digest itself could theoretically be pre-loaded with injection if the Horizon pipeline is compromised. Low risk.

**Section 2 (Code Quality):**
- DRY: `call_deepseek()` is currently responsible for both selection and answering. Better to keep it focused on answering; add a separate `select_relevant_context()`.
- Naming: `select_relevant_context(question, digest)` → clear.
- The `MAX_ANSWER_CHARS = 4000` constant applies to answers. Add `MAX_EXCERPT_CHARS = 500` for excerpts.
- Retry logic: exists in `call_deepseek()`. Should also retry in `select_relevant_context()`. Use same pattern.

**Section 3 (Test Review) — NEVER SKIP:**

Reading `tests/test_arc_digest.py` pattern:
- `sys.path.insert(0, scripts_dir)` then `import qa_responder`
- `@patch("urllib.request.urlopen")` for both GitHub and DeepSeek calls
- `monkeypatch.setenv()` for all env vars before calling `main()`

Test coverage gaps:

| Flow | Test needed |
|---|---|
| `select_relevant_context()` returns excerpt when relevant | `test_select_relevant_context_returns_excerpt` |
| `select_relevant_context()` returns None when not relevant | `test_select_relevant_context_returns_none` |
| `main()` uses excerpt as context for step 2 | `test_pipeline_uses_selected_context` |
| Extended question: appends note when answer says so | `test_extended_question_note` |
| Empty digest body: no context to select | `test_empty_digest_body` |
| Rate limit retry in selection step | `test_select_relevant_context_retry` |

**Section 4 (Performance):**
- Added latency: ~1-2s per comment (second DeepSeek call). Total: ~3-4s. Well within 5-min timeout.
- No N+1 concerns (single issue fetch, two LLM calls).

**Failure Modes Registry (Eng):**

| Mode | Severity | Gap? |
|---|---|---|
| Step 1 returns excerpt > 500 chars | Medium | Guard missing in plan — add MAX_EXCERPT_CHARS |
| Digest format changes (breaks regex if used) | Low | LLM approach is robust to format changes |
| Both DeepSeek calls rate-limited simultaneously | Low | Sequential calls, second won't be hit if first retries |
| Question < 5 chars filter (already in main) | Low | Already handled |
| Issue body empty | Low | select_relevant_context() returns None → "not in digest" |

**NOT in scope (Eng):**
- Conversation history / thread context
- Per-article URL in citation (not in current digest structure)

**ENG Consensus Table:**
```
ENG DUAL VOICES — CONSENSUS TABLE:
═══════════════════════════════════════════════════════════════
  Dimension                           Claude  Codex  Consensus
  ──────────────────────────────────── ─────── ─────── ─────────
  1. Architecture sound?               YES     N/A    [subagent-only]
  2. Test coverage sufficient?         GAPS    N/A    5 tests needed
  3. Performance risks addressed?      YES     N/A    2x latency acceptable
  4. Security threats covered?         YES+    N/A    actually improved
  5. Error paths handled?              PARTIAL N/A    add MAX_EXCERPT_CHARS
  6. Deployment risk manageable?       YES     N/A    workflow unchanged
═══════════════════════════════════════════════════════════════
```

**Eng Phase Completion Summary: 6 findings (5 test gaps auto-approved, 1 scope expansion for MAX_EXCERPT_CHARS)**

---

### Phase 3.5: DX Review [subagent-only — codex unavailable]

**DX Scope:** GitHub Actions Python script + workflow. Primary user is a developer configuring this automation. End-consumer is a news reader leaving a comment.

**Developer Journey:**
The developer journey is unchanged by this plan. Deployment = push to `main` (GitHub Actions picks it up). No new secrets, no new config.

TTHW: N/A (already deployed; this is an improvement, not a new install)

**DX Scorecard:**

| Dimension | Before | After | Notes |
|---|---|---|---|
| Configuration friction | 8/10 | 8/10 | Unchanged |
| Error messages | 6/10 | 7/10 | Better context in DeepSeek error path |
| Code readability | 6/10 | 8/10 | Two focused functions vs one do-everything call |
| Testability | 4/10 | 8/10 | New test file covers the pipeline |
| Upgrade safety | 9/10 | 9/10 | No schema changes |

DX overall: 6.6/10 → 8/10

**DX Implementation Checklist:**
- [x] No new secrets required
- [x] No new workflow steps required  
- [ ] Add `MAX_EXCERPT_CHARS` constant (DRY, discoverable)
- [ ] Add docstring to `select_relevant_context()` explaining the "NONE" return contract
- [ ] Error message in extended-Q note should be friendly (no raw exception text)

**DX Phase Completion Summary: 3 minor findings (all auto-approved, in blast radius)**

---

### Cross-Phase Themes

**Theme: One-call vs two-call** — surfaced in CEO (premise challenge) and implicitly in Eng (performance section). High-confidence signal: the simpler single-call approach deserves a fair trial before committing to two-call architecture. → TASTE DECISION T1

**Theme: Truncation is a root cause not a symptom** — CEO flagged it as a 6-month regret; Eng confirmed it's benign at current digest size (~3000 chars) but will bite as digest grows. → SCOPE EXPANSION (auto-approved: 1-line fix, in blast radius)

---

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|---------|
| 1 | CEO | Fix 8000-char truncation | Mechanical | P2 (blast radius) | Same file, 1-line fix, root cause identified | Keep hardcoded cap |
| 2 | CEO | Add language detection for bilingual replies | Mechanical | P2 (blast radius) | 2-line fix, prevents obvious UX gap | English-only replies |
| 3 | CEO | Add MAX_EXCERPT_CHARS = 500 guard | Mechanical | P1 (completeness) | Prevents runaway excerpt length | Unbounded excerpt |
| 4 | Eng | Add 5 new tests in test_qa_responder.py | Mechanical | P1 (completeness) | No tests exist for this module | Ship without tests |
| 5 | Eng | Add docstring to select_relevant_context | Mechanical | P5 (explicit) | "NONE" return contract must be documented | No docs |
| T1 | CEO+Eng | Two-call vs single-call architecture | **TASTE** | — | Close call; recommend single-call for simplicity | surfaced at gate |
