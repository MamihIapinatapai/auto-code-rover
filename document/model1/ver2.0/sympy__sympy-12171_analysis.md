# sympy__sympy-12171 — Spec Parser v2.0 分析报告

> **Instance**：MCodePrinter 不支持 Derivative → GT 仅 `_print_Derivative`（Hold+D），**不含 Float**  
> **工件**：[`det/...`](../../../spec_parser_probe_v2_det/sympy__sympy-12171/) · [`scope_llm/...`](../../../spec_parser_probe_v2_scope_llm/sympy__sympy-12171/)

## Ground Truth 摘要

| 项 | 内容 |
|----|------|
| 目标文件 | `sympy/printing/mathematica.py` |
| 核心修复 | `_print_Derivative` → `Hold[D[..., ...]]`，复用 `doprint` join |
| 勿修 | `_print_Float`（继承 StrPrinter；改法会致 test_Pow 回归） |
| Hidden test | `test_Derivative` 缺 Hold；Float 相关 test 非 F2P |
| 失败范式 | A Issue scope creep + B 未对齐邻居 `_print_Integral` Hold 契约 |

---

## P1 Issue 抽取

**det / scope_llm（相同结构）**

- `repair_goals`：**两条** — `_print_Derivative` + `_print_Float`（Issue Reporter 草稿全收）。
- `symptom_goals`：Derivative 与 Float 打印格式。
- `fix_scope.in_scope`：含 `MCodePrinter._print_Float` — **超出 GT**。
- `negative_constraints`：「勿改其他 printer」— ✅ 但未 **out_of_scope Float**。
- AC：AC-001 Derivative、AC-002 Float、AC-003 Float 哨兵、AC-004 多元 Derivative。

**vs GT**：Derivative 方向正确；Float 为 **Reporter 噪声**，应降级为 out_of_scope 或删除。

---

## P2 静态 Enrichment

| 字段 | det | scope_llm |
|------|-----|-----------|
| analysis_scope 首位 | `physics/vector/printing.py` | **`mathematica.py`** |
| missing_handlers | Derivative, Float, MCodePrinter, _print_* | 同左 |
| neighbor_reference | null | null |
| visitors | missing_symbol, delegate_call | 同左 |

scope_llm ScopePlan 将 **`mathematica.py` 置顶** — 显著优于 det，直接对齐 GT 文件。

---

## P4 宽验收脚本

**两模式**

- 测试 `MCodePrinter().doprint(Derivative(...))` 与 `Float('1.0e-4')`。
- ✅ 在 buggy 代码上 AC-001/002 均 fail — 校准语义正确。
- ⚠️ Float AC **强化**了错误 repair_goal；无 `_print_Integral` 邻居对照 AC。
- 无 Pow 回归哨兵（GT 要求不改 Float 即保护 test_Pow）。

---

## P5 动态校准

| 模式 | calibration_passed | 轮次 |
|------|---------------------|------|
| det | ✅ | 1 |
| scope_llm | ✅ | 1 |

两模式均一次通过；`primary_failure_ac_id: AC-001`。

---

## P6 Search 注入契约

**det**（2087 B）

- repair_goals 含 Derivative + Float。
- in_scope 枚举 `_print_Derivative`, `_print_Float`。
- Execution Evidence 完整。

**scope_llm**（1849 B）

- 内容同构；in_scope 明确 **`MCodePrinter class in sympy/printing/mathematica.py`** — 文件锚点更清晰。
- search_api_hints 聚焦 mathematica 族。

---

## det vs scope_llm 差异

| 维度 | 差异 |
|------|------|
| 校准 | 相同 ✅ |
| P2 文件排序 | scope_llm **mathematica.py 首位**（关键差异） |
| 契约语义 | 相同 — 均含 Float |
| Search 误导风险 | 相同 — 可能 patch Float 致回归 |

---

## 对 Search → Patch 的帮助评估

| 问题 | 判断 |
|------|------|
| 是否指向 mathematica.py？ | scope_llm ✅✅；det ⚠️（在 scope 但非首位） |
| Derivative 方向？ | ✅ |
| Float scope？ | ❌ 两模式均 **扩大** 修复范围 |
| 邻居 Hold 契约？ | ❌ 未注入 |
| 宽脚本 buggy 失败？ | ✅ |

**综合评级**：scope_llm **B-**（文件排序优）；det **C+**。

---

## 改进建议

1. P1：Float 移入 `out_of_scope` + `reporter_drafts`；repair_goals 仅 Derivative。
2. P2：读取 `mathematica.py` 中 `_print_Integral` → `neighbor_reference: Hold+doprint`。
3. P4：增加 Pow 回归哨兵 AC；Derivative AC 断言含 `Hold[`。
4. P6：search_context 增加「Float 继承 StrPrinter，禁止 override」negative constraint。
