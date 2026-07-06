"""
A proxy agent. Process raw response into json format.
"""

import inspect
import re
from typing import Any

from loguru import logger

from app import config
from app.data_structures import MessageThread
from app.model import common
from app.post_process import ExtractStatus, is_valid_json
from app.search.search_backend import SearchBackend
from app.utils import parse_function_invocation

PROXY_PROMPT = """
You are a helpful assistant that retrieve API calls and bug locations from a text into json format.
The text may consist of:
1. do we need more context? (API_calls)
2. where are bug locations? (bug_locations with spec fields)
3. sibling scan table (sibling_scan) — may appear after --- SIBLING_SCAN --- marker

Extract API calls from question 1 (leave empty list if not exist).
Extract bug locations from question 2 (leave empty list if not exist).
Extract sibling_scan table rows (leave empty list if not present).

Each bug_location should include when possible:
file, class, method, intended_behavior, spec_source, spec_rationale,
neighbor_reference, neighbor_eligibility, handler_category

Each sibling_scan row should include:
method_or_handler, class, file, anti_pattern_id, safe, needs_fix, scope_proof, evidence_snippet

Provide your answer in JSON structure like this:

{
    "API_calls": ["api_call_1(args)", "api_call_2(args)", ...],
    "sibling_scan": [
        {
            "method_or_handler": "...",
            "class": "...",
            "file": "...",
            "anti_pattern_id": "AP-...",
            "safe": "yes|no|unknown",
            "needs_fix": "yes|no|unknown",
            "scope_proof": "...",
            "evidence_snippet": "..."
        }
    ],
    "bug_locations":[
        {
            "file": "path/to/file",
            "class": "class_name",
            "method": "method_name",
            "intended_behavior": "...",
            "spec_source": "issue_example|neighbor_contract|scan_inferred|mixed",
            "spec_rationale": "...",
            "neighbor_reference": "...",
            "neighbor_eligibility": "...",
            "handler_category": "operator_node|function_arg|parent_inherited|property_eval|guard"
        }
    ]
}

Make sure each API call is written as a valid python expression.
"""


SIBLING_SCAN_PROXY_PROMPT = """
Extract ONLY the sibling_scan table from the text into JSON.
Return: {"sibling_scan": [...]} with rows containing method_or_handler, class, file,
anti_pattern_id, safe, needs_fix, scope_proof, evidence_snippet.
"""


def run_with_retries(text: str, retries=5) -> tuple[str | None, list[MessageThread]]:
    msg_threads = []
    for idx in range(1, retries + 1):
        logger.debug(
            "Trying to convert API calls/bug locations into json. Try {} of {}.",
            idx,
            retries,
        )

        res_text, new_thread = run(text)
        msg_threads.append(new_thread)

        extract_status, data = is_valid_json(res_text)

        if extract_status != ExtractStatus.IS_VALID_JSON:
            logger.debug("Invalid json. Will retry.")
            continue

        valid, diagnosis = is_valid_response(data)
        if not valid:
            logger.debug(f"{diagnosis}. Will retry.")
            continue

        logger.debug("Extracted a valid json.")
        return res_text, msg_threads
    return None, msg_threads


def run_sibling_scan_proxy(text: str, retries=3) -> tuple[list[dict], list[MessageThread]]:
    """Extract sibling_scan from dedicated step ④ response."""
    scan_text = text
    if "--- SIBLING_SCAN ---" in text:
        scan_text = text.split("--- SIBLING_SCAN ---", 1)[1]

    msg_threads = []
    for idx in range(1, retries + 1):
        msg_thread = MessageThread()
        msg_thread.add_system(SIBLING_SCAN_PROXY_PROMPT)
        msg_thread.add_user(scan_text)
        res_text, *_ = common.SELECTED_MODEL.call(
            msg_thread.to_msg(), response_format="json_object"
        )
        msg_thread.add_model(res_text, [])
        msg_threads.append(msg_thread)

        extract_status, data = is_valid_json(res_text)
        if extract_status != ExtractStatus.IS_VALID_JSON:
            continue
        if isinstance(data, dict) and isinstance(data.get("sibling_scan"), list):
            return data["sibling_scan"], msg_threads
    return [], msg_threads


def run(text: str) -> tuple[str, MessageThread]:
    msg_thread = MessageThread()
    msg_thread.add_system(PROXY_PROMPT)
    msg_thread.add_user(text)
    res_text, *_ = common.SELECTED_MODEL.call(
        msg_thread.to_msg(), response_format="json_object"
    )
    msg_thread.add_model(res_text, [])
    return res_text, msg_thread


def merge_proxy_responses(main_json: dict, sibling_scan: list[dict]) -> dict:
    if sibling_scan and not main_json.get("sibling_scan"):
        main_json["sibling_scan"] = sibling_scan
    return main_json


def is_valid_response(data: Any) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Json is not a dict"

    api_calls = data.get("API_calls") or []
    bug_locations = data.get("bug_locations") or []
    sibling_scan = data.get("sibling_scan") or []

    if not api_calls:
        if not isinstance(bug_locations, list):
            return False, "bug_locations must be a list"
        if not bug_locations:
            return False, "Both API_calls and bug_locations are empty"

        for loc in bug_locations:
            if not isinstance(loc, dict):
                return False, "Each bug location must be an object"
            if loc.get("class") or loc.get("method") or loc.get("file"):
                continue
            return (
                False,
                "Bug location not detailed enough. Each location must contain at least a class or a method or a file.",
            )

        if config.enable_sympy_pipeline_v2:
            if not sibling_scan:
                return False, "bug_locations non-empty requires sibling_scan"
            if not isinstance(sibling_scan, list):
                return False, "sibling_scan must be a list"
            for loc in bug_locations:
                if not loc.get("spec_source"):
                    return False, "spec_source required for each bug_location"
                if not loc.get("spec_rationale"):
                    return False, "spec_rationale required for each bug_location"
                if loc.get("spec_source") == "neighbor_contract":
                    if not loc.get("neighbor_reference"):
                        return False, "neighbor_reference required for neighbor_contract"
                    if not loc.get("neighbor_eligibility"):
                        return False, "neighbor_eligibility required for neighbor_contract"
    else:
        for api_call in api_calls:
            if not isinstance(api_call, str):
                return False, "Every API call must be a string"

            try:
                func_name, func_args = parse_function_invocation(api_call)
            except Exception:
                return False, "Every API call must be of form api_call(arg1, ..., argn)"

            function = getattr(SearchBackend, func_name, None)
            if function is None:
                return False, f"the API call '{api_call}' calls a non-existent function"

            while "__wrapped__" in function.__dict__:
                function = function.__wrapped__

            arg_spec = inspect.getfullargspec(function)
            arg_names = arg_spec.args[1:]

            if len(func_args) != len(arg_names):
                return False, f"the API call '{api_call}' has wrong number of arguments"

    return True, "OK"


def parse_sibling_scan_from_text(text: str) -> list[dict]:
    """Fallback: parse markdown table rows without LLM."""
    rows: list[dict] = []
    section = text
    if "--- SIBLING_SCAN ---" in text:
        section = text.split("--- SIBLING_SCAN ---", 1)[1]
    for line in section.splitlines():
        if "|" not in line or line.strip().startswith("|--"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 4 and cells[0] not in (
            "method_or_handler",
            "Method",
            "method",
        ):
            rows.append(
                {
                    "method_or_handler": cells[0],
                    "anti_pattern_id": cells[3] if len(cells) > 3 else "",
                    "safe": cells[4] if len(cells) > 4 else "unknown",
                    "needs_fix": cells[5] if len(cells) > 5 else "unknown",
                    "scope_proof": cells[6] if len(cells) > 6 else "",
                    "evidence_snippet": cells[7] if len(cells) > 7 else "",
                }
            )
    return rows
