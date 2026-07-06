# Probe Review Template

Copy to `experiment/spec_parser_probe/{instance_id}/probe_review.md`.

## L1-A Issue extraction
- [ ] repair_goals authoritative (not draft copy)
- [ ] symptom vs repair separated
- [ ] fix_scope / negative_constraints present

## L1-B Static enrichment
- [ ] repo_enrichment matches clinical GT

## L1-C Script and dynamic evidence
- [ ] AC sections in reproduce_issue.py
- [ ] calibration_passed on buggy code
- [ ] primary_failure_ac_id correct (11400: AC-REL)

## L1-D Search context
- [ ] search_context.txt includes repair_goals, co_fix, negatives

## Notes
