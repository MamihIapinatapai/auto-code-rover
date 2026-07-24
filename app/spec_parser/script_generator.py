"""Generate wide acceptance scripts via LLM or templates."""

from __future__ import annotations

import re

from app import config
from app.agents.agent_common import InvalidLLMResponse
from app.data_structures import MessageThread
from app.model.gpt import common
from app.spec_parser.schema import RepoContext, ReproScriptArtifact, StructuredSpecification, TaskType
from app.spec_parser.script_prompts import SCRIPT_GENERATION_SYSTEM_PROMPT, format_script_user
from app.spec_parser.script_prompts_v3 import (
    format_script_user_v3,
    select_script_system_prompt,
)
from app.spec_parser.script_templates import render_minimal_script, wrap_generated_body
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
        issue_text: str = "",
        feedback: str | None = None,
        round_no: int = 1,
        use_llm: bool = True,
        script_anchor_block: str = "",
    ) -> tuple[ReproScriptArtifact, MessageThread]:
        filename = (
            "reproduce_issue.py"
            if spec.task_type == TaskType.BUG_FIX
            else "test_feature.py"
        )
        thread = MessageThread()
        content: str

        if use_llm:
            if config.spec_parser_use_v3_prompts:
                thread.add_system(select_script_system_prompt(spec.task_type))
                thread.add_user(
                    format_script_user_v3(
                        spec,
                        repo_ctx,
                        issue_text,
                        filename,
                        feedback,
                        round_no,
                        script_anchor_block=script_anchor_block,
                    )
                )
            else:
                thread.add_system(SCRIPT_GENERATION_SYSTEM_PROMPT)
                thread.add_user(
                    format_script_user(spec, repo_ctx, filename, feedback, round_no)
                )
            try:
                response, *_ = common.SELECTED_MODEL.call(
                    thread.to_msg(), response_format=None
                )
                thread.add_model(response)
                body = extract_script_from_llm_response(response)
                if config.spec_parser_use_v3_prompts:
                    content = wrap_generated_body(body, summary=spec.summary)
                else:
                    content = body
            except (InvalidLLMResponse, Exception):
                content = render_minimal_script(spec)
        else:
            content = render_minimal_script(spec)

        artifact = ReproScriptArtifact(filename=filename, content=content)
        return artifact, thread
