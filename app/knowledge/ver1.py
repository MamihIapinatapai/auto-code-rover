# TODO (ver1): Dynamic semantic injection for SymPy library to prevent math logical errors
"""ver1 branding constants for AutoCodeRover semantic injection."""

ACR_VERSION = "ver1"
ACR_LOG_PREFIX = "[AutoCodeRover-ver1]"


def ver1_prompt_header(phase: str) -> str:
    return (
        f"=== {ACR_LOG_PREFIX} Semantic Injection ({ACR_VERSION}, phase={phase}) ===\n"
        "The following domain rules are authoritative over Issue draft code."
    )


def acr_version_metadata() -> dict:
    return {
        "version": ACR_VERSION,
        "semantic_injection": True,
        "log_prefix": ACR_LOG_PREFIX,
    }
