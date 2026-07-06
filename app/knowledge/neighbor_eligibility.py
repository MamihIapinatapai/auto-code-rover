"""
Neighbor eligibility hard-rule gate (HE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.search.search_backend import SearchBackend


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str
    fix_path: str = "CO_FIX"


def infer_layer(method_name: str) -> str:
    if method_name.startswith("_needs_"):
        return "policy"
    if method_name.startswith("_eval_is_"):
        return "property_eval"
    if method_name.startswith("_print_"):
        return "formatting"
    if method_name == "__new__":
        return "guard"
    return "unknown"


def _method_exists(backend: SearchBackend, class_name: str, method_name: str) -> bool:
    if not class_name or not method_name:
        return False
    if class_name in backend.class_func_index:
        if method_name in backend.class_func_index[class_name]:
            return True
    # fallback: search entire index
    for cls, funcs in backend.class_func_index.items():
        if method_name in funcs and (not class_name or cls == class_name):
            return True
    return False


def _is_ancestor_method(
    backend: SearchBackend, target_class: str, neighbor_class: str, neighbor_method: str
) -> bool:
    if neighbor_class == target_class:
        return False
    relations = backend.class_relation_index.get(target_class, [])
    if neighbor_class not in relations:
        return False
    return neighbor_method in backend.class_func_index.get(neighbor_class, {})


def check_neighbor_eligibility(
    backend: SearchBackend,
    *,
    target_class: str,
    target_method: str,
    neighbor_reference: str,
    neighbor_class: str | None = None,
    sibling_scan: list[dict] | None = None,
    anti_pattern_id: str | None = None,
    fix_path: str = "CO_FIX",
) -> EligibilityResult:
    """Hard-rule gate before L2 contract extraction."""
    if not neighbor_reference:
        return EligibilityResult(False, "empty neighbor_reference")

    neighbor_method = neighbor_reference
    n_class = neighbor_class or target_class

    if not _method_exists(backend, n_class, neighbor_method):
        return EligibilityResult(False, f"neighbor {n_class}.{neighbor_method} not in index")

    if fix_path == "Parent Inheritance" or fix_path == "PARENT_INHERITANCE":
        if not _is_ancestor_method(backend, target_class, n_class, neighbor_method):
            return EligibilityResult(
                False,
                f"{neighbor_method} is not an ancestor of {target_class}",
                fix_path="PARENT_INHERITANCE",
            )
        return EligibilityResult(True, "parent inheritance path", fix_path="PARENT_INHERITANCE")

    if n_class != target_class:
        return EligibilityResult(False, f"neighbor class {n_class} != target {target_class}")

    target_layer = infer_layer(target_method)
    neighbor_layer = infer_layer(neighbor_method)
    if target_layer != "unknown" and neighbor_layer != "unknown":
        if target_layer != neighbor_layer:
            if not (
                target_layer == "formatting"
                and neighbor_layer == "formatting"
                and target_method.startswith("_print_")
                and neighbor_method.startswith("_print_")
            ):
                return EligibilityResult(
                    False,
                    f"layer mismatch: {neighbor_layer} vs {target_layer}",
                )

    if sibling_scan and anti_pattern_id:
        target_aps = {
            r.get("anti_pattern_id")
            for r in sibling_scan
            if r.get("method_or_handler") == target_method
        }
        neighbor_aps = {
            r.get("anti_pattern_id")
            for r in sibling_scan
            if r.get("method_or_handler") == neighbor_method
        }
        if anti_pattern_id in target_aps and anti_pattern_id not in neighbor_aps:
            pass  # neighbor may still be semantic sibling by layer

    return EligibilityResult(True, "same class, layer aligned", fix_path=fix_path)


def suggest_semantic_siblings(
    backend: SearchBackend,
    class_name: str,
    target_method: str,
    *,
    fix_path: str = "CO_FIX",
    limit: int = 5,
) -> list[str]:
    """Mechanical ranking of candidate neighbor handlers."""
    if class_name not in backend.class_func_index:
        return []
    target_layer = infer_layer(target_method)
    candidates: list[tuple[int, str]] = []
    for method in backend.class_func_index[class_name]:
        if method == target_method:
            continue
        layer = infer_layer(method)
        score = 0
        if layer == target_layer:
            score += 3
        if method.startswith("_print_") and target_method.startswith("_print_"):
            score += 2
        if fix_path == "CO_FIX" and layer in ("formatting", "property_eval"):
            score += 1
        if score > 0:
            candidates.append((score, method))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return [m for _, m in candidates[:limit]]
