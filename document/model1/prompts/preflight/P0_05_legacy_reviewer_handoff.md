# P0-5 Prompt：旧 script_reviewer / 自由生成路径交接

## 可复制 Prompt

```text
# Role
你是迁移架构师。请定义 3.4.0 契约路径与旧脚本生成/审视路径的交接规则。

# 依据
O8（仅 stub+开关走契约）；§3.5.10「旧审视降级或旁路」；硬约束不以审视完美毕业；WP-S1 stub 触发。

# 任务
1. 决策表：何时走 contract_path vs legacy_path
2. 契约路径上旧 ScriptReviewer 的行为：skip / warn-only / 禁止改脚本
3. legacy 路径保留哪些 3.3.1 能力
4. 配置键与互斥规则（不能双写两份 accepted script）
5. 迁移风险与回滚开关

# 质量
禁止两套路径同时 persist accepted；契约路径禁止「LLM 润色 pytest 毕业」。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 O8 / §3.5.10 | PASS |
| ART 单口径 | PASS |
| 可配置 | PASS |

**审查结论**：PASS。
