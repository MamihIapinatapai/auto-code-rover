"""
This agent selects the search APIs to use, and returns the selected APIs in its response in
non-json format.
"""

import re
from collections.abc import Generator
from pathlib import Path

from loguru import logger

from app import config
from app.data_structures import MessageThread
from app.infrastructure.shared_memory import SharedMemoryStore
from app.knowledge.semantic_injection import (
    build_search_final_round_checklist,
    build_semantic_context_ver1,
    build_sibling_scan_prompt,
    detect_module_families,
)
from app.knowledge.ver1 import ACR_LOG_PREFIX
from app.log import print_acr, print_retrieval
from app.model import common, ollama
from app.task import Task

SYSTEM_PROMPT = """You are a software developer maintaining a large project.
You are working on an issue submitted to your project.
The issue contains a description marked between <issue> and </issue>.
Your task is to invoke a few search API calls to gather sufficient code context for resolving the issue.
The collected context will later be sent to your colleage for writing a patch.
Do not worry about test files or writing test; you are only interested in crafting a patch.
"""


SELECT_PROMPT = (
    "Based on the files, classes, methods, and code statements from the issue related to the bug, you can use the following search APIs to get more context of the project."
    "\n- search_class(class_name: str): Search for a class in the codebase."
    "\n- search_class_in_file(self, class_name, file_name: str): Search for a class in a given file."
    "\n- search_method_in_file(method_name: str, file_path: str): Search for a method in a given file.."
    "\n- search_method_in_class(method_name: str, class_name: str): Search for a method in a given class."
    "\n- search_method(method_name: str): Search for a method in the entire codebase."
    "\n- search_code(code_str: str): Search for a code snippet in the entire codebase."
    "\n- search_code_in_file(code_str: str, file_path: str): Search for a code snippet in a given file file."
    "\n- get_code_around_line(file_path: str, line_number: int, window_size: int): Get the code around a given line number in a file. window_size is the number of lines before and after the line number."
    "\n\nYou must give correct number of arguments when invoking API calls."
    "\n\nNote that you can use multiple search APIs in one round."
    "\n\nNow analyze the issue and select necessary APIs to get more context of the project. Each API call must have concrete arguments as inputs."
)


ANALYZE_PROMPT = (
    "Let's analyze collected context first.\n"
    "If an API call could not find any code, you should think about what other API calls you can make to get more context.\n"
    "If an API call returns some result, you should analyze the result and think about these questions:\n"
    "1. What does this part of the code do?\n"
    "2. What is the relationship between this part of the code and the bug?\n"
    "3. Given the issue description, what would be the intended behavior of this part of the code?\n"
)


ANALYZE_AND_SELECT_PROMPT = (
    "Based on your analysis, answer below questions:\n"
    "1. do we need more context: construct search API calls to get more context of the project. "
    "If you don't need more context, LEAVE THIS EMPTY.\n"
    "2. bug_locations:\n"
    "   - One entry per needs_fix=yes row ONLY (from sibling scan decision tree).\n"
    "   - Each intended_behavior MUST satisfy LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT.\n"
    "   - Include spec_source, spec_rationale per location; neighbor_reference when using neighbor_contract.\n"
    "   - If any needs_fix=yes, bug_locations MUST NOT be empty.\n"
    "   - If more context needed: API_calls non-empty, bug_locations EMPTY.\n"
    "   - For each location: file, class, method, intended_behavior, spec_source, spec_rationale, "
    "and neighbor_reference/neighbor_eligibility when applicable."
)


def prepare_issue_prompt(problem_stmt: str) -> str:
    problem_wo_comments = re.sub(r"<!--.*?-->", "", problem_stmt, flags=re.DOTALL)
    content_lines = problem_wo_comments.split("\n")
    content_lines = [x.strip() for x in content_lines]
    content_lines = [x for x in content_lines if x != ""]
    problem_stripped = "\n".join(content_lines)
    return "<issue>" + problem_stripped + "\n</issue>"


def _run_analyze_and_select(
    msg_thread: MessageThread,
    task: Task | None,
    task_dir: str | None,
) -> tuple[str, str]:
    """Steps ③ and ④: analyze+select then dedicated sibling scan."""
    analyze_and_select_prompt = ANALYZE_AND_SELECT_PROMPT
    if isinstance(common.SELECTED_MODEL, ollama.OllamaModel):
        analyze_and_select_prompt += (
            "\n\nNOTE: If you have already identified the bug locations, "
            "do not make any search API calls."
        )

    if task is not None and config.enable_sympy_pipeline_v2:
        families = detect_module_families([], task.get_issue_statement())
        checklist = build_search_final_round_checklist(
            task, module_families_detected=families
        )
        if checklist:
            msg_thread.add_user(checklist)
            print_acr(checklist, "final localization checklist")

    msg_thread.add_user(analyze_and_select_prompt)
    print_acr(analyze_and_select_prompt, "context retrieval analyze and select prompt")

    logger.debug("<Agent search> Analyze and select (step 3).")
    res_text, *_ = common.SELECTED_MODEL.call(msg_thread.to_msg())
    msg_thread.add_model(res_text)
    print_retrieval(res_text, "Model response (analyze and select)")

    sibling_scan_text = ""
    if config.enable_sympy_pipeline_v2:
        sibling_prompt = build_sibling_scan_prompt()
        msg_thread.add_user(sibling_prompt)
        print_acr(sibling_prompt, "sibling scan prompt (step 4)")
        logger.debug("<Agent search> Sibling scan dedicated call (step 4).")
        sibling_scan_text, *_ = common.SELECTED_MODEL.call(msg_thread.to_msg())
        msg_thread.add_model(sibling_scan_text)
        print_retrieval(sibling_scan_text, "Model response (sibling scan)")

    combined = res_text
    if sibling_scan_text:
        combined += "\n\n--- SIBLING_SCAN ---\n" + sibling_scan_text
    return res_text, combined


def generator(
    issue_stmt: str,
    sbfl_result: str,
    reproducer_result: str,
    task: Task | None = None,
    task_dir: str | None = None,
) -> Generator[tuple[str, MessageThread], tuple[str, bool | str] | None, None]:
    msg_thread = MessageThread()
    msg_thread.add_system(SYSTEM_PROMPT)

    issue_prompt = prepare_issue_prompt(issue_stmt)
    msg_thread.add_user(issue_prompt)

    if task is not None:
        semantic_context = build_semantic_context_ver1(
            task, phase="search", task_dir=task_dir
        )
        if semantic_context:
            msg_thread.add_user(semantic_context)
            logger.info("{} semantic rules injected (search)", ACR_LOG_PREFIX)

    if config.enable_sbfl:
        sbfl_prompt = (
            "An external analysis tool has been deployed to identify the suspicious code "
            "to be fixed. You can choose to use the results from this tool, if you think they are useful."
        )
        sbfl_prompt += "The tool output is as follows:\n"
        sbfl_prompt += sbfl_result
        msg_thread.add_user(sbfl_prompt)

    if config.reproduce_and_review and reproducer_result:
        reproducer_prompt = (
            "An external analysis tool has been deployed to construct tests that reproduce "
            "the issue. You can choose to use the results from this tool, if you think they are useful."
        )
        reproducer_prompt += "The tool output is as follows:\n"
        reproducer_prompt += reproducer_result
        msg_thread.add_user(reproducer_prompt)

    if config.enable_spec_parser and task_dir:
        swm = SharedMemoryStore.read(Path(task_dir).parent)
        if swm is None:
            swm = SharedMemoryStore.read(task_dir)
        if swm is not None:
            repair_contract = SharedMemoryStore.to_search_context(swm)
            msg_thread.add_user(
                "=== Repair Contract from Specification Parser (authoritative over Issue draft) ===\n"
                + repair_contract
            )
            logger.info("{} injected repair contract from SWM", ACR_LOG_PREFIX)

    msg_thread.add_user(SELECT_PROMPT)
    print_acr(SELECT_PROMPT, "context retrieval initial prompt")

    localization_rewrite_pending = False

    while True:
        if not localization_rewrite_pending:
            logger.debug("<Agent search> Selecting APIs to call.")
            res_text, *_ = common.SELECTED_MODEL.call(msg_thread.to_msg())
            msg_thread.add_model(res_text)
            print_retrieval(res_text, "Model response (API selection)")

            generator_input = yield res_text, msg_thread
            assert generator_input is not None
            search_result, re_search = generator_input

            if re_search is True:
                logger.debug(
                    "<Agent search> Downstream could not consume our last response. Will retry."
                )
                msg_thread.add_user(search_result)
                continue

            logger.debug("<Agent search> Analyzing search results.")
            msg_thread.add_user(search_result)
        else:
            localization_rewrite_pending = False

        msg_thread.add_user(ANALYZE_PROMPT)
        print_acr(ANALYZE_PROMPT, "context retrieval analyze prompt")

        res_text, *_ = common.SELECTED_MODEL.call(msg_thread.to_msg())
        msg_thread.add_model(res_text)
        print_retrieval(res_text, "Model response (context analysis)")

        _, combined_response = _run_analyze_and_select(msg_thread, task, task_dir)

        generator_input = yield combined_response, msg_thread
        assert generator_input is not None
        search_result, re_search = generator_input

        if re_search is True:
            logger.debug(
                "<Agent search> Downstream could not consume analyze/select response. Will retry."
            )
            msg_thread.add_user(search_result)
            continue

        if re_search == "localization_rewrite":
            logger.debug("<Agent search> Localization rewrite requested.")
            msg_thread.add_user(search_result)
            localization_rewrite_pending = True
            continue
