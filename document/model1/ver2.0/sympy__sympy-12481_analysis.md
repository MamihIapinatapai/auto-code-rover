# sympy__sympy-12481 — Spec Parser v2.0 分析报告

> **Instance**：Permutation 非_disjoint cycles → GT 仅改 `has_dups` 守卫，保留 Cycle 合成  
> **工件**：[`det/...`](../../../spec_parser_probe_v2_det/sympy__sympy-12481/) · [`scope_llm/...`](../../../spec_parser_probe_v2_scope_llm/sympy__sympy-12481/)

## Ground Truth 摘要

| 项 | 内容 |
|----|------|
| 目标文件 | `sympy/combinatorics/permutations.py` |
| 核心修复 | `if has_dups(temp) and not is_cycle: raise` — **最小守卫** |
| 勿改 | 下游 `Cycle()` 合成逻辑（「use Cycle(...)」为设计提示） |
| Hidden test | `Permutation([[0,1],[0,2]]) == Permutation(0,2,1)` |
| 失败范式 | B4 守卫 vs 核心逻辑未分离（过度重写 Cycle） |
| 历史 | ver1 **PASS** — 本题 spec_parser 语义方向最接近 GT |

---

## P1 Issue 抽取

**det / scope_llm**

- `repair_goals`：Permutation 构造函数接受非_disjoint cycles，左到右应用 — ✅ 语义正确。
- `architecture_hint`：`core_logic` + **`minimal_guard`** — ✅ 与 GT 一致。
- scope_llm `negative_constraints`：✅ 「勿改 disjoint cycles 行为」；det 融合后亦有类似约束。
- AC-001：`Permutation([[0,1],[0,1]]) == Permutation()` — ✅  
- AC-002：`Permutation([[0,1],[1,2]]) == Permutation(0,2,1)` — ✅ 泛化 hidden test。
- **无** 显式 `combinatorics/permutations.py` 路径（符合 P1 不发明路径规则）。

**vs GT**：P1 契约 **本题最佳** — 守卫最小化 + 负约束 + 泛化 AC 均到位。

---

## P2 静态 Enrichment — **严重偏差**

| 字段 | 值 |
|------|-----|
| target_resolution 首位 | **`sympy/simplify/hyperexpand.py`**（score 30.7，仅匹配 `__init__`） |
| 次位 | `plot.py`, `agca/modules.py`, `codegen.py`, `diffgeom.py` |
| **GT 文件** | `sympy/combinatorics/permutations.py` — **未出现在 analysis_scope** |
| missing_handlers | `Permutation`（符号级） |
| co_fix_candidates | **[]** |
| ScopePlan scope_llm | `used_llm: true`, **`validated: false`, `fallback: true`** |

**根因**：实体解析将 `Permutation` 与全局 `__init__` 方法泛化匹配；P2 deterministic 与 scope_llm fallback **文件列表完全相同** — ScopePlan LLM **未能纠正**。

P2 enrichment 从错误文件抽取 guard_raise 片段（hyperexpand ValueError 等），对 Search **高度误导**。

---

## P4 宽验收脚本

**两模式**（校准通过后）

- 测试 `Permutation([[0,1],[0,1]])` 与 `Permutation([[0,1],[1,2]])`。
- ✅ buggy 上 ValueError / 错误结果 — 校准通过。
- 脚本 **不依赖** P2 文件定位 — 语义 AC 自洽。

---

## P5 动态校准

| 模式 | calibration_passed | 轮次 | 备注 |
|------|---------------------|------|------|
| det | ✅ | 1 | 首次 run 曾因 `calibration_gate.py` 缺 `import re` 失败，修复后重跑成功 |
| scope_llm | ✅ | 1 | ScopePlan fallback |

---

## P6 Search 注入契约

**det / scope_llm**（~1700–1800 B）

- ✅ repair_goals、negative_constraints、Execution Evidence 完整。
- ✅ AC 覆盖 Issue 例 + 泛化例。
- Static hints：`search_api_hints` 来自 **错误文件** 的 Permutation 方法名。
- **无** `combinatorics/permutations.py` in_scope 路径。

**矛盾**：P1/P4/P6 语义契约 **正确**；P2 静态锚点 **错误** — Search 若依赖 `search_api_hints` / target_files 会偏离 GT。

---

## det vs scope_llm 差异

| 维度 | det | scope_llm |
|------|-----|-----------|
| 校准 | ✅ | ✅ |
| P2 文件列表 | hyperexpand 首位 | **相同**（fallback） |
| P1 契约 | 相同 | negative_constraints 略完整 |
| ScopePlan | 未用 LLM | LLM 计划 **校验失败** |

**本题 ScopePlan LLM 无收益** — 需改进符号索引而非 ScopePlan prompt。

---

## 对 Search → Patch 的帮助评估

| 问题 | 判断 |
|------|------|
| P1 语义 / AC？ | ✅✅ 最接近 GT |
| P2 文件定位？ | ❌❌ **严重错误** |
| 宽脚本 buggy 失败？ | ✅ |
| Search 会否找到 permutations.py？ | ⚠️ 依赖 SBFL / 文本检索；P2 hints **指向错误模块** |
| 负约束防过度修复？ | ✅ 有助于 Patch Review |

**综合评级**：语义契约 **A-**；P2 定位 **F**；整体 **C**（本题 ver1 曾 PASS，spec_parser 语义优势被 P2 抵消）。

---

## 改进建议

1. **P2 符号索引**：类名 `Permutation` 硬匹配 `combinatorics/permutations.py`；降低裸 `__init__` 权重。
2. **实体抽取**：过滤 issue_regex 误抽（`Calling`, `If`, `I` 等假 class）。
3. **ScopePlan 校验**：要求 `analysis_scope` 至少一个文件路径含 `combinatorics` 当 failure_anchor 含 Permutation。
4. **P6**：search_context 增加 `Failure Anchor Entities` → 推荐路径映射（来自 symbol_index 修正后）。
