"""Prompts for v3.2 acceptance-script reviewer LLM."""

from __future__ import annotations

import json

from app.spec_parser.schema import ScriptLintReport, TaskType

LINT_RULE_DIGEST = """
- L1-MISSING-AC: every must AC id needs `# --- AC-XXX ---`
- L2-COFIX-*: grounded co_fix symbols need executable assert/raise
- L3-WEAK-ASSERT-*: weak numeric/prereq probes
  bad: assert result > 0 / assert x is not None as the only check
  good: assert concrete Issue value/behavior (e.g. aliases == expected mapping)
- L4-SWALLOW-EXCEPTION: except body must not be bare pass/return False/empty
  on broad Exception/BaseException without re-raise; legal:
  (A) except SpecificError: pass  # expected negative path
  (B) except Exception as e: raise AssertionError(f"AC-XXX FAIL: {e}") from e
  Forbidden: except Exception: pass / except: pass
- L7-NUMPY-LAMBDA: no numpy lambdify shortcuts
- L8-FUTURE-IMPORT: no bad __future__ placement
- L9-FAKE-IMPORT: no path-hack imports
- L10-EXISTENCE-ONLY: no AC that only uses hasattr/callable/is not None/assert True
  bad: assert hasattr(obj, "foo")
  good: call foo with Issue inputs and assert observable outcome / raise AC FAIL
- L11-DEAD-AC: do not define test_* without calling them; prefer inline AC bodies
  bad: def test_ac001(): ...  # never called
  good: inline body under `# --- AC-001 ---` or call the helper
- L12-STUB-AC: no unconditional raise AssertionError("Stub ...")
  bad: raise AssertionError("Stub AC-001")
  good: real call + behavioral assert, or NOT_IMPLEMENTED only when API missing
- L13-VACUOUS-ASSERT: no assert True
- L14-EMPTY-FAIL: no AC that only raises NotImplementedError / NOT_IMPLEMENTED
  without a prior product API probe call
  bad: raise NotImplementedError("todo")
  good: result = api.fn(issue_input); assert result == expected  OR probe then NOT_IMPLEMENTED
""".strip()

SCRIPT_REVIEW_SYSTEM_PROMPT = """You are an acceptance-script review assistant for AutoCodeRover Spec Parser v3.2.

You are NOT the final examiner. Machine lint and calibration Gate outrank you.

Hard priority (never violate):
1. Static lint blocking rules
2. Calibration Gate (FEATURE: intentional AC FAIL / NOT_IMPLEMENTED; not pure ENV ImportError)
3. Issue text coverage and assertion strength
4. Style / readability

Conflict policy:
- If improving Issue coverage conflicts with lint/Gate, choose a lint/Gate-legal rewrite.
- Forbidden suggestions: except Exception: pass / except: pass; Stub-only raises;
  existence-only AC (hasattr-only); uncalled def test_*; using pytest/sympy ModuleNotFoundError
  as the script's only failure mode; inventing APIs or test points not in the Issue.
- Prefer blocking_fixes / gate_fixes first; put Issue gaps that cannot be fixed without
  risking lint into deferred_issue_gaps.

Evidence chain (Issue↔AC) — v3.3:
- Emit issue_coverage_chain[]: one entry per Issue Must/Should you can anchor with a verbatim
  issue_quote (<=200 chars).
- Fields per item: issue_item_id, issue_quote, ac_id, expected_layer, actual_layer,
  product_calls[], assertion_strength, evidence_type, verdict, legal_rewrite
  (when fixable without violating lint).
- verdict: covered|partial|missing|over_spec|deferred
- assertion_strength: strong|medium|weak|wrong_layer|missing|existence|stub
- Do NOT mark covered when AC only proxies CLI/Web via lower-level API calls.

Decision summary — v3.3:
- Emit decision_summary: { lint_vs_issue_conflict: bool, top_missing_must: [...],
  recommended_priority: "lint_first" }
- When lint/gate conflicts with coverage fixes, verdict MUST be deferred and legal_rewrite empty.

Minimal legal behavior template (for L10/L12/L14 blocking):
- Each blocking_fix MUST include a 5-15 line bad→good example with at least one real library
  call and a value or exception assertion (not is not None only).

Output MUST be a single JSON object (no markdown fences) with keys:
{
  "diagnosis": {
    "failure_class": "lint|gate_feature|gate_env|mixed|none",
    "summary": "<=2 sentences of what is wrong this round"
  },
  "blocking_fixes": [
    {"rule": "exact id from blocking_rules", "bad_pattern": "...",
     "legal_rewrite": "pasteable code skeleton", "why_legal": "..."}
  ],
  "gate_fixes": [
    {"kind": "intentional_ac_fail|not_implemented|env_not_script|other",
     "evidence": "from validation_reason/stderr",
     "legal_rewrite": "pasteable skeleton; empty when env_not_script",
     "why": "..."}
  ],
  "issue_alignment": [
    {"kind": "missing_must|weak_assert|over_spec_risk", "detail": "...",
     "legal_rewrite": "pasteable or empty if deferred", "superseded_by_blocking": false}
  ],
  "issue_coverage_chain": [
    {"issue_item_id": "I1", "issue_quote": "...", "ac_id": "AC-001",
     "expected_layer": "api|cli|web|any", "actual_layer": "api|cli|web|proxy|unknown",
     "product_calls": [], "assertion_strength": "strong|weak|wrong_layer|missing",
     "evidence_type": "behavioral|structural|existence|none",
     "verdict": "covered|partial|missing|over_spec|deferred", "legal_rewrite": ""}
  ],
  "decision_summary": {
    "lint_vs_issue_conflict": false,
    "top_missing_must": [],
    "recommended_priority": "lint_first"
  },
  "deferred_issue_gaps": ["..."],
  "ordered_actions": [
    "1. Clear blocking lint/gate first ...",
    "2. Then Issue gaps ..."
  ]
}

Rewrite quality:
- legal_rewrite must be a pasteable code skeleton the author can apply; ban vague advice
  like "strengthen asserts" without code.
- ordered_actions: <=15 ordered lines for the script author model; start with blocking
  lint/gate, then Issue gaps (missing Must before weak_assert).

ScriptAnchor (machine, may be incomplete) — v3.3.1:
- When writing issue_coverage_chain.product_calls and legal_rewrite:
  Prefer symbols/entrypoints listed in ScriptAnchor (see user message if present).
- If expected_layer=cli|web and Anchor layer_hints show present, legal_rewrite MUST use
  that entry style (CliRunner/console script or HTTP client), not only lower-level library calls.
- Do not invent parameter names that contradict signature_runtime/signature_ast when conf>=0.5.

Do NOT inject official/hidden tests, solution patches, or sample_test excerpts.
Anchor only on Issue text + the provided script + machine evidence (+ ScriptAnchor if provided).
"""


def _stage_task_block(stage: str) -> str:
    if stage == "gate":
        return """## Task (stage=gate)
Review against calibration Gate evidence and the Issue. Emit JSON only.
1. Set diagnosis.failure_class: gate_feature (intentional AC FAIL / NOT_IMPLEMENTED missing),
   gate_env (pure ENV ImportError e.g. pytest/sympy missing), mixed, or none.
2. If gate_env: put a gate_fixes entry with kind=env_not_script; legal_rewrite MUST be empty;
   do NOT invent script logic patches for missing env packages.
3. If gate_feature: gate_fixes must give pasteable rewrites so the script fails with
   AssertionError AC-XXX FAIL / NOT_IMPLEMENTED (not ModuleNotFoundError alone).
4. blocking_fixes only if blocking_rules is non-empty (else []).
5. Content may be truncated — only comment on visible regions; put suspected off-screen
   gaps into deferred_issue_gaps. Do not invent symbols absent from visible Issue text.
6. ordered_actions must start with: fix blocking lint/gate first, then Issue gaps.
"""
    return """## Task (stage=preflight)
Review against lint machine evidence and the Issue. Emit JSON only.
1. Set diagnosis.failure_class to "lint" when blocking_rules is non-empty.
2. blocking_fixes MUST cover every listed blocking_rules id (one entry per rule minimum)
   with LEGAL pasteable legal_rewrite skeletons.
3. gate_fixes should usually be [].
4. If Issue gaps conflict with lint, set superseded_by_blocking=true and/or use
   deferred_issue_gaps.
5. Content may be truncated — only comment on visible regions; put suspected off-screen
   gaps into deferred_issue_gaps. Do not invent symbols absent from visible Issue text.
6. ordered_actions must start with: fix blocking lint first, then Issue gaps.
"""


def format_script_review_user(
    *,
    issue_text: str,
    script_content: str,
    task_type: TaskType | str,
    stage: str,
    round_no: int,
    lint_report: ScriptLintReport | None,
    validation_reason: str = "",
    failed_criteria_ids: list[str] | None = None,
    stderr_excerpt: str = "",
    exit_code: int | None = None,
    script_anchor_compact: str = "",
) -> str:
    tt = task_type.value if isinstance(task_type, TaskType) else str(task_type)
    blocking = list(lint_report.blocking_rules) if lint_report else []
    missing = list(lint_report.missing_ac_ids) if lint_report else []
    issue_truncated = len(issue_text) > 6000
    script_truncated = len(script_content) > 12000
    issue_excerpt = (
        issue_text if not issue_truncated else issue_text[:6000] + "\n...(truncated)"
    )
    script_excerpt = (
        script_content
        if not script_truncated
        else script_content[:12000] + "\n# ...(truncated)"
    )
    payload = {
        "task_type": tt,
        "stage": stage,
        "round_no": round_no,
        "blocking_rules": blocking,
        "missing_ac_ids": missing,
        "validation_reason": validation_reason,
        "failed_criteria_ids": failed_criteria_ids or [],
        "exit_code": exit_code,
        "stderr_excerpt": (stderr_excerpt or "")[:4000],
        "issue_truncated": issue_truncated,
        "script_truncated": script_truncated,
    }
    anchor_section = ""
    if script_anchor_compact:
        anchor_section = (
            "\n## ScriptAnchor (compact)\n```\n"
            + script_anchor_compact[:3000]
            + "\n```\n"
        )
    return (
        f"""## Machine constraints (AUTHORITATIVE — do not contradict)

### Lint rule digest
{LINT_RULE_DIGEST}

### This-round machine evidence
```json
{json.dumps(payload, indent=2, ensure_ascii=False)}
```

## Issue (authoritative for coverage; do not invent symbols absent here)
```
{issue_excerpt}
```

## Current acceptance script
```python
{script_excerpt}
```
"""
        + anchor_section
        + "\n"
        + _stage_task_block(stage)
    )
