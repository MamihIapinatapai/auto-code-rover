"""Load static Library Recipe Cards."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app import config


def _cards_dir() -> Path:
    rel = getattr(config, "spec_parser_recipe_cards_path", "app/spec_parser/recipe_cards")
    root = Path(__file__).resolve().parents[2]
    path = Path(rel)
    if not path.is_absolute():
        path = root / rel
    return path


@lru_cache(maxsize=1)
def load_recipe_cards() -> dict[str, dict]:
    if not getattr(config, "spec_parser_enable_recipe_cards", True):
        return {}
    out: dict[str, dict] = {}
    d = _cards_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            cid = str(data.get("id") or p.stem)
            out[cid] = data
        except Exception:  # noqa: BLE001
            continue
    return out


def match_recipe_hints(issue_text: str, anchor_summary: str = "") -> list[dict]:
    blob = f"{issue_text}\n{anchor_summary}".lower()
    hits = []
    for cid, card in load_recipe_cards().items():
        key = cid.split(".")[0].lower()
        if key in blob or cid.lower() in blob:
            hits.append(card)
            continue
        for pat in card.get("required_patterns") or []:
            token = pat.split("(")[0].lower()
            if token and token in blob:
                hits.append(card)
                break
    return hits


def format_recipe_hints_for_prompt(cards: list[dict]) -> str:
    if not cards:
        return "(none)"
    lines = []
    for c in cards:
        lines.append(
            f"- id={c.get('id')} required={c.get('required_patterns')} "
            f"forbidden={c.get('forbidden_patterns')} hint={c.get('hint')}"
        )
    return "\n".join(lines)


def recipe_compliance(script: str, recipe_id: str | None) -> bool:
    if not recipe_id:
        return True
    cards = load_recipe_cards()
    card = cards.get(recipe_id)
    if not card:
        return True
    for pat in card.get("required_patterns") or []:
        if pat and pat not in script:
            return False
    for pat in card.get("forbidden_patterns") or []:
        # allow loose match: strip (...) placeholders
        needle = pat.replace("...", "")
        if needle and needle in script:
            return False
    return True
