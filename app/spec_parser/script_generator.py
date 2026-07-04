"""Generate wide acceptance scripts via LLM or templates."""

from __future__ import annotations

import re

from app.agents.agent_common import InvalidLLMResponse
from app.data_structures import MessageThread
from app.model.gpt import common
from app.spec_parser.schema import RepoContext, ReproScriptArtifact, StructuredSpecification, TaskType
from app.spec_parser.script_prompts import SCRIPT_GENERATION_SYSTEM_PROMPT, format_script_user
from app.spec_parser.script_templates import render_minimal_script
from app.task import Task


def extract_script_from_llm_response(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        raise InvalidLLMResponse("No python code block in script generation response")
    return match.group(1).strip()


class ScriptGenerator:
    def __init__(self, task: Task, output_dir: str) -> None:
        self.task = task
        self.output_dir = output_dir

    def generate(
        self,
        spec: StructuredSpecification,
        repo_ctx: RepoContext,
        *,
        feedback: str | None = None,
        round_no: int = 1,
        use_llm: bool = True,
    ) -> tuple[ReproScriptArtifact, MessageThread]:
        filename = (
            "reproduce_issue.py"
            if spec.task_type == TaskType.BUG_FIX
            else "test_feature.py"
        )
        thread = MessageThread()
        content: str

        if use_llm:
            thread.add_system(SCRIPT_GENERATION_SYSTEM_PROMPT)
            thread.add_user(
                format_script_user(spec, repo_ctx, filename, feedback, round_no)
            )
            try:
                response, *_ = common.SELECTED_MODEL.call(
                    thread.to_msg(), response_format=None
                )
                thread.add_model(response)
                content = extract_script_from_llm_response(response)
            except (InvalidLLMResponse, Exception):
                content = render_minimal_script(spec)
        else:
            content = render_minimal_script(spec)

        artifact = ReproScriptArtifact(filename=filename, content=content)
        return artifact, thread
