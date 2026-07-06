"""
SymPy-specific semantic knowledge rules (v2.2 pipeline).

Rules use Bug Class / Anti-Pattern / module-family wording — no instance-specific hardcoding.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticRule:
    name: str
    scope: str
    prompt_text: str


ISSUE_SCOPE_AND_COMPLETENESS = SemanticRule(
    name="ISSUE_SCOPE_AND_COMPLETENESS",
    scope="global",
    prompt_text="""[ISSUE_SCOPE_AND_COMPLETENESS]

- Issue = symptom report; Reporter code blocks = drafts to VERIFY, not implement.
- Add a new handler/location ONLY when sibling scan or AST dependency chain proves needs_fix=yes.
- Issue listing multiple symptoms does not mean all symptoms need code changes in this patch.
  Second symptom without executable repro / without failing behavior in scan -> needs_fix=no.
- Do NOT skip a sibling with the SAME anti_pattern_id as an already-identified fix (CO_FIX).
- Do NOT add handlers merely because Issue mentions them (SCOPE_CREEP guard).""",
)

LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT = SemanticRule(
    name="LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT",
    scope="search",
    prompt_text="""[LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT]

Applies when writing bug_locations[].intended_behavior (NOT when writing patch code).

MANDATORY — Neighbor Contract Extraction:
Before finalizing intended_behavior for a NEW or OVERRIDE dispatch handler:
1. Identify the nearest Semantic Sibling Reference Handler in the SAME class (same operator family).
2. Quote its return-structure: Outer Wrapper Contract, Primary Join API, Alternate Join API, Bracket Policy.
3. intended_behavior MUST specify the SAME contracts as the sibling source — NOT Issue draft code.

REQUIRED metadata per bug_location:
- spec_source: issue_example | neighbor_contract | scan_inferred | mixed
- spec_rationale: one sentence explaining why this source was chosen
- neighbor_reference: required when spec_source involves neighbor_contract
- neighbor_eligibility: why this handler is a semantic sibling / parent (same class, category, layer, anti_pattern family)

FORBIDDEN in intended_behavior:
- Following Issue example when it CONFLICTS with an eligible neighbor/parent contract.
- Claiming "follow sibling" while specifying contracts that contradict eligible sibling source.
- Adding a bug location to override an Existing Non-Trivial Parent Handler
  UNLESS sibling scan documents proven broken behavior with scope_proof.

NOTE: Following Issue example is ALLOWED when Issue aligns with eligible neighbor OR when no eligible neighbor exists and scan_inferred/issue_example is documented in spec_rationale.

PRINTING appendix — Handler Category taxonomy:
- Operator Node Handlers (integrate/sum/derivative-like families):
  mirror sibling Outer Wrapper + Primary Join API when any semantic sibling uses them.
- Function Argument Handlers:
  Alternate Join API acceptable ONLY when sibling handlers for functions consistently use it.
- Numeric Literal / Parent-Inherited Handlers:
  if parent provides Non-Trivial Implementation (precision logic, special-case branches),
  default intended_behavior = "inherit parent; needs_fix=no" unless scan proves break.""",
)

MODULE_PATTERN_SCAN = SemanticRule(
    name="MODULE_PATTERN_SCAN",
    scope="sympy/*",
    prompt_text="""[MODULE_PATTERN_SCAN]

Purpose: find SAME anti-pattern across siblings — NOT list every Issue-mentioned symptom.

=== Scan table (required before bug_locations in final search round) ===
| method_or_handler | anti_pattern_id | safe? | needs_fix? | scope_proof |

needs_fix=yes ONLY IF:
  (A) Same anti_pattern_id as a confirmed broken handler in this class/file (CO_FIX), OR
  (B) AST dependency gap — planned fix requires Dispatch Dependency Prerequisite, OR
  (C) Missing dispatch override where parent maps type to unsupported-only handler.

needs_fix=no IF:
  (D) Parent provides Existing Non-Trivial Parent Implementation AND scan shows no
      broken behavior in retrieved context (Parent Inheritance Path), OR
  (E) Issue mentions symptom but no code path in scan proves override needed.

=== Anti-Pattern ID registry (module-family level) ===
- AP-PRINT-WRAPPER-JOIN-MISMATCH
- AP-PRINT-INLINE-BYPASS-DELEGATION
- AP-PRINT-LAYER-CONFUSION
- AP-MATRIX-DIM-UNCLAMPED
- AP-MATRIX-SYMMETRIC-SIBLING-OMIT
- AP-COMB-GUARD-CORE-CONFLATION
- AP-DISPATCH-MISSING-PREREQUISITE

=== Module appendix: printing ===
- Layer split: Precedence/Bracket Policy Layer vs Formatting Handler Layer.
- Operator Node family: check Outer Wrapper + Primary Join API across semantic siblings.
- Delegation: prefer AST Composition Delegation Target + self._print over inline target-language strings.

=== Module appendix: matrices ===
- Loop bound vs self.cols/self.rows; Symmetric Property Sibling families (upper/lower/hessenberg).

=== Module appendix: combinatorics / core ===
- Guard layer vs core composition layer separation.""",
)

MINIMAL_COMPLETE_PATCH = SemanticRule(
    name="MINIMAL_COMPLETE_PATCH",
    scope="global",
    prompt_text="""[MINIMAL_COMPLETE_PATCH]

- Fix the entire bug CLASS (all scan needs_fix=yes rows), not Issue bullet list length.
- Smallest diff that achieves completeness — omit scan-marked-safe locations.
- Override Existing Non-Trivial Parent Handler only when scan scope_proof is documented.
- Prefer one delegation path over multiple inline string templates.""",
)

REVIEWER_COMPLETENESS_GATE = SemanticRule(
    name="REVIEWER_COMPLETENESS_GATE",
    scope="review",
    prompt_text="""[REVIEWER_COMPLETENESS_GATE]

Applies when reproduce_and_review is enabled and a reproducer result exists.

- Do NOT approve when patch fixes only the reproducer-narrow symptom but scan table
  shows additional needs_fix=yes siblings with the same anti_pattern_id.
- Decision INCOMPLETE when: sibling CO_FIX rows uncovered, Dispatch Dependency Prerequisite
  missing, or patch reverts from delegation to inline target-language strings.
- Reproducer pass is necessary but NOT sufficient for approval when hidden suite may cover
  broader bug class (BC-ISSUE-TUNNEL guard).""",
)

PRINTING_DELEGATION_AND_DEPENDENCY = SemanticRule(
    name="PRINTING_DELEGATION_AND_DEPENDENCY",
    scope="sympy/printing",
    prompt_text="""[PRINTING_DELEGATION_AND_DEPENDENCY]

- Prefer AST Composition Delegation Target (build internal AST subtree, route via self._print)
  over inline target-language string templates.
- When a planned fix uses conditional rendering, check whether Dispatch Dependency Prerequisite
  handlers exist; add them in the same patch if scan marks needs_fix=yes.
- Do NOT replace delegation chains with inline ternary strings when neighbors use compose+print.
- Trace mutual recursion risk before adding peer handler cross-calls.""",
)

ALL_SYMPY_RULES: tuple[SemanticRule, ...] = (
    ISSUE_SCOPE_AND_COMPLETENESS,
    LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT,
    MODULE_PATTERN_SCAN,
    MINIMAL_COMPLETE_PATCH,
    REVIEWER_COMPLETENESS_GATE,
    PRINTING_DELEGATION_AND_DEPENDENCY,
)

# Backward-compatible aliases for tests migrating from v1
ISSUE_SKEPTICISM_AND_SCOPE = ISSUE_SCOPE_AND_COMPLETENESS
SYMPY_ARCHITECTURE_RECON_AND_REUSE = MODULE_PATTERN_SCAN
MINIMAL_CHANGE_AND_SIBLING_AUDIT = MINIMAL_COMPLETE_PATCH


def _is_printing_path(file_paths: list[str] | None, issue_text: str = "") -> bool:
    paths = file_paths or []
    if any("printing" in p.replace("\\", "/") for p in paths):
        return True
    return "printing" in issue_text.lower()


def select_sympy_rules(
    *,
    file_paths: list[str] | None = None,
    issue_text: str = "",
    phase: str = "patch",
) -> list[SemanticRule]:
    """Route rules by pipeline phase and detected module family."""
    printing = _is_printing_path(file_paths, issue_text)

    if phase == "search":
        rules = [
            ISSUE_SCOPE_AND_COMPLETENESS,
            LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT,
            MODULE_PATTERN_SCAN,
        ]
    elif phase == "patch":
        rules = [
            ISSUE_SCOPE_AND_COMPLETENESS,
            MODULE_PATTERN_SCAN,
            MINIMAL_COMPLETE_PATCH,
        ]
    elif phase == "review":
        rules = [ISSUE_SCOPE_AND_COMPLETENESS, REVIEWER_COMPLETENESS_GATE]
    elif phase == "reproducer":
        rules = [ISSUE_SCOPE_AND_COMPLETENESS]
    else:
        rules = list(ALL_SYMPY_RULES)

    if printing and phase in ("search", "patch", "review", "reproducer"):
        if phase != "search":
            rules.append(PRINTING_DELEGATION_AND_DEPENDENCY)

    return rules
