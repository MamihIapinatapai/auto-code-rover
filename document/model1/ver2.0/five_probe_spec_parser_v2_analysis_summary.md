# Spec Parser v2.0 五探针分析总表

> **分析依据**：本地 `spec_parser_probe_v2_det/` 与 `spec_parser_probe_v2_scope_llm/` 实际工件  
> **分析框架**：P1 Issue 抽取 → P2 静态 enrichment → P4 宽脚本 → P5 校准 → P6 Search 注入契约  
> **Ground Truth**：SWE-bench 人类补丁 + 跨案知识库（不可见 hidden test 前提下的人工对照）

---

## 1. 执行摘要

v2.1 Spec Parser 在五探针上 **3/5（det）与 5/5（scope_llm）** 通过动态校准。ScopePlan LLM 的主要增益来自 **11400、11897**：在 P2 分析范围排序与脚本可运行性上帮助 det 模式未闭合的环节。

**仍未闭合的系统性缺口**（两模式共有）：

1. **Issue 范围 ⊂ GT 范围**：11400 缺 `_print_Relational`；11897 锚定 exp/fraction 症状而非 `_needs_mul_brackets`；12454 缺 hessenberg 共修；12171 含 Float scope creep。
2. **P2 实体→文件解析偏差**：12481 将 `Permutation` 解析到 `hyperexpand.py` / `plot.py`，而非 `combinatorics/permutations.py`。
3. **宽脚本仍偏窄或偏错**：11400 det 脚本 `lambdify(..., 'numpy')` 致 ImportError；11897 det 脚本 SyntaxError（`__future__` 位置 + 假 `get_sympy`）；12454 两模式均未测 hessenberg。

**对 Search 的总体判断**：scope_llm 在五题上均产出可用的 `search_context.txt` + 校准证据，**比 det 更适合作为下游输入**；但 **仅 12481 的 P2 定位明显误导 Search**，11400/11897/12454 的契约缺口仍可能导致 Search 走偏（与 ver1.1 失败签名同类）。

---

## 2. 校准与 P2 模式对比

| Instance | GT 核心修复 | det 校准 | scope_llm 校准 | det 轮次 | scope_llm 轮次 | ScopePlan |
|----------|------------|----------|----------------|----------|----------------|-----------|
| **11400** | `_print_sinc` 委托 Piecewise + `_print_Relational` | ❌ ImportError | ✅ | 3 | 1 | validated |
| **11897** | `_needs_mul_brackets` 对 Piecewise 返回 True | ❌ SyntaxError | ✅ | 3 | 1 | validated |
| **12171** | 仅 `_print_Derivative`（Hold+D），不含 Float | ✅ | ✅ | 1 | 1 | validated |
| **12454** | `is_upper` + `_eval_is_upper_hessenberg` clamp | ✅ | ✅ | 2 | 1 | validated |
| **12481** | `has_dups` 守卫最小改，保留 Cycle 合成 | ✅ | ✅ | 1 | 1 | fallback（LLM 计划未过校验） |

**det 失败根因（工程层，非语义层）**：

- **11400**：`reproduce_issue.py` AC-002 使用 `lambdify(x, sinc(x), 'numpy')`，环境无 numpy → `ImportError`，`per_criterion_results` 为空。
- **11897**：脚本在 import 块中插入 `from __future__ import print_function`（非法位置）并引用不存在的 `get_sympy` → `SyntaxError`，preflight 通过但 sandbox 失败。

**scope_llm 增益机制**：

- P2 将 `ccode.py` / `latex.py` 排到分析范围首位（11400、11897），有利于 search_api_hints 聚焦 printing 族。
- 11897 scope_llm 额外纳入 `exponential.py`，替换 det 的 `core/symbol.py`。
- 12171 scope_llm 将 `mathematica.py` 置顶（det 为 `physics/vector/printing.py` 首位）——**更贴近 GT**。
- 12481 ScopePlan LLM **校验失败并 fallback**，两模式 P2 文件列表相同，问题未解。

---

## 3. 分阶段达标率（人工审查 + probe_review 指标）

| 阶段 | 11400 | 11897 | 12171 | 12454 | 12481 |
|------|-------|-------|-------|-------|-------|
| **P1 契约完整性** | ⚠️ 仅 sinc，无 Relational/prerequisite | ⚠️ 症状层 repair_goals | ⚠️ 含 Float | ⚠️ 无 hessenberg co_fix | ✅ 语义对，缺文件路径 |
| **P2 静态 enrichment** | ⚠️ 命中 ccode.py，无 `_print_Relational` | ⚠️ latex.py 在 scope，无 bracket 层 | ⚠️ mathematica 在 scope | ✅ matrices.py 首位；co_fix 过宽且无 hessenberg | ❌ 目标文件全错 |
| **P4/P5 脚本+校准** | det ❌ / llm ✅（弱 AC） | det ❌ / llm ✅（未测 Piecewise） | ✅ 两模式 | ✅ 两模式（缺 hessenberg） | ✅ 两模式 |
| **P6 Search 契约** | ⚠️ 无 Relational/Ne 契约 | ⚠️ 症状/修复未分离到 GT 层 | ⚠️ Float 仍在 repair_goals | ⚠️ co_fix 列表噪声大 | ⚠️ 缺 permutations.py 路径 |

图例：✅ 基本达标 · ⚠️ 部分达标 · ❌ 明显偏离 GT

---

## 4. 逐题一句话结论

| 探针 | det | scope_llm | Search 就绪度 |
|------|-----|-----------|---------------|
| **11400** | 脚本工程失败；契约缺 Relational | 校准通过但 AC 仍弱（仅「不含 Not supported」） | scope_llm **勉强可用**；需补 Relational AC |
| **11897** | 脚本语法失败；P1 锚定 exp/log | 校准通过；仍测 exp/fraction 非 Piecewise 括号 | scope_llm **部分可用**；P1/P4 需 bracket 层 |
| **12171** | 校准通过；Float scope creep | 同上；`mathematica.py` 排序更好 | 两模式 **可用但需收窄 Float** |
| **12454** | 校准通过；缺 hessenberg | 同上；ScopePlan 1 轮收敛 | 两模式 **可用但 sibling 不全** |
| **12481** | 校准通过；P2 文件错位 | 同上；ScopePlan fallback | 契约语义 **较好**；P2 **严重误导 Search** |

---

## 5. 优先改进项（按 Search 影响排序）

1. **P2 符号索引**：类名 `Permutation` 应优先匹配 `sympy/combinatorics/permutations.py`，抑制 `__init__` 泛化命中。
2. **P1 模板 + P3 融合**：11400 从 Issue Piecewise 示例推断 `prerequisite: _print_Relational`；11897 区分 symptom（exp/fraction）与 repair（`_needs_mul_brackets`）。
3. **P4 脚本 prompt**：禁止 AC 中使用 numpy lambdify；禁止 `__future__` 出现在 docstring 之后。
4. **P4 宽验收**：12454 增加 `is_upper_hessenberg` AC；11897 增加 `latex(Mul(Piecewise(...)))` 括号 AC。
5. **P2 co_fix 规则**：矩阵族 `loop_bound` visitor 应对 `_eval_is_upper_hessenberg` 与 `is_upper` 成对输出。

---

## 6. 详细报告

- [sympy__sympy-11400_analysis.md](./sympy__sympy-11400_analysis.md)
- [sympy__sympy-11897_analysis.md](./sympy__sympy-11897_analysis.md)
- [sympy__sympy-12171_analysis.md](./sympy__sympy-12171_analysis.md)
- [sympy__sympy-12454_analysis.md](./sympy__sympy-12454_analysis.md)
- [sympy__sympy-12481_analysis.md](./sympy__sympy-12481_analysis.md)
