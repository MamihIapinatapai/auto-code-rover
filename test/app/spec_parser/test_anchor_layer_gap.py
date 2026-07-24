from app.spec_parser.schema import ScriptAnchor
from app.spec_parser.script_anchor import detect_layer_gaps


def test_detect_layer_gaps_cli_http():
    anchor = ScriptAnchor(layer_hints={"cli": "unknown", "http": "absent", "library": "present"})
    gaps = detect_layer_gaps("Add CLI and HTTP /api/snapshot endpoints", anchor)
    assert "LAYER_GAP_CLI" in gaps
    assert "LAYER_GAP_HTTP" in gaps


def test_no_gap_when_present():
    anchor = ScriptAnchor(layer_hints={"cli": "present", "http": "present"})
    assert detect_layer_gaps("CLI and HTTP API", anchor) == []
