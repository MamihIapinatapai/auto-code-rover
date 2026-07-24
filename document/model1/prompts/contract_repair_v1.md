# BehaviorContract 修表 Agent Prompt — v2

> **Status**: Spec / 已合入代码  
> **元 Prompt（本次优化任务）**：[prompt_optimize_contract_repair.md](./prompt_optimize_contract_repair.md)  
> **代码**：[`app/spec_parser/contract_repair_prompts.py`](../../../app/spec_parser/contract_repair_prompts.py)  
> **首填（分离）**：[`app/spec_parser/contract_fill_prompts.py`](../../../app/spec_parser/contract_fill_prompts.py)（MVP v1，首次落地）

---

## 落地状态（2026-07-22）

| Prompt | 状态 | 文件 |
|--------|------|------|
| 表格**生成/首填** | **已落地 MVP v1** | `contract_fill_prompts.py` |
| 表格**修改/修表** | **已落地并优化 v2** | `contract_repair_prompts.py` |
| 表质量审视 | 已落地 v1 | `contract_review_prompts.py` |
| 脚本质量审视 SCC-L | 规格有，专用 Prompt 文件待补 | §3.5.10；可先走 SCC-M + Feedback |
| TableGenFeedback | Schema + 修表消费 + `build_minimal_feedback_from_table_review` | 修表模块内 |

---

## v2 相对 v1 的优化点

1. **按 error_type 的修表配方**（false_fail / weak_degraded / render_error…）写进 System  
2. **明确消费 TableGenFeedback**，并规定 Feedback 为空时如何映射表审 / 脚本审原文  
3. **优先级**：false_fail > quote_drift > off_must > … > insufficient_evidence  
4. **输出增加** `source_finding_ref` / `error_type_applied` / `feedback_driven_only`  
5. **User** 增加 filler_instructions、locked_fields、round_no  
6. **辅助函数** `build_minimal_feedback_from_table_review` 便于 Agent 归一入口  

---

## Agent 调用

```python
from app.spec_parser.contract_repair_prompts import (
    CONTRACT_REPAIR_SYSTEM,
    format_contract_repair_user,
    build_minimal_feedback_from_table_review,
)

# Prefer merged TableGenFeedback; or:
feedback = build_minimal_feedback_from_table_review(table_review_json)

user = format_contract_repair_user(
    issue_text=issue,
    contract_json=contract,
    table_gen_feedback=feedback,
    table_review_excerpt=table_review_json,  # fallback only
    script_review_excerpt=scc_patch_json,    # fallback only
    prefer_blocking_only=True,
    round_no=1,
)
```

---

## 与审查反馈的衔接

| 来源 | 修表如何用 |
|------|------------|
| TableGenFeedback.items | **主输入**；按 playbook 改 expect 等 |
| 表审 item_findings | Feedback 空时映射；或先 `build_minimal_feedback_from_table_review` |
| 脚本审 contract_patch | `update_expect`→可修表；`mark_render_bug`→unchanged |
| SCC-M 字面量缺失 | 通常 render_error，**不改表**，重渲染 |

---

## Worked examples（期望行为）

### false_fail
Feedback: quote「value should be None」，expect.value 为对象 → patch value=null，confidence=high。

### render_error
Feedback/patch: mark_render_bug → items_patch 空，unchanged reason=render_error。
