"""Build repository context for spec parsing."""

from __future__ import annotations

from pathlib import Path

from app.spec_parser.schema import RepoContext
from app.task import Task


def build_repo_context(task: Task) -> RepoContext:
    project = Path(task.project_path)
    repo_name = getattr(task, "repo", None) or project.name
    conda_env = getattr(task, "env_name", None)

    test_framework = "pytest"
    sample_test_files: list[str] = []
    for pattern in ("test_*.py", "*_test.py"):
        for p in sorted(project.rglob(pattern))[:8]:
            rel = str(p.relative_to(project))
            if "test" in rel.lower():
                sample_test_files.append(rel)

    top_level: list[str] = []
    for child in project.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            top_level.append(child.name)

    excerpt = ""
    if sample_test_files:
        sample_path = project / sample_test_files[0]
        if sample_path.is_file():
            lines = sample_path.read_text(errors="replace").splitlines()[:40]
            excerpt = "\n".join(lines)

    return RepoContext(
        repo_name=str(repo_name),
        python_version=None,
        conda_env=conda_env,
        test_framework=test_framework,
        sample_test_files=sample_test_files[:5],
        top_level_packages=top_level[:5] or ["sympy"],
        sample_test_excerpt=excerpt,
    )
