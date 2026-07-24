# P0-3 Prompt：TableGenFeedback + apply API

## 可复制 Prompt

```text
# Role
你是数据契约设计师。请冻结 TableGenFeedback 与 apply 层 API。

# 依据
prompt_design_dual_review_to_table_feedback.md；contract_repair_prompts.py（v2）；§3.5.8 输出；§3.5.10 contract_patch；修表只改 expect/fail_mode/expect_confidence。

# 任务
1. 冻结 TableGenFeedback JSON Schema（字段、枚举、必填）
2. merge_table_and_script_feedback() 规则（去重、severity、false_fail 优先）
3. apply_items_patch(contract, repair_json) 与 apply_contract_patch 白名单/回滚
4. render_error 不得改表的硬规则
5. Python 函数签名草案（模块路径建议）

# 质量
与修表 Prompt v2 字段名对齐；禁止 patch call_graph/recipe/layer（除非显式允许）。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐修表 v2 / §3.5.8/10 | PASS |
| 表优先 / render_error | PASS |
| 可编码 API | PASS |

**审查结论**：PASS。
