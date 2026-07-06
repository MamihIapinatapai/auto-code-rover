# sympy__sympy-12454 — Spec Parser v2.0 分析报告

> **Instance**：`Matrix.is_upper()` 高矩阵 IndexError → GT 同步修 `is_upper` + `_eval_is_upper_hessenberg`  
> **工件**：[`det/...`](../../../spec_parser_probe_v2_det/sympy__sympy-12454/) · [`scope_llm/...`](../../../spec_parser_probe_v2_scope_llm/sympy__sympy-12454/)

## Ground Truth 摘要

| 项 | 内容 |
|----|------|
| 目标文件 | `sympy/matrices/matrices.py` |
| 核心修复 | `is_upper` 与 `_eval_is_upper_hessenberg` 内层循环上界 clamp 为 `min(i, self.cols)` 或 `range(..., self.cols)` |
| Bug class | AP-MATRIX-DIM-UNCLAMPED（兄弟方法同构越界） |
| Hidden test | `test_is_upper` + **`test_hessenberg`** |
| 失败范式 | C Bug class 泛化不足（Issue 仅提 is_upper） |

---

## P1 Issue 抽取

**det / scope_llm**

- `repair_goals`：修复 `is_upper()` 高矩阵 IndexError + 返回正确布尔值 — ✅ 对准 Issue。
- `architecture_hint`：`core_logic` + **`dimension_clamp`** — ✅ 模式识别正确。
- `fix_scope.co_fix_required`：**空**（search_context 融合后膨胀，见 P6）。
- **未**显式列出 `hessenberg` / `_eval_is_upper_hessenberg`。

**vs GT**：Issue 隧道视野复现；P1 未从矩阵族规则推断兄弟共修。

---

## P2 静态 Enrichment

| 字段 | det | scope_llm |
|------|-----|-----------|
| analysis_scope 首位 | **`matrices.py`** | **`matrices.py`** |
| visitors | missing_symbol, **loop_bound**, guard_raise | 同左 |
| co_fix_candidates | 24 项（`_LDLdecomposition`, `eye`, `zeros`…） | 同左（fusion 后写入 search_context） |
| `_eval_is_upper_hessenberg` | ❌ 不在 co_fix | ❌ |
| ForLoopVisitor clamp | ⚠️ 检测到 loop_bound 但未绑定 hessenberg | 同左 |

P2 **正确锁定 matrices.py** 且启用 `loop_bound` visitor — 基础设施到位，但 **共修候选未精确到 GT 兄弟方法**；反而 fusion 注入大量无关 co_fix（decomposition 系）。

---

## P4 宽验收脚本

**两模式**

- AC-001..006：全为 `is_upper` 变体（zeros(4,2)、eye(3)、zeros(2,4) 等）。
- ✅ buggy 代码上六 AC 均 fail（det 第 2 轮通过校准）。
- ❌ **无** `is_upper_hessenberg` / `zeros(5,2).is_upper_hessenberg` 测试。

与 ver1.1 相同：**脚本过窄导致 hessenberg 假阴**。

---

## P5 动态校准

| 模式 | calibration_passed | 轮次 |
|------|---------------------|------|
| det | ✅ | **2** |
| scope_llm | ✅ | **1** |

scope_llm ScopePlan validated，一轮收敛；det 需两轮 script 迭代。

---

## P6 Search 注入契约

**det**（2491 B）— 节选 Fix Scope：

```
in_scope: sympy/matrices/matrices.py, is_upper, py
co_fix_required: _LDLdecomposition, _cholesky, ... (24 methods)
out_of_scope: sympy/matrices/dense.py
```

- ✅ `matrices.py` + `is_upper` 锚点明确。
- ✅ `architecture_hint: dimension_clamp`。
- ❌ co_fix 列表 **噪声大**且 **缺 hessenberg**。
- Execution Evidence：六 AC 均 failed on buggy。

**scope_llm**（2319 B）：结构相同，co_fix 略短，仍无 hessenberg。

---

## det vs scope_llm 差异

| 维度 | det | scope_llm |
|------|-----|-----------|
| 校准 | ✅（2 轮） | ✅（1 轮） |
| P2 scope 文件 | 相同 | 相同 |
| search_context | 更长（2491 B） | 略短 |
| 语义缺口 | 相同 — 无 hessenberg | 相同 |

**ScopePlan LLM 仅改善收敛速度，未改善共修完整性**。

---

## 对 Search → Patch 的帮助评估

| 问题 | 判断 |
|------|------|
| 是否指向 matrices.py / is_upper？ | ✅✅ |
| 是否覆盖 GT 双点？ | ❌ hessenberg 遗漏 |
| dimension_clamp 提示？ | ✅ 有助于 Search 理解模式 |
| co_fix 噪声？ | ⚠️ 可能分散 Search 注意力 |
| 宽脚本 buggy 失败？ | ✅ 但 **仅测 is_upper** |

**综合评级**：两模式 **B-**（主文件正确，兄弟齐修未闭合 — 与 ver1/ver1.1 同签名）。

---

## 改进建议

1. P2 `loop_bound` visitor：对 `for j in range(i)` 模式成对报告 `is_upper` + `_eval_is_upper_hessenberg`。
2. P4：增加 AC-HESS：`zeros(5,2).is_upper_hessenberg` 不抛 IndexError。
3. P3 fusion：co_fix 白名单过滤 — 仅保留同 loop_bound 反模式方法，剔除 decomposition 系。
4. P1：从 Issue「upper triangular」+ 矩阵 API 推断 hessenberg 为 should co_fix。
