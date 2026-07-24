# P0-2 Prompt：Agent 编排状态机

## 可复制 Prompt

```text
# Role
你是编排架构师。请为 Spec Parser 3.4.0 **契约路径**设计可编码状态机。

# 依据
§3.5.7 填表流水、§3.5.8 表审、§3.5.9 Renderer、§3.5.10 SCC、contract_repair、WP-ART；修槽预算共享 max_expect_retries=2。

# 任务
1. 列出状态节点（id、入口条件、产物文件名、决策链 D_* 节点）
2. 画出失败转移（BC fail / 表审 reject / SCC blocking / 修槽耗尽 → no_script）
3. 定义 consume_repair_budget() 伪代码（表审+修表+SCC 共用）
4. 标明何时走旧自由生成路径（非契约）——仅引用 P0-5，不展开

# 质量
每个状态必须有明确 next；禁止「再自由 regen 三轮脚本」。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 与 §3.5.7–3.5.10 一致 | PASS |
| 修槽共享预算 | PASS |
| 禁止润色脚本毕业 | PASS |
| 可编码 | PASS |

**审查结论**：PASS。
