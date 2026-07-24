# P1-8 Prompt：Dual-State Lite 可执行规则

## 可复制 Prompt

```text
# Role
你是假失败防护工程师。请把 WP-DSL / BC-09 落成 **可执行规则表** DSL-01…。

# 依据
WP-DSL；cattrs/aiomonitor 案例；与表审 LLM、BC-09 的分工；无 solution.patch。

# 任务
1. 规则表：id、触发条件（脚本AST/契约/Issue关键词）、severity、处置（reject段/强制模板/记 false_fail_risk）
2. 明确与 §3.5.8 表审、BC-09 的先后：谁在渲染前/后
3. 不做什么（不做完整 patched-pass）
4. 单测夹具要点（V2）

# 质量
每条规则机器可判定或明确「仅 LLM」；禁止依赖官方测。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 WP-DSL | PASS |
| 无 solution | PASS |
| 可测 | PASS |

**审查结论**：PASS。
