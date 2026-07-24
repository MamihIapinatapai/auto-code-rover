"""v3.3 best-of draft selection among calibration candidates."""

from __future__ import annotations

from pathlib import Path

from app.spec_parser.schema import DraftMetrics, ScriptLintReport
from app.spec_parser.script_linter import count_behavioral_acs


def score_draft(metrics: DraftMetrics) -> float:
    """draft_score_v33 or frozen draft_score_v34 (FINAL WP-SCR)."""
    from app import config

    ver = str(getattr(config, "spec_parser_draft_score_version", "v33") or "v33")
    if ver == "v34":
        return _score_v34(metrics)

    score = 100.0 if metrics.calibration_passed else 0.0
    score += metrics.behavioral_ac_count * 8
    score -= metrics.lint_violations * 10
    score -= metrics.existence_only_ac_count * 12
    score -= metrics.empty_fail_ac_count * 25
    score -= metrics.coverage_missing_must * 6
    score -= metrics.coverage_wrong_layer * 4
    score -= metrics.anchor_layer_gap_count * 3
    w_sig = float(
        getattr(config, "spec_parser_anchor_score_signature_weight", 0.0) or 0.0
    )
    score -= metrics.anchor_signature_violations * w_sig
    return float(score)


def _score_v34(metrics: DraftMetrics) -> float:
    feature_ok = metrics.feature_calib_ok or (
        metrics.calibration_passed and metrics.harness_error == 0
    )
    score = 0.0
    score += metrics.concrete_expect_ac_count * 12
    score += metrics.recipe_compliance_bonus * 15
    score += (10 if metrics.scc_m_pass else 0)
    score += metrics.behavioral_ac_count * 6
    score += 20 if feature_ok else 0
    score += 8 if metrics.contract_path_s1 else 0
    score -= metrics.existence_only_ac_count * 15
    score -= metrics.empty_fail_ac_count * 25
    score -= metrics.false_fail_risk_hits * 30
    score -= metrics.lint_violations * 10
    score -= metrics.coverage_missing_must * 6
    score -= metrics.coverage_wrong_layer * 10
    score -= metrics.harness_error * 20
    # env_fail * 0 intentionally omitted
    return float(score)


def build_draft_metrics(
    *,
    round_no: int,
    script_content: str,
    lint_report: ScriptLintReport | None,
    calibration_passed: bool,
    must_ids: list[str] | None = None,
    coverage_missing_must: int = 0,
    coverage_wrong_layer: int = 0,
    concrete_expect_ac_count: int = 0,
    recipe_compliance_bonus: int = 0,
    scc_m_pass: bool = False,
    contract_path_s1: bool = False,
    feature_calib_ok: bool = False,
    false_fail_risk_hits: int = 0,
    harness_error: int = 0,
) -> DraftMetrics:
    blocking = list(lint_report.blocking_rules) if lint_report else []
    counts = count_behavioral_acs(script_content, must_ids)
    if concrete_expect_ac_count <= 0:
        concrete_expect_ac_count = max(
            0, counts["behavioral_ac_count"] - counts["existence_only_ac_count"]
        )
    metrics = DraftMetrics(
        draft_id=f"r{round_no}",
        round_no=round_no,
        script_content=script_content,
        lint_violations=len(blocking),
        blocking_rules=blocking,
        behavioral_ac_count=counts["behavioral_ac_count"],
        existence_only_ac_count=counts["existence_only_ac_count"],
        empty_fail_ac_count=counts["empty_fail_ac_count"],
        calibration_passed=calibration_passed,
        coverage_missing_must=coverage_missing_must,
        coverage_wrong_layer=coverage_wrong_layer,
        concrete_expect_ac_count=concrete_expect_ac_count,
        recipe_compliance_bonus=recipe_compliance_bonus,
        scc_m_pass=scc_m_pass,
        contract_path_s1=contract_path_s1,
        feature_calib_ok=feature_calib_ok or calibration_passed,
        false_fail_risk_hits=false_fail_risk_hits,
        harness_error=harness_error,
    )
    metrics.score = score_draft(metrics)
    return metrics


def pick_best_draft(candidates: list[DraftMetrics]) -> DraftMetrics | None:
    """Pick among calibration_passed candidates; tie-break fewer lint then earlier round."""
    from app import config

    ver = str(getattr(config, "spec_parser_draft_score_version", "v33") or "v33")
    if ver == "v34":
        # Prefer feature_calib / scc among passed; also allow contract S1 with feature signal
        passed = [
            c
            for c in candidates
            if c.calibration_passed or (c.contract_path_s1 and c.concrete_expect_ac_count > 0)
        ]
        # Exclude pure harness-only "fake pass"
        passed = [c for c in passed if c.harness_error == 0 or c.calibration_passed]
        if not passed:
            passed = [c for c in candidates if c.calibration_passed]
        if not passed:
            return None
        return sorted(
            passed,
            key=lambda c: (-c.score, c.round_no, c.lint_violations),
        )[0]

    passed = [c for c in candidates if c.calibration_passed]
    if not passed:
        return None
    return sorted(
        passed,
        key=lambda c: (-c.score, c.lint_violations, c.round_no),
    )[0]


def best_draft_overall(candidates: list[DraftMetrics]) -> DraftMetrics | None:
    """Best draft by score even if not calib_pass (for regen base / feedback)."""
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda c: (-c.score, c.lint_violations, c.round_no),
    )[0]


def persist_candidate(output_dir: Path, metrics: DraftMetrics) -> None:
    path = output_dir / f"draft_candidates_round_{metrics.round_no}.json"
    path.write_text(metrics.model_dump_json(indent=2))
