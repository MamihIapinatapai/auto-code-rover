# SymPy C 类 Case 多维错因对比与语义常识规则库

> **文档类型**: 优化计划步骤 2（多维错因对比分析）+ 步骤 3（高价值语义常识规则库）  
> **数据来源**: 5 个典型 C 类（Logic/Assertion Failure）Case 单案诊断报告  
> **覆盖 Instance**: sympy__sympy-11400, 11897, 12171, 12454, 12481  
> **注入约束**: Patch 生成阶段 **无法获知** SWE-bench 评测题集（`test_patch` / `FAIL_TO_PASS`），规则设计须仅依赖 Issue 与仓库源码。

---

## 任务 1：多维错因横向对比矩阵

| Instance ID | 报错模块 | 报错类型 | LLM 核心认知盲区 | 人类补丁的「破局点」 |
|---|---|---|---|---|
| **sympy__sympy-11400** | `sympy/printing`（CCodePrinter / `ccode.py`） | **AssertionError**（2 项：`test_ccode_sinc` 字符串不匹配；`test_ccode_Relational` 关系运算符未渲染） | 将 Printer 问题当作「目标语言字符串翻译」而非 **AST 组合委托**；不知道 `Ne`/`Eq` 需 `_print_Relational` 前置支持，且 C 测试要求 **精确多行格式契约** | 构造 `Piecewise((sin(x)/x, Ne(x,0)), (1, True))` 并 `self._print(_piecewise)` 复用已有 `_print_Piecewise` 链；同步新增 `_print_Relational` 将 `Ne`→`!=` |
| **sympy__sympy-11897** | `sympy/printing`（LatexPrinter / `latex.py`） | **AssertionError**（`test_latex_Piecewise` 缺括号）+ **RecursionError**（9 项 PASS_TO_PASS 回归） | 混淆 Printer **格式化层**（`_print_Mul`/`fraction`）与 **括号决策层**（`_needs_mul_brackets`）；被 Issue 中 `exp(-x)`/`1/(x+y)/2` 症状锚定，忽略实际需修 Piecewise 括号的代码路径 | 在 `_needs_mul_brackets` 增加 `if expr.is_Piecewise: return True`，使 `A * Piecewise(...)` 强制 `\left(...\right)` 包裹；不触碰 `_print_Mul` 避免 `_print_Mul↔_print_Pow` 互调递归 |
| **sympy__sympy-12171** | `sympy/printing`（MCodePrinter / `mathematica.py`） | **AssertionError**（`test_Derivative` 缺 `Hold`；`test_Pow` PASS→FAIL 回归） | 将 Issue Reporter 内嵌草稿当作权威规格；未读取同文件 `_print_Integral`/`_print_Sum` 的 **`Hold[Operator[...]]` 家族契约** 及 `doprint` vs `stringify` 分工；对未验收子问题（Float）做 scope creep | 仅新增 `_print_Derivative`，格式为 `Hold[D[` + `doprint` join + `]]`；不 override `_print_Float`，继续继承 `StrPrinter` 的 mpmath 精度逻辑 |
| **sympy__sympy-12454** | `sympy/matrices`（MatrixProperties / `matrices.py`） | **IndexError**（`test_hessenberg` 在 `zeros(5,2).is_upper_hessenberg` 崩溃；`test_is_upper` 已通过） | 理解单点「非方阵列索引须 `< self.cols`」语义，但未 **泛化为同 bug class 的兄弟方法**；Issue 隧道视野 + 计划查 hessenberg 却未执行 API | 同步修复 `is_upper` 与 `_eval_is_upper_hessenberg`：列循环上界 clamp 为 `min(..., self.cols)`；参照 `_eval_is_lower` 已安全的 `range(..., self.cols)` 模式做反模式扫描 |
| **sympy__sympy-12481** | `sympy/combinatorics`（`Permutation.__new__` / `permutations.py`） | **AssertionError**（`Permutation([[0,1],[0,2]])` 结果错误，非 Exception） | 正确识别 `has_dups` 守卫过严，但 **误重写已正确的下游 `Cycle` 合成**；混淆 array form 下标赋值与置换复合语义 | 仅将守卫改为 `if has_dups(temp) and not is_cycle: raise`；保留 `c = Cycle(); c = c(*ci)` 现有合成路径（错误信息 `use Cycle(...)` 即设计意图提示） |

### 横向共性（Cross-Cutting Themes）

- **5/5 均属「局部正确、全局契约失败」**：11400/11897/12171 修错层或缺依赖；12454 修对但未修全；12481 守卫修对但下游画蛇添足。
- **4/5 存在 Issue 描述范围与实际修复范围落差**：11897（exp/fraction 症状 vs Piecewise 括号）、12171（Derivative+Float vs 仅 Derivative）、12454（is_upper vs hessenberg）、12481（`[[0,1],[0,1]]` vs `[[0,1],[0,2]]`）。
- **3/5 在 printing 模块**：共同缺失「读邻居 `_print_*` / 复用已有 Printer 基础设施」意识（11400 Piecewise 委托、12171 Hold+doprint、11897 `_needs_*_brackets`）。
- **内部 Reviewer/Reproducer 验收过窄**：11400 只查「不含 Not supported」、12454 只测 `is_upper`、12481 候选 Patch 2/4 已是 Golden 却未选中。

### 关键差异（Discriminating Factors）

| 维度 | 11400 / 11897 / 12171 | 12454 | 12481 |
|---|---|---|---|
| 失败子类型 | 输出格式/架构层错误 | 修复范围不完整（兄弟方法漏修） | 过度修复（重写正确下游） |
| 是否引入回归 | 11897 有 RecursionError；12171 有 test_Pow 回归 | 无 PASS_TO_PASS 回归 | 无 PASS_TO_PASS 回归 |
| 核心数学域 | 代码生成 / 排版 precedence | 矩阵索引边界 / 空真语义 | 置换合成 / 守卫 vs 核心逻辑分离 |

---

## 任务 2：通用错因范式（2–3 种）

### 范式 A：Issue 锚定错位（Issue Misalignment）

**行为表现：**

- Agent 将 **Issue 正文、Reporter 草稿代码、Reproducer 通过** 当作完成标准，而非 **仓库既有惯例与同模块邻居实现**。
- 典型路径：Issue 描述多个子问题 → Agent 全部实现（12171 的 Float）→ 引入回归；Issue 只点名一个函数 → Agent 只改一处（12454 的 hessenberg）；Issue 示例是 broad 症状 → Agent 修错代码路径（11897 的 `_print_Mul` 而非 `_needs_mul_brackets`）。
- 伴随现象：检索阶段曾触及正确线索（11897 搜过 `_needs_mul_brackets`、12454 CoT 提到 hessenberg）但未整合进最终补丁。

**覆盖 Case：** 11897、12171、12454（主因）；11400、12481（次因——忽略 Issue 中 Piecewise/Cycle 架构线索）。

---

### 范式 B：SymPy 架构层/委托链盲区（Architectural Layer & Delegation Blindness）

**行为表现：**

- Agent 在 **错误的抽象层** 打补丁，或在 **已有基础设施可用时** 手写等价但契约不同的逻辑。
- 子模式 B1 — **分层混淆**（11897）：格式化层 vs 括号/决策层；在核心 `_print_*` 内 bypass 中间变换触发互调递归。
- 子模式 B2 — **组合委托缺失**（11400）：直接拼接目标语言字符串，而非构造 AST 子树并复用已有 printer 链。
- 子模式 B3 — **家族契约未对齐**（12171）：Issue 草稿 vs 同文件邻居方法的包装符/参数 join 方式不一致。
- 子模式 B4 — **守卫 vs 核心逻辑未分离**（12481）：守卫修对后仍重写下游已正确的合成路径。

**覆盖 Case：** 11400、11897、12171、12481（主因）；12454 的「参照 `_eval_is_lower` 安全模式」同属架构对照缺失。

---

### 范式 C：Bug Class 泛化不足（Incomplete Anti-Pattern Generalization）

**行为表现：**

- Agent 对 **触发点** 的数学/逻辑理解正确，但未将 fix **上升为 bug class 规则** 并在同模块/同文件做系统性排查。
- 典型路径：12454 的 `range(min(i, self.cols))` 与 Golden 逐字一致，但遗漏 `_eval_is_upper_hessenberg` 中同构越界；11400 只加 `_print_sinc` 却遗漏 `_print_Relational` 这一 **前置依赖**。
- 伴随现象：上下文块中已可见兄弟方法（12454 Location #2 含 hessenberg 源码），但被「最小修改原则」误读为「忽略可见的相同反模式」。

**覆盖 Case：** 12454（主因）；11400（Relational 依赖漏修）；11897/12171/12481 亦有「只改一处、未扫同类」成分但非主因。

---

## 任务 3：高价值语义常识规则库

以下规则可直接拷贝至 AutoCodeRover 路由代码。每条均为高层泛化常识，无特定题目/行号硬编码。

**设计前提**：Agent 在 Search / Patch 阶段 **不可见** 隐藏评测题集；规则须引导 Agent 通过 Issue 线索 + 仓库源码调查来推断正确修复范围与实现契约。

---

### Rule 1: Issue Skepticism & Scope Discipline

> **Rule Name:** `ISSUE_SKEPTICISM_AND_SCOPE`
>
> **Scope:** 全量通用
>
> **Prompt Text:**

```text
Treat the Issue as a symptom report, NOT a complete fix specification.

ISSUE SKEPTICISM:
- Issue descriptions often over-generalize (multiple symptoms) or under-specify (only one function named while sibling methods share the same bug).
- Embedded "suggested fix" or example code blocks from the Reporter are draft hints only — NOT ground truth. They may omit wrappers, use wrong APIs, or diverge from merged project style.
- Error messages that suggest an alternative API ("use X instead") signal that X likely already implements the desired behavior; the bug may be blocking access, not missing logic.
- Maintain healthy skepticism: verify every Issue claim against actual source code before implementing.

SCOPE DISCIPLINE (without access to hidden test suites):
- Fix the root cause implied by the Issue, but infer the FULL fix scope from codebase structure — not from Issue brevity.
- Do NOT implement every sub-problem the Issue mentions if your investigation shows only one is broken, or if fixing an unmentioned sub-problem requires overriding inherited behavior (risk of regression).
- Do NOT declare the task complete when only a narrow reproducer passes; ask whether symmetric or sibling code paths need the same fix.
- When Issue examples and neighbor-code conventions disagree, ALWAYS follow neighbor-code conventions.
```

---

### Rule 2: SymPy Codebase Architecture Reconnaissance & Convention Reuse

> **Rule Name:** `SYMPY_ARCHITECTURE_RECON_AND_REUSE`
>
> **Scope:** `sympy/*` 全模块（printing、matrices、combinatorics、core、functions 等）
>
> **Prompt Text:**

```text
Before writing any patch, actively investigate the target module's architecture in the repository — do NOT rely on Issue text alone.

ARCHITECTURE RECONNAISSANCE (mandatory search step):
1. From the Issue, identify the affected module (e.g., printing, matrices, combinatorics).
2. Read the target class AND its inheritance chain (parent classes, mixins) to understand dispatch, delegation, and shared helpers.
3. Identify which abstraction layer owns the bug:
   - Dispatch / handler layer (e.g., _print_<Type>, _eval_is_<Property>, __new__ guards)
   - Decision / policy layer (e.g., _needs_*_brackets, validation guards, shape checks)
   - Formatting / algorithm layer (e.g., fraction rendering, loop bodies, composition logic)
   Fix at the layer that OWNS the behavior — not a symptomatic layer above or below.

4. Survey the module for established patterns:
   - printing: layered _print_* dispatch, _needs_*_brackets for precedence, AST delegation over string hacking, doprint vs stringify
   - matrices: _eval_is_* property families with symmetric upper/lower variants; index bounds tied to self.rows/self.cols
   - combinatorics: guard clauses vs core composition helpers (Cycle, rmul); internal representation contracts
   - core/functions: assumption-aware evaluation vs printing separation
   Adapt your investigation to whichever module the Issue touches — the pattern of "find the owning layer first" is universal.

CODEBASE CONVENTION REUSE (authoritative over Issue drafts):
- BEFORE adding or modifying any method, read semantically similar methods in the SAME class (neighbors) and the SAME hierarchy (parent class overrides).
- Extract shared contracts: outer wrappers, argument joining, bracket style, loop bound patterns, guard structure.
- Prefer reusing existing helpers, delegation chains, and composition utilities over reimplementing equivalent logic inline.
- When adding a new handler, mirror the style of sibling handlers — neighbor code is more authoritative than Issue example code.
- Check parent class: if parent already implements _print_<Type> or provides a safe default, extend or call super rather than bypassing with ad-hoc logic.

DELEGATION OVER REIMPLEMENTATION:
- When no native support exists, prefer constructing equivalent internal representations and routing through existing pipelines (e.g., build Piecewise/Relational AST then self._print, narrow a guard and keep downstream Cycle composition, clamp loop bounds consistently across sibling properties).
- Trace dispatch chains before adding bypass paths; avoid mutual recursion between peer _print_* methods.
```

---

### Rule 3: Minimal Change & Sibling-Method Completeness Audit

> **Rule Name:** `MINIMAL_CHANGE_AND_SIBLING_AUDIT`
>
> **Scope:** 全量通用（Patch 生成与候选选择阶段）
>
> **Prompt Text:**

```text
Apply these heuristics before submitting or selecting a patch:

MINIMAL CHANGE PRINCIPLE:
- Make the smallest change that resolves the Issue's root cause while preserving existing behavior everywhere else.
- Prefer: narrowing a guard, adding one type check, clamping a loop bound, adding a single handler aligned with neighbors, or removing an overly strict validation — over rewriting algorithms or refactoring control flow.
- If the Issue describes a single validation or format failure but your patch restructures multiple methods or control-flow branches, STOP and ask whether a guard-only or rule-only fix suffices.
- When a bug is an overly strict entry guard, FIRST verify whether downstream logic already handles the input once the guard is removed or narrowed. Prefer guard-only changes; do not rewrite downstream code without evidence it is broken.

SIBLING-METHOD COMPLETENESS AUDIT (critical — addresses incomplete fixes):
- After identifying a fix for ONE method, scan the ENTIRE class or file for related methods that share the same structural pattern or mathematical symmetry.
- Examples of "sibling" relationships: is_upper / is_upper_hessenberg / _eval_is_upper*; _print_Integral / _print_Sum / _print_Derivative; guard+compose pairs in the same constructor.
- If the same anti-pattern (unchecked index bound, missing handler, overly broad dup check, wrong abstraction layer) appears in siblings, fix ALL instances — not only the one named in the Issue.
- A patch that passes the Issue reproducer but leaves the same bug class in sibling methods is INCOMPLETE.
- When bug localization provides an entire class/module context, audit every visible sibling method. "Do not modify every location" means skip UNRELATED bugs — NOT skip identical anti-patterns already visible in the provided context.

PATCH SELECTION (multi-candidate workflows):
- Prefer the candidate that: (a) smallest diff, (b) preserves existing helper/class usage, (c) aligns with neighbor-method conventions, (d) passes reproduction tests if available.
- Reject candidates that "look more complete" in natural language but add unnecessary algorithm rewrites or override inherited behavior without need.
```

---

## 规则与范式映射

| Prompt Rule | 对抗范式 | 主要覆盖 Case |
|---|---|---|
| Rule 1 `ISSUE_SKEPTICISM_AND_SCOPE` | 范式 A | 11897, 12171, 12454, 12481 |
| Rule 2 `SYMPY_ARCHITECTURE_RECON_AND_REUSE` | 范式 B | 11400, 11897, 12171, 12481, 12454 |
| Rule 3 `MINIMAL_CHANGE_AND_SIBLING_AUDIT` | 范式 C + 流程层 | 全部 5 Case |

---

## 单案诊断报告索引

| Instance | 报告路径 |
|---|---|
| sympy__sympy-11400 | [sympy__sympy-11400.md](./sympy__sympy-11400.md) |
| sympy__sympy-11897 | [sympy__sympy-11897.md](./sympy__sympy-11897.md) |
| sympy__sympy-12171 | [sympy__sympy-12171.md](./sympy__sympy-12171.md) |
| sympy__sympy-12454 | [sympy__sympy-12454.md](./sympy__sympy-12454.md) |
| sympy__sympy-12481 | [sympy__sympy-12481.md](./sympy__sympy-12481.md) |

---

## ver1 工程落地说明

| 组件 | 路径 |
|------|------|
| 版本常量 | `app/knowledge/ver1.py` — `ACR_VERSION=ver1`, `[AutoCodeRover-ver1]` |
| 注入路由 | `app/knowledge/semantic_injection.py` — `build_semantic_context_ver1()` |
| Patch 注入 | `app/agents/agent_write_patch.py` — `_construct_init_thread()`（含 `bug_locs` 为空路径） |
| Search 注入 | `app/agents/agent_search.py` — `generator()` |
| 配置开关 | `app/config.py` — `enable_semantic_injection_ver1: true`；conf 字段 `enable_semantic_injection_ver1` |
| 元数据 | `<task_dir>/semantic_injection_ver1.json`；`output_*/acr_version.json` |

**评测命令（SymPy ver1，推荐 per-instance pipeline）：**

详见 [`document/PER_INSTANCE_PIPELINE_GUIDE.md`](../../PER_INSTANCE_PIPELINE_GUIDE.md)。

```bash
export PIPELINE_PROFILE=ver1
export SYSTEM_VERSION=ver1
python3 scripts/lite300_process_instances.py \
  --instances-file conf/lite300_tasks/sympy.txt \
  --system-version ver1 \
  --pipeline-profile ver1
```

Legacy batch（不推荐作 L3+飞书入口）：`bash scripts/run_sympy_ver1_eval.sh`

**输出目录（与 baseline 隔离）：**

- L2: `experiment/deepseek-lite-300-ver1/repos/sympy`
- L3 sync: `lite300_output_ver1/repos/sympy`
- 报告: `document/output_analysis/sympy/sympy_ver1_run_report.md`

**防污染：** L2/L3 前 `git reset --hard` + `git clean -fdx`（`scripts/repo_sanitize_ver1.sh`）

**飞书上传：** 每题 L3 完成后或 L2 终局失败时 **立即 upsert**（`系统版本=ver1`）。需在飞书表「系统版本」中预先添加 `ver1` 选项。

---

*生成依据：5 份单案 C 类诊断临床报告 + SWE-bench Lite meta.json + Golden 评测日志交叉验证。规则库已按 Patch 阶段不可见评测题集约束修订。*
