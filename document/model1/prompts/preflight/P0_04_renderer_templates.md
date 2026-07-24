# P0-4 Prompt：Renderer 模板表

## 可复制 Prompt

```text
# Role
你是测试代码生成编译器设计师。请把 §3.5.9 伪代码落成 **layer × oracle_kind 模板规格表**。

# 依据
§3.5.5 oracle_kind；§3.5.9；§3.5.10 SCC-01…07（必须能对照断言/调用锚点）；禁止 LLM 改骨架。

# 任务
对 layer∈{lib,cli,web,async} 与主要 oracle_kind 给出：
- 函数/锚注释命名（test_ac_{must_id} / AC 注释）
- arrange 段如何展开 call_graph + recipe
- assert/raises/http/stdout 代码形态
- harness 壳（asyncio.run / TestClient / CliRunner）
- 哪些 SCC 规则依赖哪些锚点

给至少 1 个完整 lib+equality 与 1 个 async+equality 示例骨架。

# 质量
模板必须能被 SCC-M 静态检查；web/cli 含 entrypoint 字符串落盘。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 §3.5.5/9/10 | PASS |
| 支持 SCC | PASS |
| 不引入自由生成 | PASS |

**审查结论**：PASS。
