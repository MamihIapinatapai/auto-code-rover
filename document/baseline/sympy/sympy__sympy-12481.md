# 单案诊断临床报告：sympy__sympy-12481

> **分类**: C 类（Logic/Assertion Failure）  
> **模型**: deepseek-deepseek-chat  
> **任务目录**: `lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/`  
> **评测结果**: L2 PASS（补丁可应用）→ L3 FAIL（`test_args` 失败，7 项 PASS_TO_PASS 保持通过）  
> **特殊性质**: 本案例属于 **「定位正确、守卫条件修对、但画蛇添足重写下游逻辑」** 型 C 类失败——Agent 与人类补丁在 `has_dups` 守卫上的修改一致，却额外替换了已能正确处理非不交轮换的 `Cycle` 合成路径，导致数学语义错误。

---

## 0. 专有名词解释 (Glossary)

| 术语 | 解释 |
|------|------|
| **Permutation（置换）** | 对有限集合 `{0,1,...,n-1}` 的一一映射；SymPy 用 **array form**（数组形式）存储：`array_form[i]` 表示元素 `i` 被映射到哪里 |
| **Cycle Notation（轮换记法）** | 用不相交轮换的乘积表示置换，如 `(0 1)(2 3)`；`Permutation([[0,1],[2,3]])` 即轮换列表输入 |
| **Non-disjoint Cycles（非不交轮换）** | 多个轮换共享至少一个元素，如 `[[0,1],[0,1]]` 中 `0` 和 `1` 同时出现在两个轮换里 |
| **Left-to-right Composition（从左到右合成）** | Issue 要求：先应用最左边的轮换，再依次向右；SymPy 现有代码通过 `c = Cycle(); c = c(*ci)` 实现 |
| **`Cycle` 类** | SymPy 中表示轮换的内部类型；`Cycle().__call__(*elements)` 将新轮换与已有轮换**合成** |
| **`has_dups(temp)`** | 检查扁平化后的元素列表是否有重复；原代码用它拦截「跨轮换重复元素」，Issue 要求取消对 cyclic form 的此拦截 |
| **Array Form vs Cycle Application** | **错误根源**：直接写 `aform[cycle[i]] = cycle[i+1]` 是在**原地覆写映射表**，不等于置换合成；正确合成应通过 `Cycle` 或 `new[i] = cycle(old[i])` |
| **`FAIL_TO_PASS`** | SWE-bench 指标：应用补丁 + test patch 后原先失败的测试应变通过。本实例仅 `test_args` |
| **`PASS_TO_PASS`** | 回归指标：原先通过的测试仍应通过。本实例 Agent **未引入回归**（7 项全部 success） |
| **Guard Clause（守卫分支）** | 函数入口处的提前校验/返回逻辑；本案例 bug 在 `has_dups` 守卫，真正合成逻辑在下游 911–917 行 |

---

## 1. 原始问题快照 (Issue Snapshot)

### 1.1 Issue 原文

````text
`Permutation` constructor fails with non-disjoint cycles
Calling `Permutation([[0,1],[0,1]])` raises a `ValueError` instead of constructing the identity permutation.  If the cycles passed in are non-disjoint, they should be applied in left-to-right order and the resulting permutation should be returned.

This should be easy to compute.  I don't see a reason why non-disjoint cycles should be forbidden.
````

> 来源：[`problem_statement.txt`](../../../lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/problem_statement.txt)

### 1.2 Issue 中文翻译

**标题**：`Permutation` 构造函数无法处理非不交轮换

**正文**：

- 调用 `Permutation([[0,1],[0,1]])` 时抛出 `ValueError`，而不是构造出**单位置换**（identity permutation，即什么都不动的置换）。
- 若传入的轮换彼此**不交**（没有共同元素），应按**从左到右**的顺序依次应用，并返回合成后的置换。
- Reporter 认为这很容易计算，没有理由禁止非不交轮换。

### 1.3 核心诉求概括

| 维度 | 内容 |
|------|------|
| **报告了什么 Bug** | `Permutation` 在 cyclic form（`[[...],[...]]`）下，若多个轮换共享元素，会在构造函数中提前 `raise ValueError` |
| **期望行为** | `Permutation([[0,1],[0,1]])` 应返回单位置换；非不交轮换按左到右合成 |
| **实际行为** | 抛出 `ValueError: there were repeated elements; to resolve cycles use Cycle(0, 1)(0, 1).` |
| **数学语义** | 两次相同的 `(0 1)` 对换合成后应回到恒等映射 |

### 1.4 Issue 与 SWE-bench 验收的落差（重要）

Issue 举例为 `[[0,1],[0,1]]`，但 SWE-bench test patch 实际验收的是更一般的情形：

| 来源 | 内容 |
|------|------|
| **新增断言** | `assert Permutation([[0, 1], [0, 2]]) == Permutation(0, 1, 2)` |
| **删除断言** | `raises(ValueError, lambda: Permutation([[1], [1, 2]]))` —— 不再要求此类输入报错 |
| **含义** | 测试不仅覆盖「相同轮换重复」，还覆盖「部分重叠的不同轮换」；Agent 若只针对 `[[0,1],[0,1]]` 做特判会不够 |

---

## 2. Agent 运行轨迹与思维链追踪 (Agent Trajectory & CoT Analysis)

### 2.1 流水线概览

本实例经 **3 次 overall retry**（`output_0` → `output_1` → `output_2`），最终选中 `output_1/extracted_patch_3.diff`。

| Retry | 检索结果 | 补丁结果 |
|-------|----------|----------|
| `output_0` | 10 轮搜索，大量 API 参数错误，`bug_locations: []` | 3 次 write_patch 失败，流程终止 |
| `output_1` | 1 轮 4 个 API + 1 轮锚定 | 生成 7 个候选补丁，**选中 patch 3** |
| `output_2` | 2 轮搜索，正确锚定 | 生成 6 个候选补丁（未选中） |

以下详述**最终贡献选中补丁**的 `output_1` 检索阶段，并补充 `output_0` 的失败模式。

### 2.2 Stage 1 工具调用时序（output_1，成功路径）

**Round 0 — 并行检索（4 个 API）**

| 序号 | 工具 | 参数 | 结果 |
|------|------|------|------|
| 1 | `search_method_in_file` | `__new__`, `permutations.py` | 返回完整 `__new__` 构造器（含 898–917 行） |
| 2 | `search_class_in_file` | `Cycle`, `permutations.py` | 返回 `Cycle` 类实现 |
| 3 | `get_code_around_line` | `permutations.py`, line 900, window 30 | 返回报错行附近上下文 |
| 4 | `search_code_in_file` | `"cycles"`, `permutations.py` | 返回文件中 cycles 相关代码片段 |

**Round 1 — 分析后锚定（0 个 API，直接输出 bug location）**

Agent 输出 `bug_locations`，不再调用工具。

**output_2 检索（补充）**

| Round | 工具 | 说明 |
|-------|------|------|
| 0 | `search_method_in_class(__new__, Permutation)` | 定位构造器 |
| 1 | （意图）`search_class(Cycle)` | 在思维链中提到，最终 round 1 直接给出 bug location |

**output_0 检索（失败路径，10 轮）— 典型调用序列**

1. `search_class('Permutation')` + `search_method_in_class('__init__', 'Permutation')` ❌
2. `search_method_in_file('__new__', 'Permutation')` ❌（文件路径错误）
3. `search_code('class Permutation')` + `search_code('def __new__')` ✓
4. `search_code('class Permutation(Basic)')` + `search_code('def __new__(cls, *args, **kwargs)')` ✓
5. `search_code_in_file('def __new__(cls, *args, **kwargs)', '')` ✓（多次重复）
6. `search_code_in_file('def __new__', '')` ✓（多次重复）
7. `search_code_in_file('def __new__(cls, *args, **kwargs)', 'permutations.py')` ✓
8. 达到轮次上限 → `bug_locations: []` → write_patch 失败

### 2.3 最终锚定的 Fault Location

| 字段 | 值 |
|------|-----|
| **文件** | `sympy/combinatorics/permutations.py` |
| **类** | `Permutation` |
| **方法** | `__new__` |
| **核心行号** | **898–903**（`has_dups` 提前报错）；Agent 认为 **911–917**（`Cycle` 合成）已正确 |
| **Reproducer 堆栈行** | **第 900 行** `raise ValueError(...)` |

> 来源：[`output_1/search/bug_locations_after_process.json`](../../../lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/output_1/search/bug_locations_after_process.json)

### 2.4 定位评估：找对地方了吗？

**结论：定位基本正确，但对下游逻辑的必要性判断错误。**

| 维度 | 评估 |
|------|------|
| **文件/类/方法** | ✅ 正确锚定 `Permutation.__new__` |
| **报错根因** | ✅ 正确识别 898–903 行的 `has_dups` 守卫过严 |
| **修复策略** | ⚠️ **半对半错**：移除 cyclic form 的 dup 检查是对的；但认为必须重写 911–917 行的 `Cycle` 合成是错的 |
| **遗漏** | ❌ 未验证「仅删守卫、保留 `Cycle`」是否已足够（人类补丁正是如此） |

### 2.5 思维链中的认知偏差

#### 偏差 1：「现有 Cycle 合成可能有问题」的未经证实的怀疑

检索阶段 Agent 在 `output_2/search_round_1.json` 中写道：

> *"The fix should remove the early error ... and let the code fall through to lines 911-917, which **already correctly** applies cycles in left-to-right order using `Cycle(*ci)`."*

但在 **写补丁阶段**（`patch_raw_3.md`）思维发生反转：

> *"Wait - the test says the result is `(1)` instead of identity. Let me check what `Cycle.__call__` actually does. The issue might be that `Cycle` doesn't compose cycles in the way we expect."*

**原因分析**：Agent 在本地 reproducer 中看到 `[[0,1],[0,1]]` 仍失败（因为当时补丁尚未正确移除守卫，或只移除了守卫但未理解 `Cycle` 已能处理），便**错误推断**下游 `Cycle` 逻辑有 bug，而非验证「仅删守卫」的最小修复。

#### 偏差 2：混淆「轮换作用于下标」与「置换合成」

写补丁时 Agent 采用：

```python
aform[cycle[i]] = cycle[(i + 1) % len(cycle)]
```

这在数学上等价于：**把每个轮换的映射直接写入 array form 的下标位置**，而不是对当前置换做合成。对非不交轮换，后写轮换会破坏先写轮换建立的映射关系，产生**非置换**（值域出现重复，如 `[2,0,2]`）。

**原因分析**：Agent 将「轮换记法 `(a b c)` 的含义」（`a→b, b→c, c→a`）与「array form 的语义」（`aform[i]` = 元素 i 的像）混为一谈，未理解 SymPy 已有 `Cycle().__call__` 封装了正确的合成语义。

#### 偏差 3：补丁选择器强化了错误方案

`agent_selection.json` 显示流水线共产生 12 个候选补丁，其中 **Patch 2/4 与人类 Golden 完全一致**（仅改 `has_dups` 守卫），但选择器最终选了 **Patch 3**（额外重写合成逻辑），理由是：

> *"implements left-to-right composition by directly building the array form ... handling [[0,1],[0,1]] correctly"*

**原因分析**：选择器未运行测试验证，仅凭文字描述和「看起来更完整」而选择过度修改的补丁——典型的 **over-engineering bias**。

#### 偏差 4：对 Issue「容易修复」暗示的误读

Issue 明确说 *"This should be easy to compute"*，且错误信息已提示 `use Cycle(0, 1)(0, 1)`——暗示 **`Cycle` 路径已能处理**，只需去掉提前拦截。Agent 却实现了一套新的手写合成，违背了最小修改原则。

---

## 3. 失败补丁解剖 (Failed Patch Dissection)

### 3.1 完整失败补丁

> 来源：[`output_1/extracted_patch_3.diff`](../../../lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/output_1/extracted_patch_3.diff)（`selected_patch.json` 选定）

```diff
diff --git a/sympy/combinatorics/permutations.py b/sympy/combinatorics/permutations.py
index 136ed5a478..37c7062b9c 100644
--- a/sympy/combinatorics/permutations.py
+++ b/sympy/combinatorics/permutations.py
@@ -895,12 +895,8 @@ def __new__(cls, *args, **kwargs):
         # counting starts from 1.
 
         temp = flatten(args)
-        if has_dups(temp):
-            if is_cycle:
-                raise ValueError('there were repeated elements; to resolve '
-                'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
-            else:
-                raise ValueError('there were repeated elements.')
+        if has_dups(temp) and not is_cycle:
+            raise ValueError('there were repeated elements.')
         temp = set(temp)
 
         if not is_cycle and \
@@ -911,10 +907,15 @@ def __new__(cls, *args, **kwargs):
         if is_cycle:
             # it's not necessarily canonical so we won't store
             # it -- use the array form instead
-            c = Cycle()
-            for ci in args:
-                c = c(*ci)
-            aform = c.list()
+            # Compute the permutation by applying cycles left-to-right
+            max_element = max(temp) if temp else -1
+            aform = list(range(max_element + 1))
+            for cycle in args:
+                if len(cycle) > 1:
+                    # Apply the cycle to the current permutation
+                    # The cycle (a0 a1 ... ak-1) maps a_i to a_{i+1 mod k}
+                    for i in range(len(cycle)):
+                        aform[cycle[i]] = cycle[(i + 1) % len(cycle)]
         else:
             aform = list(args)
         if size and size > len(aform):
```

### 3.2 逐段白话解释

| 修改块 | Agent 的逻辑 | 为什么它「以为」能修好 |
|--------|-------------|----------------------|
| **修改 1：`has_dups` 守卫** | 把 `if has_dups(temp): if is_cycle: raise` 改成 `if has_dups(temp) and not is_cycle: raise`，允许 cyclic form 跨轮换重复元素 | ✅ 与 Issue 一致：非不交轮换不应在入口被拒绝；array form 仍禁止重复元素 |
| **修改 2：删除 `Cycle` 合成** | 认为原 `c = Cycle(); c = c(*ci)` 无法处理非不交轮换 | ❌ 错误假设——原逻辑在去掉守卫后即可正常工作 |
| **修改 3：手写 array 初始化** | `aform = list(range(max_element + 1))` 从单位置换出发 | 思路接近「从左到右合成」，但后续应用方式错误 |
| **修改 4：内层循环写映射** | 对每个轮换，执行 `aform[cycle[i]] = cycle[i+1]` | Agent 认为这是在「依次应用轮换」；实际上是在**覆写下标位置的目标值**，不是置换复合，重叠轮换时会产生非法映射 |

### 3.3 数值反例（说明补丁为何数学上错误）

对 `Permutation([[0, 1], [0, 2]])`（SWE-bench 验收用例）：

```
初始 aform = [0, 1, 2]  （单位置换）

应用轮换 [0,1]（Agent 写法）：
  aform[0] = 1, aform[1] = 0  →  [1, 0, 2]

应用轮换 [0,2]（Agent 写法）：
  aform[0] = 2, aform[2] = 0  →  [2, 0, 2]  ← 值 2 出现两次，不是合法置换！

期望结果 = Permutation(0, 1, 2) 的 array form（由 Cycle 合成得到）
```

Agent 本地 reproducer 对 `[[0,1],[0,1]]` 也曾得到 `(0 1)` 而非单位置换（见 `execution_3_0.json`），进一步证明手写逻辑错误。

---

## 4. 黄金标准对比 (Ground Truth Alignment)

### 4.1 人类正确补丁（Ground Truth）

> 来源：[`developer_patch.diff`](../../../lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/developer_patch.diff)

```diff
diff --git a/sympy/combinatorics/permutations.py b/sympy/combinatorics/permutations.py
--- a/sympy/combinatorics/permutations.py
+++ b/sympy/combinatorics/permutations.py
@@ -895,12 +895,8 @@ def __new__(cls, *args, **kwargs):
         # counting starts from 1.
 
         temp = flatten(args)
-        if has_dups(temp):
-            if is_cycle:
-                raise ValueError('there were repeated elements; to resolve '
-                'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
-            else:
-                raise ValueError('there were repeated elements.')
+        if has_dups(temp) and not is_cycle:
+            raise ValueError('there were repeated elements.')
         temp = set(temp)
 
         if not is_cycle and \
```

**关键特征**：仅修改 **4 行**守卫逻辑；**911–917 行的 `Cycle` 合成原封不动**。

### 4.2 并排对比

| 维度 | Agent 失败补丁 | 人类正确补丁 |
|------|---------------|-------------|
| **修改行数** | ~20 行（2 处） | 4 行（1 处） |
| **`has_dups` 守卫** | `and not is_cycle` ✅ | `and not is_cycle` ✅ |
| **Cycle 合成路径** | ❌ 删除，替换为手写循环 | ✅ 保留 `c = Cycle(); c = c(*ci)` |
| **对 `[[0,1],[0,1]]`** | 可能得到 `(0 1)` 而非恒等 | ✅ 恒等置换 |
| **对 `[[0,1],[0,2]]`** | ❌ 非法/错误映射 | ✅ 通过 test_args |
| **设计原则** | 重写已有抽象 | 信任库内已有 `Cycle` 契约 |

### 4.3 核心分析：人类多考虑了什么？

1. **信任现有下游契约**  
   错误信息 `use Cycle(0, 1)(0, 1)` 是维护者故意留下的提示：合成逻辑已在 `Cycle` 中实现，bug **仅是守卫过早拦截**。人类读懂了这一设计意图。

2. **区分「跨轮换重复」与「轮换内重复」**  
   - **跨轮换重复**（非不交）：应允许，由 `Cycle` 合成  
   - **轮换内重复**（如 `[0,0,1]`）：仍由其他路径或 `Cycle` 自身处理；test patch 删除的是 `[[1],[1,2]]` 的 ValueError 期望，而非鼓励轮换内重复

3. **不碰已验证的合成路径**  
   911–917 行对**不交轮换**已长期工作；Issue 只要求扩展输入域，不要求改写算法。

4. **最小修改原则**  
   SWE-bench Golden 是 4 行 diff；Agent 额外 15 行不仅无必要，还引入回归风险。

### 4.4 为什么 Agent 失败补丁会失败？

| 层次 | 说明 |
|------|------|
| **直接原因** | `test_args` 第 342 行 `AssertionError`：`Permutation([[0,1],[0,2]]) != Permutation(0,1,2)` |
| **数学原因** | 手写 `aform[cycle[i]] = ...` 不是置换合成，产生错误 array form |
| **工程原因** | 不必要的重写覆盖了经过测试的 `Cycle` 路径 |
| **流程原因** | 候选 Patch 2/4 已是正确解，但 patch selector 选了过度修改的 Patch 3 |

---

## 5. 评测报告与崩溃堆栈 (Evaluation Log & Traceback)

### 5.1 评测配置

| 项目 | 值 |
|------|-----|
| **Eval Log** | `lite300_output/repos/sympy/eval_logs/sympy__sympy-12481.deepseek-deepseek-chat.eval.log` |
| **测试文件** | `sympy/combinatorics/tests/test_permutations.py` |
| **FAIL_TO_PASS** | `test_args` ❌ |
| **PASS_TO_PASS** | 7 项全过（`test_Cycle`, `test_Permutation`, `test_from_sequence`, `test_josephus`, `test_mul`, `test_printing_cyclic`, `test_ranking`） |

### 5.2 SWE-bench Test Patch（验收标准）

```diff
@@ -339,6 +339,7 @@ def test_args():
     assert Permutation(
         [[1], [4, 2]], size=6) == Permutation([0, 1, 4, 3, 2, 5])
+    assert Permutation([[0, 1], [0, 2]]) == Permutation(0, 1, 2)
     assert Permutation([], size=3) == Permutation([0, 1, 2])
@@ -349,7 +350,6 @@ def test_args():
     raises(ValueError, lambda: Permutation([1, 1, 0]))
-    raises(ValueError, lambda: Permutation([[1], [1, 2]]))
```

### 5.3 崩溃堆栈（Docker pytest 输出）

```
sympy/combinatorics/tests/test_permutations.py[9] 
test_Permutation ok
test_josephus ok
test_ranking ok
test_mul ok
test_args F
test_Cycle ok
...

________________________________________________________________________________
___________ sympy/combinatorics/tests/test_permutations.py:test_args ___________
  File "/home/swe-bench/sympy__sympy/sympy/combinatorics/tests/test_permutations.py", line 342, in test_args
    assert Permutation([[0, 1], [0, 2]]) == Permutation(0, 1, 2)
AssertionError

============= tests finished: 8 passed, 1 failed, in 0.14 seconds ==============
```

### 5.4 核心分析：为什么报这个错？

| 问题 | 答案 |
|------|------|
| **错误类型** | `AssertionError`（非 Exception 崩溃） |
| **失败测试** | `test_args`，第 **342** 行 |
| **失败断言** | 非不交轮换 `[[0,1],[0,2]]` 应等于 `Permutation(0,1,2)` |
| **根本原因** | Agent 手写合成产生错误 array form；Golden 补丁用原 `Cycle` 路径可得到正确结果 |
| **对比 Golden eval** | `SWE-bench_Lite_golden` 日志显示相同测试 **9 passed, 0 failed** |

### 5.5 Agent 本地 Reproducer 反馈（补丁生成阶段）

`output_1/execution_3_0.json` 记录 Agent 自己的 reproducer 在应用 Patch 3 后：

```
AssertionError: Expected identity permutation, got (0 1)
```

说明 Agent **曾观察到补丁失败**，但在思维链中将其归因于「`Cycle` 有问题」而非「手写合成错误」，最终仍提交了错误方案。

---

## 6. 总结

Agent 在本案例中的失败，并非定位错误，而是典型的 **「正确识别守卫 bug + 错误重写下游已正确逻辑」**：它准确找到 `Permutation.__new__` 第 898–903 行的 `has_dups` 过早拦截，并正确修改为 `if has_dups(temp) and not is_cycle`；但它缺乏对 SymPy **置换合成语义** 的常识——误以为必须手写 `aform[cycle[i]] = cycle[i+1]` 来实现「从左到右应用轮换」，而没有理解 **array form 的每个下标存的是「像」而非「轮换定义」**，真正的合成应由 `Cycle().__call__` 或「对当前映射做复合」完成。人类开发者从错误提示 `use Cycle(...)` 中读懂了设计契约，只做 4 行最小修改；Agent 则 over-engineer，并在 12 个候选补丁中放弃了与人类一致的 Patch 2/4，选择了画蛇添足的 Patch 3。

**缺乏的核心语义常识**：

1. 置换 array form 的语义（`aform[i]` = 元素 i 被映射到哪里）  
2. 轮换应用 = 置换复合，不能简单对下标赋值  
3. 库内已有抽象（`Cycle`）的契约信任与「最小修改」原则  
4. 错误信息作为 API 设计意图的线索

---

## 7. Prompt 静态语义注入建议（可泛化）

### 7.1 守卫条件 vs 核心逻辑分离原则

```
When fixing validation/guard-clause bugs, first check whether downstream logic 
already handles the newly-allowed input correctly once the guard is removed.
Prefer deleting or narrowing the guard ONLY. Do not rewrite downstream 
algorithms unless you have evidence they are broken for the new input class.
```

**泛化场景**：任何「入口校验过严」类 bug（类型检查、范围检查、重复元素检查），应先验证「放开校验后现有路径是否已正确」。

### 7.2 读懂错误信息中的 API _HINT

```
If an error message suggests an alternative API path (e.g., "use Cycle(...) instead"),
treat that as a strong signal that the alternative path already implements the 
desired semantics. The bug is likely that the constructor blocks reaching that path,
not that the alternative path is missing.
```

**泛化场景**：`ValueError` / `TypeError` 消息中含 *"use X instead"*、*"call Y"* 等提示时。

### 7.3 数学对象语义注入（置换/矩阵/集合）

```
For permutation cycle input [[a,b,...], [c,d,...]]:
- Array form aform satisfies: applying the permutation sends element i to aform[i].
- Applying a cycle (x0 x1 ... xk) means the substitution x0->x1, x1->x2, ..., xk->x0.
- Composing cycles left-to-right means: start from identity, for each cycle C, 
  update aform so new_aform[i] = C(aform[i]) — NOT aform[cycle[j]] = cycle[j+1].
- Reuse existing composition helpers (Cycle, rmul) rather than reimplementing.
```

**泛化场景**：群论/组合数学模块；类似地可对矩阵（行优先 vs 列优先）、复数分支等注入语义。

### 7.4 最小 Diff 启发式

```
Before submitting a patch, compare your diff size to the issue complexity.
If the issue describes a single validation failure but your patch modifies 
multiple algorithmic blocks, STOP and verify whether a guard-only fix suffices.
Candidate patches that only change the guard clause should be preferred when 
they align with the issue's "easy fix" characterization.
```

### 7.5 补丁选择必须过测试（流程层）

```
When multiple patch candidates exist, prefer the one that:
1. Has the smallest diff
2. Preserves existing helper/class usage
3. Passes reproduction tests (if available)
Do NOT select a patch solely because it "looks more complete" in natural language.
```

**泛化场景**：multi-patch selection / self-consistency 流程。

### 7.6 区分「元素级重复」的语义层级

```
Duplicate detection must specify the scope:
- Duplicates WITHIN a single structural unit (e.g., within one cycle) → usually invalid
- Duplicates ACROSS multiple units (e.g., across cycles in a list) → may be valid 
  if composition is defined
When relaxing a global flatten-and-check-dups guard, verify which scope the 
issue actually requires relaxing.
```

**泛化场景**：图节点重复、SQL 列名重复、配置项重复等多层结构。

---

## 8. 关键文件索引

| 用途 | 路径 |
|------|------|
| Issue | `lite300_output/repos/sympy/applicable_patch/sympy__sympy-12481_2026-06-02_12-40-55/problem_statement.txt` |
| Agent 日志 | `.../info.log` |
| 检索锚定 | `.../output_1/search/bug_locations_after_process.json` |
| 失败补丁 | `.../output_1/extracted_patch_3.diff` |
| 补丁选择 | `.../selected_patch.json`, `.../agent_selection.json` |
| Golden Patch | `.../developer_patch.diff` |
| Eval Log | `lite300_output/repos/sympy/eval_logs/sympy__sympy-12481.deepseek-deepseek-chat.eval.log` |
| 评测报告 | `lite300_output/repos/sympy/report/instances/sympy__sympy-12481.json` |

---

## 9. 文档自审（Review Checklist）

| 检查项 | 状态 |
|--------|------|
| Issue 原文完整引用 | ✅ |
| Stage 1 工具调用时序（含失败/成功路径） | ✅ |
| Fault Location 行号与函数名 | ✅ |
| 失败补丁完整 diff | ✅ |
| Golden diff 并排对比 | ✅ |
| Eval traceback 与失败行号 | ✅ |
| 认知偏差与数学语义分析 | ✅ |
| 可泛化 prompt 注入建议 | ✅ |
| 候选 Patch 2/4 = Golden 但未被选中 | ✅ 已记录 |
| PASS_TO_PASS 无回归 | ✅ 已记录 |

**已知局限**：未在本地 sympy testbed 重跑 Golden 补丁验证 `[[0,1],[0,2]]` 的数学推导；结论基于 SWE-bench Golden eval 全过 + 代码逻辑分析 + Agent reproducer 失败日志，与已有分析文档（如 `sympy__sympy-12454.md`）方法论一致。
