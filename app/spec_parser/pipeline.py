"""v2.2 vs v3.x spec parser pipeline selection helpers."""

from __future__ import annotations

from app import config

V2_PARSER_VERSION = "2.2.0"
V3_PARSER_VERSION = "3.1.0"


def is_v3_pipeline() -> bool:
    version = getattr(config, "spec_parser_version", V2_PARSER_VERSION)
    return version.startswith("3")


def effective_parser_version() -> str:
    return getattr(config, "spec_parser_version", V2_PARSER_VERSION)


def should_run_repo_enrichment(stop_after: str) -> bool:
    if stop_after == "extract":
        return False
    return bool(config.spec_parser_enable_repo_enrichment)


def configure_repo_enrichment(
    *,
    stop_after: str,
    no_repo_enrichment: bool = False,
    with_repo_enrichment: bool = False,
) -> None:
    """Resolve P2 (repo_enrichment) for the current run."""
    if no_repo_enrichment:
        config.spec_parser_enable_repo_enrichment = False
        return
    if with_repo_enrichment:
        config.spec_parser_enable_repo_enrichment = True
        return
    if is_v3_pipeline():
        config.spec_parser_enable_repo_enrichment = False
        return
    config.spec_parser_enable_repo_enrichment = stop_after not in ("extract",)


def apply_spec_parser_version(version: str | None) -> None:
    if version:
        config.spec_parser_version = version
