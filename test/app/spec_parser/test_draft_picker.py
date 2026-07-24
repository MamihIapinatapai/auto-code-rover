"""Tests for v3.3 draft best-of scoring."""

from app.spec_parser.draft_picker import pick_best_draft, score_draft
from app.spec_parser.schema import DraftMetrics


def test_score_prefers_behavioral_and_calib_pass():
    a = DraftMetrics(
        draft_id="r1",
        round_no=1,
        calibration_passed=True,
        behavioral_ac_count=5,
        lint_violations=0,
    )
    b = DraftMetrics(
        draft_id="r2",
        round_no=2,
        calibration_passed=True,
        behavioral_ac_count=1,
        existence_only_ac_count=4,
        lint_violations=0,
    )
    a.score = score_draft(a)
    b.score = score_draft(b)
    best = pick_best_draft([a, b])
    assert best is not None
    assert best.draft_id == "r1"


def test_pick_ignores_failed_calibration():
    a = DraftMetrics(
        draft_id="r1",
        round_no=1,
        calibration_passed=False,
        behavioral_ac_count=10,
    )
    a.score = score_draft(a)
    assert pick_best_draft([a]) is None


def test_tie_break_earlier_round():
    a = DraftMetrics(
        draft_id="r1",
        round_no=1,
        calibration_passed=True,
        behavioral_ac_count=3,
    )
    b = DraftMetrics(
        draft_id="r2",
        round_no=2,
        calibration_passed=True,
        behavioral_ac_count=3,
    )
    a.score = score_draft(a)
    b.score = score_draft(b)
    best = pick_best_draft([a, b])
    assert best is not None
    assert best.draft_id == "r1"
