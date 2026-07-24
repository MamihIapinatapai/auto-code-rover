# P0-1 Prompt：冻结 ver3.4.0 MVP 最小闭环边界

## 可复制 Prompt

```text
# Role
你是 AutoCodeRover Spec Parser 发布经理。请冻结 **ver3.4.0 Runtime MVP** 边界。

# 依据
- document/model1/spec_parser_ver3.4_design.md（§2 非目标、§3.5、WP-CF、O8/O9/O11）
- 硬约束：不注入 Harbor/solution/官方测；BC 机械资格门；修表与首填 Prompt 分离；SCC-M 默认开、表LLM/SCC-L 默认关

# 任务
输出一张「必做 / 默认关(有开关) / 本版不做」三栏表，覆盖：契约流水、审查、Renderer、SCC、Gate/ART、Recipe、DSL、Score、旧自由生成路径。
并给出：成功标准（对齐 §2.3）、明确禁止的范围膨胀、与 Phase A–D 的映射。

# 质量
禁止把 3.4.1 项混入必做；每个「默认关」必须给配置键名。
```

## 审查（对照设计文档）

| 检查项 | 结果 |
|--------|------|
| 硬约束 | PASS |
| 不扩全量 Contract-First | PASS（放入不做） |
| 与 O8/O9/O11 默认一致 | PASS |
| 可编码 | PASS（要求配置键） |

**审查结论**：PASS — 可执行。
