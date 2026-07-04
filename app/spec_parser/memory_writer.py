"""Persist spec parser artifacts to the task output directory."""

from __future__ import annotations

from pathlib import Path

from app.data_structures import MessageThread
from app.infrastructure.shared_memory import SharedMemoryStore
from app.spec_parser.schema import StructuredSpecification


def save_thread(output_dir: Path | str, thread: MessageThread, name: str) -> Path:
    path = Path(output_dir) / f"spec_parser_{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    thread.save_to_file(path)
    return path


def save_repro_script(output_dir: Path | str, filename: str, content: str) -> Path:
    path = Path(output_dir) / filename
    path.write_text(content)
    return path


def save_all_artifacts(
    output_dir: Path | str, spec: StructuredSpecification
) -> None:
    SharedMemoryStore.write_sidecar_artifacts(output_dir, spec)
    if spec.repro_script is not None:
        save_repro_script(output_dir, spec.repro_script.filename, spec.repro_script.content)
