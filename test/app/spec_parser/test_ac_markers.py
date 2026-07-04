"""Tests for unified AC marker parsing."""

from app.spec_parser.ac_markers import (
    ac_ids_in_script,
    extract_ac_section_body,
    parse_ac_sections,
)


def test_dash_colon_format():
    script = "# --- AC-001: primary failure ---\nraise AssertionError('x')"
    assert ac_ids_in_script(script) == {"AC-001"}


def test_equals_format():
    script = "=== AC-002 ===\nassert False"
    assert "AC-002" in ac_ids_in_script(script)


def test_def_test_alias():
    script = "def test_ac_rel():\n    assert False"
    found = parse_ac_sections(script, ["AC-REL"])
    assert "AC-REL" in found.found


def test_missing_must_ids():
    script = "# --- AC-001 ---\n"
    m = parse_ac_sections(script, ["AC-001", "AC-002"])
    assert m.missing == ["AC-002"]


def test_extract_section_body():
    script = """import sys
# --- AC-001: first ---
x = 1
# --- AC-002: second ---
y = 2
"""
    body = extract_ac_section_body(script, "AC-001")
    assert body is not None
    assert "x = 1" in body
    assert "y = 2" not in body
