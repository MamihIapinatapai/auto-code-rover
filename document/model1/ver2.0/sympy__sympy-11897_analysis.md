# sympy__sympy-11897 — Spec Parser v2.0 分析报告

> **Instance**：LaTeX 与 pretty 打印不一致 → GT 仅改 `_needs_mul_brackets`（Piecewise 括号）  
> **工件**：[`det/...`](../../../spec_parser_probe_v2_det/sympy__sympy-11897/) · [`scope_llm/...`](../../../spec_parser_probe_v2_scope_llm/sympy__sympy-11897/)

## Ground Truth 摘要

| 项 | 内容 |
|----|------|
| 目标文件 | `sympy/printing/latex.py` |
| 核心修复 | `_needs_mul_brackets` 中对 `expr.is_Piecewise` 返回 `True` |
| Hidden test | `test_latex_Piecewise`（`Mul` × `Piecewise` 需括号） |
| 勿修 | `_print_Mul` / fraction 层（易触发 RecursionError） |
| 失败范式 | A Issue 锚定错位（exp/fraction 症状 vs bracket 决策层） |

---

## P1 Issue 抽取

**det / scope_llm（结构相似）**

- ✅ `symptom_goals` vs `repair_goals` 有分层意识（bracket 层在 review 中部分认可）。
- `repair_goals`：锚定 `exp(-x)*log(x)`、`1/(x+y)/2` 的 LaTeX 输出 — **症状层**，非 `_needs_mul_brackets`。
- `out_of_scope`：**未**明确排除 reporter 草稿中的 `_print_Mul` formatter 路径。
- `failure_anchor`：`LaTeX printer`, `exp`, `log`, `Pow`, `Mul` — 未含 `Piecewise` / `_needs_mul_brackets`。

**vs GT**：P1 完整复述 Issue，**未识别 hidden test 的真实修复层**。

---

## P2 静态 Enrichment

| 字段 | det | scope_llm |
|------|-----|-----------|
| analysis_scope 首位 | `sets.py` | **`latex.py`**（ScopePlan validated） |
| 差异文件 | 含 `core/symbol.py` | 含 `functions/elementary/exponential.py` |
| visitors | missing_symbol, delegate_call | + **guard_raise** |
| bracket 层信号 | ❌ | ❌ |

scope_llm 将 `latex.py` 置顶 — **对 Search 更友好**；两模式均未产出 `_needs_mul_brackets` missing_handler。

---

## P4 宽验收脚本

**det** — 严重工程缺陷

```python
# reproduce_issue.py L26-29（非法结构）
from __future__ import print_function  # 出现在普通 import 之后
from get_sympy import path_hack          # 模块不存在
```

- 测试 exp(-x)*log(x)、1/(x+y)/2、与 pretty 一致性 — **全是 Issue 症状**。
- **无** `Piecewise` / `Mul` 括号 AC。

**scope_llm**

- 结构合法，同样测 exp/fraction/pretty 一致性。
- **仍无** `latex(x * Piecewise(...))` 括号断言。

---

## P5 动态校准

| 模式 | calibration_passed | calibration_error | 轮次 |
|------|---------------------|-------------------|------|
| det | ❌ | SyntaxError | 3 |
| scope_llm | ✅ | — | 1 |

det：`preflight_passed: true` 但 sandbox SyntaxError — 说明 preflight 未捕获 `__future__` 位置违规（M7 可加强）。  
scope_llm：三 AC 在 buggy 上 fail — **校准有效**，但测的是症状非 GT。

---

## P6 Search 注入契约

**det / scope_llm** 均含：

- 清晰 symptom/repair 分层叙述。
- repair_goals 仍指向 exp/log/fraction。
- Static hints：`Mul, Pow, exp, log` — **无 Piecewise / _needs_mul_brackets**。
- scope_llm 有完整 Execution Evidence。

---

## det vs scope_llm 差异

| 维度 | det | scope_llm |
|------|-----|-----------|
| 校准 | ❌ SyntaxError | ✅ |
| P2 首位文件 | sets.py | **latex.py** |
| scope 差异 | symbol.py | exponential.py |
| 脚本 | 语法错误 | 可运行 |
| 语义契约 | 相同偏差 | 相同偏差 |

**ScopePlan LLM 主要解决「能跑」与「latex.py 优先」，未解决「测对层」**。

---

## 对 Search → Patch 的帮助评估

| 问题 | 判断 |
|------|------|
| 是否指向 latex.py？ | scope_llm ✅；det ⚠️（latex 在 scope 但非首位） |
| 是否指向 GT 方法？ | ❌ 两模式均未提 `_needs_mul_brackets` |
| 脚本会否引导错层 Patch？ | ⚠️ **高** — 与 ver1.1 同样锚定 `_print_Mul` 风险 |
| 校准证据可信度 | scope_llm 有效但 **测错 bug** |

**综合评级**：scope_llm **C**；det **F**。

---

## 改进建议

1. P1：`symptom_goals` 保留 Issue 示例；`repair_goals` 改为「`_needs_mul_brackets` 对 Piecewise 返回 True」。
2. P1 `out_of_scope`：显式禁止改 `_print_Mul` / `_print_Pow`。
3. P4：AC 改为 `latex(Mul(x, Piecewise((1, x>0), (0, True))))` 含 `\left(`。
4. P2：printing 族规则扫描 `_needs_*_brackets` 与 `is_Piecewise` 引用。
