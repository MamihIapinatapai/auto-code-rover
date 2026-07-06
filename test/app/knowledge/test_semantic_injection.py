"""Tests for SymPy semantic knowledge injection (ver1.1)."""

import json
from pathlib import Path

from app.data_structures import BugLocation
from app.knowledge.semantic_injection import (
    build_search_final_round_checklist,
    build_semantic_context,
    build_semantic_context_ver1,
    detect_module_families,
    should_inject_sympy_rules,
)
from app.knowledge.sympy_semantic_rules import (
    ALL_SYMPY_RULES,
    ISSUE_SCOPE_AND_COMPLETENESS,
    LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT,
    MINIMAL_COMPLETE_PATCH,
    MODULE_PATTERN_SCAN,
    PRINTING_DELEGATION_AND_DEPENDENCY,
    REVIEWER_COMPLETENESS_GATE,
    select_sympy_rules,
)
from app.knowledge.ver1 import ACR_LOG_PREFIX, ACR_VERSION, ver1_prompt_header
from app.task import SweTask


def _make_sympy_task(**overrides) -> SweTask:
    defaults = dict(
        task_id="sympy__sympy-11400",
        problem_statement="ccode(sinc(x)) doesn't work",
        repo_path="/tmp/sympy",
        commit="abc123",
        env_name="sympy_env",
        repo_name="sympy/sympy",
        repo_version="1.0",
        pre_install_cmds=[],
        install_cmd="pip install -e .",
        test_cmd="bin/test",
        test_patch="assert ccode(sinc(x))",
        testcases_passing=["test_a"],
        testcases_failing=["test_ccode_sinc"],
    )
    defaults.update(overrides)
    return SweTask(**defaults)


def test_ver1_constants():
    assert ACR_VERSION == "ver1.1"
    assert "AutoCodeRover-ver1.1" in ACR_LOG_PREFIX


def test_ver1_prompt_header():
    header = ver1_prompt_header("patch")
    assert ACR_LOG_PREFIX in header
    assert "ver1.1" in header


def test_should_inject_by_sympy_path(tmp_path):
    task = _make_sympy_task(repo_name="other/other", task_id="other__other-1")
    py_file = tmp_path / "sympy" / "printing" / "ccode.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text("def _print_Foo(self, x):\n    return self._print(x)\n")

    class _SR:
        file_path = str(py_file)
        start = 1
        end = 2
        class_name = "CCodePrinter"
        func_name = "_print_Foo"

    bug_loc = BugLocation(_SR(), str(tmp_path), "fix")
    assert should_inject_sympy_rules(task, [bug_loc]) is True


def test_select_sympy_rules_phase_search():
    rules = select_sympy_rules(phase="search")
    names = {r.name for r in rules}
    assert ISSUE_SCOPE_AND_COMPLETENESS.name in names
    assert LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT.name in names
    assert MODULE_PATTERN_SCAN.name in names
    assert PRINTING_DELEGATION_AND_DEPENDENCY.name not in names


def test_select_sympy_rules_phase_patch_printing():
    rules = select_sympy_rules(
        file_paths=["sympy/printing/ccode.py"],
        phase="patch",
    )
    names = {r.name for r in rules}
    assert MINIMAL_COMPLETE_PATCH.name in names
    assert PRINTING_DELEGATION_AND_DEPENDENCY.name in names


def test_select_sympy_rules_phase_review():
    rules = select_sympy_rules(phase="review")
    names = {r.name for r in rules}
    assert REVIEWER_COMPLETENESS_GATE.name in names


def test_all_sympy_rules_count():
    assert len(ALL_SYMPY_RULES) == 6


def test_detect_module_families_printing():
    families = detect_module_families(["sympy/printing/ccode.py"], "")
    assert "printing" in families


def test_build_search_final_round_checklist_printing():
    task = _make_sympy_task()
    checklist = build_search_final_round_checklist(
        task, module_families_detected=["printing"]
    )
    assert "Neighbor Contract" in checklist
    assert "neighbor_reference" in checklist


def test_build_semantic_context_ver1_writes_metadata(tmp_path):
    task = _make_sympy_task()
    context = build_semantic_context_ver1(
        task, phase="patch", task_dir=str(tmp_path)
    )
    assert context is not None
    assert ACR_LOG_PREFIX in context
    meta = json.loads((tmp_path / "semantic_injection_ver1.json").read_text())
    assert meta["version"] == "ver1.1"
    assert meta["phase"] == "patch"


def test_build_semantic_context_non_sympy_returns_none():
    task = _make_sympy_task(repo_name="django/django", task_id="django__django-1")
    context = build_semantic_context(task, phase="patch")
    assert context is None
