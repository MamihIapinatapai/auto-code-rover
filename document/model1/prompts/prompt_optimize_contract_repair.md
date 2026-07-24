# Prompt：优化「修表 LLM / Contract Repair Agent」Prompt（v2）

> **用途**：喂给 Agent，在已知流水线与审查反馈格式的前提下，**重写/强化** `CONTRACT_REPAIR_*`，使修表模型能稳定消费表审+脚本审错误信息并只改允许槽位。  
> **前置结论**：首填 Prompt（`contract_fill_*`）与修表 Prompt **必须分离**；本任务只优化**修表**侧。  
> **输入资产**：  
> - 现有 [`contract_repair_prompts.py`](../../../app/spec_parser/contract_repair_prompts.py)  
> - 表审输出：[`contract_review_prompts.py`](../../../app/spec_parser/contract_review_prompts.py)（evidence_chain findings）  
> - 脚本审/SCC：`contract_patch`（§3.5.10）  
> - 统一包：`TableGenFeedback`（[prompt_design_dual_review_to_table_feedback.md](./prompt_design_dual_review_to_table_feedback.md)）  
> **产出**：可粘贴的 `CONTRACT_REPAIR_SYSTEM` + `USER` + Feedback 兼容说明 + sanitize 规则。

---

## 可复制 Prompt 正文（给执行 Agent）

```text
# Role
你是 Prompt 工程师 + 规格流水线设计师。任务：优化 BehaviorContract **修表 Agent** 的 System/User Prompt。

# 已知流水线（不可改目标）
首填(contract_fill, 可未落地) → BC机械 → 表审LLM(§3.5.8) → Renderer → 薄lint
→ SCC-M →（可选）脚本审LLM(§3.5.10) → 归一 TableGenFeedback →【修表Agent】→ BC → 重渲染

# 修表 Agent 定位
- 不是首填，不是写脚本，不是再审一遍
- 输入：Issue + 当前 Contract + TableGenFeedback（主）+ 可选原始表审/脚本审摘录
- 输出：items_patch（完整 expect 信封）+ unchanged 说明
- 只改：expect / fail_mode / expect_confidence（默认）；quote 仅 quote_drift 且有 Issue 子串
- 禁止：call_graph / recipe_id / layer；禁止 pytest；禁止发明字面量

# 审查错误信息格式（必须对齐消费）

## A. TableGenFeedback（首选入口）
fields: feedback_id, source(table_review|script_review|merged), blocking,
summary_for_filler, items[], filler_instructions
item fields: must_id, error_type, severity, what_is_wrong, evidence_digest[],
allowed_edits[], forbidden_edits[], suggested_patch{path,next_value_hint,oracle_kind_hint,rationale}, do_not[]

error_type 至少处理：
false_fail, off_must, weak_degraded, quote_drift, recipe_misaligned,
multi_item_inconsistency, script_contract_mismatch, invented_expect,
insufficient_evidence, render_error（→ 不改表）

## B. 表审原始 JSON（无 Feedback 时的降级入口）
verdict, item_findings[{must_id, issue, severity, claim, evidence_chain, fix, confidence}],
must_coverage_notes, self_checks
映射：issue→error_type；evidence_chain→evidence_digest；fix→suggested_patch 提示

## C. 脚本审 contract_patch（降级入口）
verdict, findings[{must_id, problem, evidence_chain, patch{action,path,next_value,rationale}}]
映射：action=mark_render_bug|noop_rerender → unchanged；update_expect → 可修表

# 优化目标
1. 按 error_type 给出**可执行修表配方**（写进 System），避免模型自由发挥
2. User 模板结构化：优先 Feedback；兼容原始表审/脚本审；标明优先级（blocking>warning；false_fail>others）
3. 强化抗幻觉：字面量 ∈ Issue ∪ evidence spans；否则 insufficient_grounding
4. 输出 schema 保持可 apply；增加 per-item `source_finding_ref` 便于审计
5. 明确「无 Feedback 且无原始审查」时的行为

# 你必须交付
1. 诊断：现有 CONTRACT_REPAIR_v1 的缺口（对照上述格式）
2. 按 error_type 的修表配方表
3. Feedback / 表审 / 脚本审 → 修表动作 映射表
4. **CONTRACT_REPAIR_SYSTEM v2 全文**
5. **CONTRACT_REPAIR_USER v2 全文**（占位符明确）
6. sanitize 规则清单
7. 两个 worked example 期望输出要点（false_fail；render_error）

# Quality Bar
- 禁止把修表 Prompt 写成又一次「自由填整表」
- 禁止主路径改脚本
- 配方必须绑定证据，不得「按常识修」
- System/User 可直接替换进 contract_repair_prompts.py
```

---

## 执行说明

Agent 应读取当前 `contract_repair_prompts.py`，按上文交付物重写该文件，并更新 `contract_repair_v1.md` 为 v2 说明。
