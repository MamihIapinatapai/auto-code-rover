import inspect
import json
from collections.abc import Mapping
from os.path import join as pjoin
from pathlib import Path

from loguru import logger

from app import config
from app.agents import agent_proxy, agent_search
from app.data_structures import BugLocation, LocalizationContext, MessageThread
from app.knowledge.intended_behavior_linter import (
    format_rewrite_message,
    has_blocking_findings,
    lint_localization,
    write_validation_report,
)
from app.knowledge.scan_validator import enrich_scan_suggestions, validate_sibling_scan
from app.knowledge.semantic_injection import detect_module_families
from app.log import print_acr, print_banner
from app.search.search_backend import SearchBackend
from app.task import Task
from app.utils import parse_function_invocation


class SearchManager:
    def __init__(self, project_path: str, output_dir: str):
        self.output_dir = pjoin(output_dir, "search")
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.tool_call_layers: list[list[Mapping]] = []
        self.backend: SearchBackend = SearchBackend(project_path)
        self.localization_context: LocalizationContext | None = None
        self._localization_rewrite_count = 0
        self._last_partial_artifact: dict | None = None

    @property
    def localization_artifact_path(self) -> str:
        return str(Path(self.output_dir) / "localization_artifact.json")

    def search_iterative(
        self,
        task: Task,
        sbfl_result: str,
        reproducer_result: str,
        reproduced_test_content: str | None,
    ) -> tuple[list[BugLocation], MessageThread]:
        search_api_generator = agent_search.generator(
            task.get_issue_statement(),
            sbfl_result,
            reproducer_result,
            task=task,
            task_dir=self.output_dir,
        )
        generator_input = None
        round_no = 0
        search_msg_thread: MessageThread | None = None

        for round_no in range(config.conv_round_limit):
            self.start_new_tool_call_layer()
            print_banner(f"CONTEXT RETRIEVAL ROUND {round_no}")

            agent_search_response, search_msg_thread = search_api_generator.send(
                generator_input
            )

            conversation_file = Path(self.output_dir, f"search_round_{round_no}.json")
            search_msg_thread.save_to_file(conversation_file)

            selected_apis, proxy_threads = agent_proxy.run_with_retries(
                agent_search_response
            )

            proxy_msg_log = Path(self.output_dir, f"agent_proxy_{round_no}.json")
            proxy_messages = [thread.to_msg() for thread in proxy_threads]
            proxy_msg_log.write_text(json.dumps(proxy_messages, indent=4))

            if selected_apis is None:
                logger.debug(
                    "Could not extract API calls from agent search response, asking search agent to re-generate response."
                )
                search_result_msg = (
                    "The search API calls seem not valid. Please check the arguments "
                    "you give carefully and try again."
                )
                generator_input = (search_result_msg, True)
                continue

            selected_apis_json: dict = json.loads(selected_apis)

            if config.enable_sympy_pipeline_v2:
                extra_scan, _ = agent_proxy.run_sibling_scan_proxy(agent_search_response)
                if extra_scan:
                    selected_apis_json = agent_proxy.merge_proxy_responses(
                        selected_apis_json, extra_scan
                    )
                if not selected_apis_json.get("sibling_scan"):
                    parsed = agent_proxy.parse_sibling_scan_from_text(
                        agent_search_response
                    )
                    if parsed:
                        selected_apis_json["sibling_scan"] = parsed

            json_api_calls = selected_apis_json.get("API_calls", [])
            buggy_locations = selected_apis_json.get("bug_locations", [])
            sibling_scan = selected_apis_json.get("sibling_scan", [])

            self._last_partial_artifact = {
                "round": round_no,
                "sibling_scan": sibling_scan,
                "bug_locations_raw": buggy_locations,
                "module_families_detected": detect_module_families(
                    [loc.get("file", "") for loc in buggy_locations],
                    task.get_issue_statement(),
                ),
                "checklist_injected": config.enable_sympy_pipeline_v2,
            }

            formatted = []
            if json_api_calls:
                formatted.append("API calls:")
                for call in json_api_calls:
                    formatted.extend([f"\n- `{call}`"])

            if buggy_locations:
                formatted.append("\n\nBug locations")
                for location in buggy_locations:
                    s = ", ".join(f"{k}: `{v}`" for k, v in location.items())
                    formatted.extend([f"\n- {s}"])

            if sibling_scan:
                formatted.append("\n\nSibling scan rows: " + str(len(sibling_scan)))

            print_acr("\n".join(formatted), "Agent-selected API calls")

            if buggy_locations and (not json_api_calls):
                bug_loc_file = Path(
                    self.output_dir, "bug_locations_before_process.json"
                )
                bug_loc_file.write_text(json.dumps(buggy_locations, indent=4))

                artifact_path = Path(self.localization_artifact_path)
                artifact_path.write_text(
                    json.dumps(self._last_partial_artifact, indent=2)
                )

                if config.enable_sympy_pipeline_v2:
                    scan_findings = validate_sibling_scan(
                        self.backend,
                        sibling_scan,
                        project_path=self.backend.project_path,
                    )
                    blocking_scan = [f for f in scan_findings if f.severity == "block"]
                    if blocking_scan:
                        scan_report = Path(self.output_dir) / "scan_validation.json"
                        scan_report.write_text(
                            json.dumps(
                                [
                                    {
                                        "rule_id": f.rule_id,
                                        "severity": f.severity,
                                        "remediation": f.remediation,
                                    }
                                    for f in scan_findings
                                ],
                                indent=2,
                            )
                        )
                        if self._localization_rewrite_count < 1:
                            self._localization_rewrite_count += 1
                            msg = "sibling_scan rejected:\n" + "\n".join(
                                f"- {f.rule_id}: {f.remediation}" for f in blocking_scan
                            )
                            generator_input = (msg, "localization_rewrite")
                            continue

                    for row in sibling_scan:
                        cls = row.get("class", "")
                        if cls:
                            enrich_scan_suggestions(
                                self.backend, cls, sibling_scan, self.output_dir
                            )

                new_bug_locations: list[BugLocation] = []
                for loc in buggy_locations:
                    new_bug_locations.extend(self.backend.get_bug_loc_snippets_new(loc))

                unique_bug_locations: list[BugLocation] = []
                for loc in new_bug_locations:
                    if loc not in unique_bug_locations:
                        unique_bug_locations.append(loc)

                if new_bug_locations:
                    if config.enable_sympy_pipeline_v2:
                        ib_findings = lint_localization(
                            self.backend,
                            sibling_scan=sibling_scan,
                            bug_locations_raw=buggy_locations,
                            bug_locs=new_bug_locations,
                            issue_text=task.get_issue_statement(),
                            project_path=self.backend.project_path,
                        )
                        write_validation_report(self.output_dir, ib_findings)

                        if has_blocking_findings(ib_findings):
                            if self._localization_rewrite_count < 1:
                                self._localization_rewrite_count += 1
                                rewrite_msg = format_rewrite_message(ib_findings)
                                generator_input = (rewrite_msg, "localization_rewrite")
                                continue
                            logger.warning(
                                "Localization linter still blocking after rewrite; proceeding with warn."
                            )

                    bug_loc_file_processed = Path(
                        self.output_dir, "bug_locations_after_process.json"
                    )
                    json_obj = [loc.to_dict() for loc in new_bug_locations]
                    bug_loc_file_processed.write_text(json.dumps(json_obj, indent=2))

                    self.localization_context = LocalizationContext(
                        sibling_scan=sibling_scan,
                        bug_locations_raw=buggy_locations,
                        module_families=self._last_partial_artifact.get(
                            "module_families_detected", []
                        ),
                        round_no=round_no,
                        checklist_injected=config.enable_sympy_pipeline_v2,
                    )
                    artifact_path.write_text(
                        json.dumps(
                            {
                                **self._last_partial_artifact,
                                "localization_context": True,
                            },
                            indent=2,
                        )
                    )

                    logger.debug(
                        f"Bug location extracted successfully: {new_bug_locations}"
                    )
                    return new_bug_locations, search_msg_thread

                logger.debug(
                    "Failed to retrieve code from all bug locations. Asking search agent to re-generate response."
                )
                search_result_msg = (
                    "Failed to retrieve code from all bug locations. You may need to "
                    "check whether the arguments are correct or issue more search API calls."
                )
                generator_input = (search_result_msg, True)
                continue

            collated_search_res_str = ""
            for api_call in json_api_calls:
                func_name, func_args = parse_function_invocation(api_call)
                func_unwrapped = getattr(self.backend, func_name)
                while "__wrapped__" in func_unwrapped.__dict__:
                    func_unwrapped = func_unwrapped.__wrapped__
                arg_spec = inspect.getfullargspec(func_unwrapped)
                arg_names = arg_spec.args[1:]

                assert len(func_args) == len(
                    arg_names
                ), f"Number of argument is wrong in API call: {api_call}"

                kwargs = dict(zip(arg_names, func_args))
                function = getattr(self.backend, func_name)
                result_str, _, call_ok = function(**kwargs)
                collated_search_res_str += f"Result of {api_call}:\n\n"
                collated_search_res_str += result_str + "\n\n"
                self.add_tool_call_to_curr_layer(func_name, kwargs, call_ok)

            print_acr(collated_search_res_str, f"context retrieval round {round_no}")
            logger.debug(
                "Obtained search results from API invocation. Going into next retrieval round."
            )
            generator_input = (collated_search_res_str, False)

        logger.info("Too many rounds. Try writing patch anyway.")
        assert search_msg_thread is not None

        if self._last_partial_artifact and config.enable_sympy_pipeline_v2:
            Path(self.localization_artifact_path).write_text(
                json.dumps(self._last_partial_artifact, indent=2)
            )
            raw_locs = self._last_partial_artifact.get("bug_locations_raw", [])
            if raw_locs:
                partial: list[BugLocation] = []
                for loc in raw_locs:
                    partial.extend(self.backend.get_bug_loc_snippets_new(loc))
                if partial:
                    self.localization_context = LocalizationContext(
                        sibling_scan=self._last_partial_artifact.get("sibling_scan", []),
                        bug_locations_raw=raw_locs,
                        module_families=self._last_partial_artifact.get(
                            "module_families_detected", []
                        ),
                        round_no=round_no,
                    )
                    return partial, search_msg_thread

        return [], search_msg_thread

    def start_new_tool_call_layer(self):
        self.tool_call_layers.append([])

    def add_tool_call_to_curr_layer(
        self, func_name: str, args: dict[str, str], result: bool
    ):
        self.tool_call_layers[-1].append(
            {
                "func_name": func_name,
                "arguments": args,
                "call_ok": result,
            }
        )

    def dump_tool_call_layers_to_file(self):
        tool_call_file = Path(self.output_dir, "tool_call_layers.json")
        tool_call_file.write_text(json.dumps(self.tool_call_layers, indent=4))
