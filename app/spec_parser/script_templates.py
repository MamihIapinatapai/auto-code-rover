"""Fallback script templates when LLM generation fails."""

from __future__ import annotations

from app.spec_parser.schema import AcceptanceCriterion, StructuredSpecification, TaskType


_PRINT_STACKTRACE = '''
def print_stacktrace(e: Exception):
    import traceback
    import sys
    tb = traceback.extract_tb(e.__traceback__)
    print("Traceback (most recent call last):", file=sys.stderr)
    for frame in tb:
        line_number = frame.lineno
        code_context = frame.line.strip() if frame.line else "Unknown"
        print(f'  File "{frame.filename}"', file=sys.stderr)
        print(f"    {line_number}: {code_context}", file=sys.stderr)
    print(f"{e.__class__.__name__}: {e}", file=sys.stderr)
'''


def render_ac_stub(ac: AcceptanceCriterion) -> str:
    obs = ac.observable.lower()
    if "ne" in obs or "relational" in ac.covers_entity.lower():
        return """
# --- {id} ---
from sympy import symbols, Ne
from sympy.printing.ccode import ccode
x = symbols('x')
out_ne = ccode(Ne(x, 0))
assert "!=" in out_ne, out_ne
""".format(id=ac.id)
    if "sinc" in obs or "sinc" in ac.covers_entity.lower():
        return """
# --- {id} ---
from sympy import symbols, sinc
from sympy.printing.ccode import ccode
x = symbols('x')
out_sinc = ccode(sinc(x))
assert "Not supported" not in out_sinc
assert "\\n" in out_sinc or "Piecewise" in out_sinc or len(out_sinc) > 20
""".format(id=ac.id)
    if "permutation" in obs.lower():
        return """
# --- {id} ---
from sympy.combinatorics import Permutation
p = Permutation([[0, 1], [0, 1]])
assert p == Permutation([])
""".format(id=ac.id)
    return f"""
# --- {ac.id} ---
raise AssertionError("Stub for {ac.observable}")
"""


def render_minimal_script(spec: StructuredSpecification) -> str:
    must = [ac for ac in spec.acceptance_criteria if ac.priority == "must"]
    stubs = [render_ac_stub(ac) for ac in must]
    filename = (
        "reproduce_issue.py"
        if spec.task_type == TaskType.BUG_FIX
        else "test_feature.py"
    )
    body = "\n".join(stubs)
    return f'''"""Auto-generated acceptance script for: {spec.summary}"""
{_PRINT_STACKTRACE}

def main():
{body.replace(chr(10), chr(10) + "    ")}
    print("All checks passed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_stacktrace(e)
        raise
'''
