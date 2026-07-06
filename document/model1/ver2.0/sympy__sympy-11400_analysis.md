# sympy__sympy-11400 — Spec Parser v2.0 分析报告

> **Instance**：ccode(sinc(x)) 不支持 → 需 Piecewise 委托 + `_print_Relational`  
> **工件**：[`spec_parser_probe_v2_det/sympy__sympy-11400/`](../../../spec_parser_probe_v2_det/sympy__sympy-11400/) · [`scope_llm/...`](../../../spec_parser_probe_v2_scope_llm/sympy__sympy-11400/)

## Ground Truth 摘要

| 项 | 内容 |
|----|------|
| 目标文件 | `sympy/printing/ccode.py` |
| 核心修复 | `_print_sinc` 构造 `Piecewise((sin(x)/x, Ne(x,0)), (1, True))` 并 `_print` 委托；**同步**新增 `_print_Relational`（`Ne`→`!=`） |
| Hidden test | `test_ccode_sinc` + `test_ccode_Relational` |
| 失败范式 | B 委托链缺失 + C Relational 前置依赖漏修 |

---

## P1 Issue 抽取

**det / scope_llm（相同）**

- `repair_goals`：仅「ccode(sinc(x)) 输出有效 C 表达式」，**未提及** `_print_Relational` 或 `Ne`/`Eq`。
- `issue_completeness.reporter_drafts`：含 `ccode(Piecewise(..., Ne(theta,0)...))` 线索，但 **未写入 `fix_scope.prerequisite`**。
- `architecture_hint`：`formatter` + `delegate_ast`，`neighbor_reference` 为空（应为 `_print_ITE` / `_print_Piecewise`）。
- `negative_constraints`：✅ 「勿假设 math.h 有 sinc」——与 GT 一致。

**vs GT**：P1 捕获 Issue 主诉，**遗漏 GT 双点修复中的 Relational 半部**。

---

## P2 静态 Enrichment

| 字段 | det | scope_llm |
|------|-----|-----------|
| analysis_scope 首位 | `ccode.py`（via sets/trig 等候选） | `ccode.py`（ScopePlan validated，排序提前） |
| missing_handlers | `ccode`, `sinc` | 同左 |
| missing `_print_Relational` | ❌ | ❌ |
| neighbor_reference | null | null |

P2 正确将 printing/ccode 纳入范围，但 **未从 Piecewise 示例推断 Relational 缺失 handler**。

---

## P4 宽验收脚本

**det** — `reproduce_issue.py`

- AC-001：断言输出不含 `Not supported` — ✅ 能测出 buggy 行为。
- AC-002：`lambdify(x, sinc(x), 'numpy')` — ❌ **ImportError**，脚本未跑到 assert。
- **无** AC-REL / `_print_Relational` / `Ne` 专项节。

**scope_llm** — `reproduce_issue.py`

- AC-001/002/003 + negative_constraint：均围绕「不含 Not supported / 不含 sinc() 调用」。
- **无** Relational 测试；AC 仍偏窄（与 ver1.1 reproducer 同类问题）。

---

## P5 动态校准

| 模式 | calibration_passed | calibration_error | 轮次 |
|------|---------------------|-------------------|------|
| det | ❌ false | ImportError | 3 |
| scope_llm | ✅ true | — | 1 |

det 的 `execution_evidence.json`：`per_criterion_results: []`，门禁在 ImportError 处终止。  
scope_llm：`primary_failure_ac_id: AC-001`，三 AC 在 buggy 上均为 `passed_on_buggy=False` — **校准语义正确**。

---

## P6 Search 注入契约（`search_context.txt`）

**det**（1257 B）

- 含 repair_goals、negative_constraints、Execution Evidence **为空**（校准失败）。
- **无** Relational、Ne、Piecewise 委托、prerequisite 字段。

**scope_llm**（1427 B）

- 含 Execution Evidence（AC-001..003 failed on buggy）。
- 仍 **无** `_print_Relational` / prerequisite；repair_goals 提到 Piecewise 但仍单点 sinc。

---

## det vs scope_llm 差异

| 维度 | 差异 |
|------|------|
| 校准 | scope_llm ✅；det ❌（numpy 依赖） |
| P2 文件序 | scope_llm 将 `ccode.py` 置顶（validated ScopePlan） |
| 契约内容 | **实质相同**，均缺 Relational |
| Search 可用性 | 仅 scope_llm 有 execution evidence |

---

## 对 Search → Patch 的帮助评估

| 问题 | 判断 |
|------|------|
| 是否指向正确模块？ | ⚠️ 部分 — ccode.py 在 scope / hints 中 |
| 是否指向完整 GT？ | ❌ 缺 Relational 共修 |
| 宽脚本能否在 buggy 上失败？ | scope_llm ✅；det ❌ |
| 会否误导 Search？ | ⚠️ 高 — Search 可能只补 `_print_sinc` 手写三元式，重复 ver1.1 失败 |

**综合评级**：scope_llm **C+**（可注入但契约不全）；det **F**（无 execution evidence）。

---

## 改进建议

1. P1：从 `reporter_drafts` 提取 `prerequisite: [_print_Relational]`。
2. P4：增加 AC-REL：`ccode(Eq(x,0))` / `ccode(Ne(x,0))` 不含 unsupported。
3. P4 prompt：禁止 numpy lambdify；数值等价用 sympy subs。
4. P2 printing 规则：`delegate_call` visitor 检测 Piecewise 条件中的 Relational 节点。
