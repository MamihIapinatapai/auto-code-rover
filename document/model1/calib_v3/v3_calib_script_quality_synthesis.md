# DeepSWE Python v3 Calib — 复现脚本质量横截面总结

**路径**: `outputs/deepswe_spec_parser/deepswe-spec-parser-python-v3-calib/`  
**数据**: 34 份 `issue_script_match_audit.md` + `AUDIT_INDEX.md`  
**对照**: `document/model1/spec_parser_ver3_dev_plan.md`（P1 / P1.6 / P4 / P4.5 / P5 / P6）  
**日期**: 2026-07-15  

> **核心前提**：`calibration_passed=true` ≠ Issue↔脚本完美匹配。本报告以审计判定与缺陷代号为准，不以校准布尔值为准。

---

## 1. 执行摘要

- **34 case 判定分布（以磁盘报告为准）**：**STRONG_MATCH 9 / PARTIAL_MATCH 9 / INVALID_SCRIPT 16 / PERFECT_MATCH 0 / MISMATCH 0**。  
  （`AUDIT_INDEX.md` 中 10/11/13 为略旧快照，以本报告为准。）
- **一句话总评**：ver3 calib 能稳定「在 buggy 上 exit≠0」，但约一半脚本**不能作为有效 F2P 验收**（死代码 AC、ENV 假校准、Stub、无产出）；另一半里多数仅部分对齐 Issue，**无一题达到 PERFECT_MATCH**。
- **Top-5 共性缺陷**（按工程危害优先，括号为命中数/占比）：  
  1. **D-CALIB**（11 / 32%）— 校准门禁接受「不对味」失败  
  2. **D-NOOUT**（7 / 21%）— 流水线未产出脚本或 Issue  
  3. **D-ENV**（6 / 18%）— pytest / 无关 sympy 等环境失败冒充 F2P  
  4. **D-DEAD**（5 / 15%）— 定义 `test_*` 却不调用  
  5. **D-EXIST / D-STUB**（7+3）— existence-only 或纯 Stub，修对代码仍验不出 / 仍 fail  
  （**D-NARROW** 命中最多 15/44%，属覆盖质量问题，危害次于结构失效。）
- **Top-3 ver3 P0 优化动作**：  
  1. **P5 Gate**：拒绝「仅 ModuleNotFoundError(pytest|sympy.*) / 无 `AC-xxx FAIL`」的 `calibration_passed`  
  2. **P4.5 Lint**：新增 **L11-DEAD-AC**、**L12-STUB-AC**；落地已规划的 **L10-EXISTENCE-ONLY**；硬化 **L4-SWALLOW**  
  3. **P4 Prompt**：强制 AC **顺序内联执行**（禁止只定义不调用）；禁止 `assert True` / 无条件 Stub；FEATURE 必须 happy+negative 行为断言

---

## 2. 效果：什么时候脚本「像样」

### 2.1 好案例清单

| 档 | TASK_ID | 证据强度 | 像样之处（摘要） |
|----|---------|----------|------------------|
| STRONG（精读） | `httpx-multipart-response-parsing` | 精读 | 行为级 I/O；buggy 以缺 API/断言失败；结构可执行 |
| STRONG（精读） | `httpx-streaming-json-iteration` | 精读 | 同上；与 Issue 流式 JSON 能力对齐较好 |
| STRONG（精读） | `cattrs-partial-structuring-recovery` | 精读 | 主路径 + 失败语义多为 AssertionError；次要 D-SHAPE |
| STRONG（启发式） | `ipython-session-bundle-replay`、`kombu-*`、`mnamer-*`、`mobly-*`、`pwntools-*` | 启发式 | AC 分节多、空断言少、能挂 buggy；**可能高估**，需精读复核 |
| 较好 PARTIAL（精读） | `bandit-structured-nosec-directives` | 精读 | AC 覆盖面高、可执行；被无用 `import pytest` 的 ENV 拖累 |
| 较好 PARTIAL（精读） | `fastapi-deprecation-response-headers` | 精读 | 覆盖广、非 Stub；Oracle 层 API 偏差与 existence 边角降档 |
| 较好 PARTIAL（精读） | `adaptix-name-mapping-aliases` | 精读 | 主路径加载/冲突够硬；existence 门闸 + 空断言拖累 |

### 2.2 好复用模式（好脚本共性）

1. **AC 分节在 `main()` 内顺序执行**，不是嵌套 `def test_*` 后直接 `All checks passed`。  
2. **断言是行为级**：构造最小输入 → 观察返回值 / 异常类型 / 副作用，而不是 `hasattr` / `callable`。  
3. **buggy 失败文案可解析**：`AssertionError: AC-xxx FAIL` 或 `NOT_IMPLEMENTED`，而不是无关 `ModuleNotFoundError`。  
4. **FEATURE 至少含 happy path + 一条负向/冲突**（如非法参数、冲突 key、缺资源）。  
5. **Import 契约收敛到仓库包**：不引入 pytest/sympy 等与 Issue 无关的硬依赖。  
6. **失败不靠 Stub**：每个 AC 至少有一次对目标 API 的真实调用（即便预期失败）。

---

## 3. 不足：判定分布与分层解读

| 判定 | 数量 | 含义 | 对下游 F2P / Agent 的影响 |
|------|------|------|---------------------------|
| PERFECT_MATCH | 0 | Must 全覆盖且断言硬、失败语义对 | 理想验收源；本批未出现 |
| STRONG_MATCH | 9 | 主路径+关键约束够用，边角略弱 | 可作为 Search/Patch 的弱监督；精读 3 题可信，启发式 6 题需降权 |
| PARTIAL_MATCH | 9 | 能挂 buggy，但漏 Must / 断言松 / 测偏 | 易导致「假 F2P」：Agent 过拟合弱脚本仍过校准 |
| MISMATCH | 0 | 测错层/目标不符 | — |
| INVALID_SCRIPT | 16 | 无法当验收（死代码、ENV、Stub、无产出） | **最危险**：`calibration_passed` 仍常为 true，污染下游 |

### 分层说明

- **INVALID（47%）**：结构或流水线失效。典型三元组：**(D-DEAD | D-ENV | D-STUB) + D-CALIB**，或 **D-NOOUT**。  
- **PARTIAL（26%）**：脚本「看起来在测」，但 existence / swallow / narrow / wrong-layer 使「正确实现」与「错误实现」区分力不足。  
- **STRONG（26%）**：可用作正向范例喂 Prompt few-shot；其中启发式 STRONG 不应单独作为回归金标。

---

## 4. 共性缺陷 Taxonomy（核心表）

| 代号 | 命中 | 占比 | 代表 case（2–4） | 主责模块 | ver3 计划是否已覆盖 |
|------|------|------|------------------|----------|---------------------|
| **D-CALIB** | 11 | 32% | aiomonitor, gql, igel, sqlfmt, bandit-structured | **P5**（协同 P4.5） | **部分**：有 symptom_aligner / FEATURE gate 构想，**未拒绝 ENV-only / Stub-only** |
| **D-NARROW** | 15 | 44% | adaptix, fastapi-*, mashumaro, textual-kitty, 多个启发式 STRONG | **P1**（协同 P4） | **部分**：FEATURE Prompt 要求 happy+negative+edge，但 P1 AC 常写成 existence |
| **D-NOOUT** | 7 | 21% | bandit-incremental-*, koota, langchain, narwhals, numba, skrub, textual-richlog | **agent 编排** | **弱**：有失败回退策略，缺「无脚本禁止 calibration_passed」硬闸 |
| **D-ENV** | 6 | 18% | aiomonitor, gql, python-statemachine, bandit-structured, psd-tools, sqlfmt | **P5**（协同 P4） | **部分**：ImportError 策略有，但 **pytest/sympy 误导入未专项拦截** |
| **D-EXIST** | 7 | 21% | adaptix, fastapi-*, returns, textual-kitty, tomlkit, vulture | **P4.5 + P1** | **已规划 L10-EXISTENCE-ONLY**，calib 显示 **未生效或未打开 v3 prompts** |
| **D-DEAD** | 5 | 15% | aiomonitor, sqlite-utils, python-statemachine, gql, bandit-interprocedural | **P4**（协同 P4.5） | **未覆盖**：Prompt 假设 runtime 注入 scaffold，**未禁嵌套未调用 test_*** |
| **D-SWALLOW** | 4 | 12% | aiomonitor, mashumaro, tomlkit, vulture | **P4.5** | **已有 L4-SWALLOW-EXCEPTION**，仍漏检或未 blocking |
| **D-STUB** | 3 | 9% | igel, dateutil, bandit-interprocedural | **P4**（协同 P5） | **未覆盖**：无 Stub 模式检测；Gate 把 Stub AssertionError 当成功 F2P |
| **D-WRONG** | 3 | 9% | adaptix, aiomonitor, fastapi-deprecation | **P4**（协同 P1.6） | **部分**：Import Contract / 禁止编造 API 已写，仍生成自创 helper/错路由 |
| **D-VACUOUS** | 2 | 6% | adaptix, fastapi-implicit-head-options | **P4.5** | **可并入 L10/弱断言**；Prompt 已禁弱检查但未点名 `assert True` |
| **D-SHAPE** | 1 | 3% | cattrs（次要） | **P4** | **低优**：避免强制 dict keys vs 属性对象 |

**说明**：一题可多标签；占比分母=34。D-NARROW 虽最广，但常与「尚可运行」共存；D-DEAD/ENV/STUB/NOOUT 直接导致 INVALID。

---

## 5. 缺陷 → ver3.0 模块映射矩阵

图例：**主** = 主责；**协** = 协同；**—** = 无关/弱相关

| 缺陷 | P1 | P1.6 | P4 Prompt/Gen | P4.5 Lint | P5 Gate | P6 / agent |
|------|----|------|---------------|-----------|---------|------------|
| D-DEAD | — | — | **主**（生成结构） | **协**（应拦） | **协**（exit0 风险） | — |
| D-ENV | — | — | **协**（误 import） | **协**（禁硬依赖） | **主**（拒假校准） | 协（勿放行） |
| D-STUB | 协（AC 过空） | 协 | **主** | **协** | **主**（拒 Stub F2P） | — |
| D-EXIST | **主**（AC 写成 hasattr） | 协 | **协** | **主**（L10） | 协（feature_calibrator） | — |
| D-VACUOUS | — | — | **协** | **主** | 协 | — |
| D-SWALLOW | — | — | 协 | **主**（L4） | 协 | — |
| D-NARROW | **主** | **协**（缺行为约束） | **协** | — | — | — |
| D-WRONG | 协 | **协**（draft 偏） | **主** | 协（L9 FAKE-IMPORT） | 协（symptom） | — |
| D-SHAPE | — | — | **主** | — | — | — |
| D-NOOUT | — | — | 协 | — | **协**（禁止无脚本通过） | **主** |
| D-CALIB | — | — | — | 协 | **主** | **协**（下游降权不够） |

### 根因三分法（本批）

| 类型 | 典型缺陷 | 结论 |
|------|----------|------|
| **Prompt/生成问题** | D-DEAD, D-STUB, D-WRONG, 部分 D-ENV | 模型仍输出「pytest 风格嵌套测试 / Stub / 自创 API」 |
| **Lint/Gate 没拦住** | D-CALIB, D-ENV, D-EXIST, D-SWALLOW, D-VACUOUS | ver3 文档已规划 L10/L4/FEATURE gate，**calib 产物显示门禁未真正挡住** |
| **规格 AC 本身差** | D-NARROW, 部分 D-EXIST | P1 把「有 aliases 属性」写成 must AC，诱导 existence 脚本 |

---

## 6. 优化方案（P0 → P2）

### P0-1 拒绝 ENV-only / 不对味校准失败

1. **问题**：`calibration_passed=true` 常因 `ModuleNotFoundError: pytest|sympy...`，而非 `AC-xxx FAIL`。  
2. **落点**：**P5** `calibration_gate` / `feature_calibrator`（协同 P4.5）。  
3. **改法（Gate 拒绝条件）**：
   ```python
   def is_intentional_ac_failure(stderr: str, issue_text: str) -> bool:
       if re.search(r"AC-\d+\s+FAIL|AssertionError:.*NOT_IMPLEMENTED", stderr):
           return True
       # 无关第三方：默认 reject
       if re.search(r"No module named ['\"]?(pytest|sympy)(\.|['\"]|$)", stderr):
           if "pytest" not in issue_text.lower() and "sympy" not in issue_text.lower():
               return False
       return False  # 再交给 symptom_aligner

   # calibration_passed 仅当 exit!=0 AND is_intentional_ac_failure AND lint.blocking==[]
   ```
4. **验收指标**：本 calib 中 D-ENV 代表 case（aiomonitor / gql / sqlfmt / psd-tools）再跑时 **`calibration_passed=false`**；失败原因字段含 `ENV_OR_SCRIPT_ERROR`。  
5. **优先级**：**P0**

### P0-2 Lint：死代码 AC + Stub + 落地 L10

1. **问题**：定义 `test_ac*` 不调用、或整段 `raise AssertionError("Stub for...")`，仍过校准。  
2. **落点**：**P4.5**（协同 P4 / P5）。  
3. **改法**：
   ```text
   L11-DEAD-AC (blocking):
     nested_or_toplevel = {name for FunctionDef name startswith test_}
     called = names used in Call nodes inside main() / module level (not inside those defs)
     if nested_or_toplevel and not called.intersection(nested_or_toplevel):
         FAIL "test functions never invoked"

   L12-STUB-AC (blocking):
     for each AC section: if body is only raise AssertionError and message matches /Stub for/i
        and no attribute access to project packages → FAIL

   L10-EXISTENCE-ONLY (blocking, 已规划):
     AC section whose asserts are only hasattr/callable/is not None → FAIL
     unless paired with behavioral assert in same section

   L13-VACUOUS-ASSERT (blocking):
     assert True / assert False 无条件 → FAIL
   ```
4. **验收指标**：D-DEAD / D-STUB 代表 case Lint blocking；INVALID 中这两类清零或不再 `calibration_passed`。  
5. **优先级**：**P0**

### P0-3 Prompt：强制可执行 AC 体 + 禁弱模式

1. **问题**：FEATURE Prompt 已写「勿 hasattr-only」，但生成仍出现死函数 / Stub / `assert True`。  
2. **落点**：**P4** `script_prompts_v3.py`（FEATURE/BUG 双 System）。  
3. **改法（可直接贴入 bullet）**：
   ```text
   - AC body MUST be inline under each `# --- AC-XXX ---` inside the scaffold-injected
     execution path. Do NOT define nested `def test_*` unless you also call them.
   - FORBIDDEN: `assert True`, unconditional `raise AssertionError("Stub for ...")`,
     bare `except Exception: pass` that skips the AC.
   - FORBIDDEN imports unless Issue mentions them: pytest, unittest.mock as hard dep,
     unrelated scientific stacks (e.g. sympy) when repo packages do not include them.
   - FEATURE: ≥1 happy-path behavioral assert AND ≥1 negative/conflict assert,
     each printing `AC-XXX FAIL` on failure.
   - Prefer repo sample_test_excerpt import style; if unsure, fail with
     AssertionError("AC-XXX FAIL: NOT_IMPLEMENTED") after catching AttributeError/ImportError
     of the *feature* symbol only.
   ```
4. **验收指标**：新生成脚本中「嵌套 test 未调用」率 → 0（抽样 20 题）；Stub-only 率 → 0。  
5. **优先级**：**P0**

### P1-1 P1 AC schema：禁止 existence 作 must

1. **问题**：如 adaptix AC-001「instance has aliases attribute」诱导 existence 脚本。  
2. **落点**：**P1 / contract_refiner**（协同 P1.6）。  
3. **改法**：
   - `acceptance_criteria.observable` 必须含 **动词化行为**（load/parse/raise/return），禁止sole `has`/`exists`/`callable`。  
   - validator：若 must AC 的 observable 匹配 `/(has(attr)?|exists?|callable)/i` 且无行为词 → 降为 should 或自动改写模板。  
   - repair_draft 增加 `behavioral_examples: [{input, expect}]` 字段供 P4 使用。  
4. **验收指标**：新 calib 中 must AC existence-only 占比 **< 10%**；D-EXIST 主标签 case 减少一半。  
5. **优先级**：**P1**

### P1-2 硬化 L4-SWALLOW + Feedback 闭环

1. **问题**：`except Exception: pass` / 宽捕获 TypeError 当「校验成功」仍出现。  
2. **落点**：**P4.5 L4** + **P4 feedback**。  
3. **改法**：L4 对 AC 段内 `except Exception` / `except (ValueError, TypeError, Exception)` 后仅 `pass` 一律 blocking；校准 feedback 模板明确：「Do not treat unexpected kwargs TypeError as validation success」。  
4. **验收指标**：mashumaro / tomlkit / vulture 类 swallow 在 Lint 被拦。  
5. **优先级**：**P1**

### P1-3 无产出硬闸（D-NOOUT）

1. **问题**：7 题无脚本或仅有 Issue；索引仍可能标 calib 未知/通过。  
2. **落点**：**agent 编排 + P5/P6**。  
3. **改法**：`repro_script.content` 为空或 preflight 未跑 → `calibration_passed=false` 且 `calibration_error=NO_SCRIPT`；可选 `block_search_on_calib_fail` 对 NO_SCRIPT 强制 true。  
4. **验收指标**：D-NOOUT case 不得进入「calibration_passed 计数」。  
5. **优先级**：**P1**

### P2-1 测偏 / 形状过度规格

1. **问题**：自创 `get_input_schema` / 错 Web 路由 / 强制 dict。  
2. **落点**：**P4 + P1.6**（协同 L9）。  
3. **改法**：User 模板强化 `sample_test_excerpt`；RepairDraft 只列 Issue 出现的符号；Lint 对「import 不在 top_level_packages」已有 L9，扩展到「调用属性名完全未在 Issue/excerpt 出现」的 warning。  
4. **验收指标**：adaptix/fastapi-deprecation 类 D-WRONG 在精读复审中降为次要。  
5. **优先级**：**P2**

### P2-2 覆盖收窄（D-NARROW）的规格侧

1. **问题**：44% case 标 Narrow；常因 P1 漏 negative/edge 或 P4 偷懒。  
2. **落点**：**P1 + P4**。  
3. **改法**：P1 对 FEATURE 强制产出 `ac_roles: {happy, negative, edge}` 各 ≥1；P4 User 表按 role 分列；缺 role → Lint warning `L14-ROLE-COVERAGE`。  
4. **验收指标**：PARTIAL 中「仅缺次要边角」可升 STRONG；Must 级 Missing 率下降。  
5. **优先级**：**P2**

---

## 7. 建议的回归评测集（缺陷探针）

改完 ver3 后，对下列 case **重跑 spec_parser → 再审计**，期望升档或主缺陷消失：

| # | TASK_ID | 探针缺陷 | 期望 |
|---|---------|----------|------|
| 1 | `aiomonitor-task-snapshots-diff` | D-DEAD + D-ENV + D-CALIB | Lint/Gate 拒；或生成可执行 AC 且失败为 AC FAIL |
| 2 | `sqlite-utils-safe-import-checkpoints` | D-DEAD | 不再「定义不调用」 |
| 3 | `python-statemachine-state-data-scoping` | D-DEAD + D-ENV | 同上 |
| 4 | `gql-incremental-graphql-delivery` | D-DEAD + D-ENV | 去 pytest；AC 执行 |
| 5 | `igel-persist-feature-schema` | D-STUB + D-CALIB | Stub 被 Lint 拦或换成真 API 断言 |
| 6 | `dateutil-rfc5545-timezone-interop` | D-STUB | 同上 |
| 7 | `sqlfmt-create-table-ddl-formatting` | D-ENV | 无 sympy；失败为 AC |
| 8 | `psd-tools-blend-range-api` | D-ENV | 同上 |
| 9 | `adaptix-name-mapping-aliases` | D-EXIST + D-VACUOUS | 无 hasattr 门闸；无 assert True |
| 10 | `bandit-structured-nosec-directives` | D-ENV（内容本不错） | 删无用 pytest 后应 ≥ STRONG |
| 11 | `mashumaro-flattened-dataclass-fields` | D-SWALLOW | L4 blocking |
| 12 | `narwhals-rolling-window-suite` 或 `skrub-duration-encoding` | D-NOOUT | 产出脚本或明确 NO_SCRIPT 失败 |

**金标正向对照（应保持 ≥ STRONG）**：`httpx-multipart-response-parsing`、`httpx-streaming-json-iteration`、`cattrs-partial-structuring-recovery`。

---

## 8. 风险与局限

1. **启发式 STRONG 可能高估**：`ipython` / `kombu*` / `mnamer` / `mobly` / `pwntools` 等报告偏结构信号，未统一精读 Oracle；其 D-NARROW 标签为保守附注。  
2. **未做统一 Oracle 双态**：本横截面基于单题审计 + calib buggy 态证据，**未**批量验证「golden patch 后 exit=0」。  
3. **`AUDIT_INDEX` 与磁盘判定略有漂移**：以各目录 `issue_script_match_audit.md` 的判定枚举为准（9/9/16）。  
4. **多标签重叠**：一题可同时 D-DEAD+D-ENV+D-CALIB；优化时应按「先结构、再语义」排序，避免只改 Prompt 不改 Gate。  
5. **不建议恢复 P2 AST 全家桶**：本批缺陷均可由 Prompt + Lint + Gate + AC schema 解释；静态 enrichment 不是主因。

---

## 9. 附录：全量 TASK_ID → 判定 → 主缺陷标签

| TASK_ID | 判定 | 缺陷标签 | 证据强度 |
|---------|------|----------|----------|
| adaptix-name-mapping-aliases | PARTIAL_MATCH | D-EXIST, D-VACUOUS, D-NARROW, D-WRONG, D-CALIB | 精读 |
| aiomonitor-task-snapshots-diff | INVALID_SCRIPT | D-DEAD, D-ENV, D-SWALLOW, D-WRONG, D-CALIB | 精读 |
| bandit-incremental-cache-control | INVALID_SCRIPT | D-NOOUT | 简报 |
| bandit-interprocedural-taint-checks | INVALID_SCRIPT | D-STUB, D-DEAD, D-CALIB | 精读 |
| bandit-structured-nosec-directives | PARTIAL_MATCH | D-ENV, D-CALIB, D-NARROW | 精读 |
| cattrs-partial-structuring-recovery | STRONG_MATCH | D-SHAPE | 精读 |
| dateutil-rfc5545-timezone-interop | INVALID_SCRIPT | D-STUB, D-CALIB | 精读 |
| fastapi-deprecation-response-headers | PARTIAL_MATCH | D-WRONG, D-EXIST, D-NARROW | 精读 |
| fastapi-implicit-head-options | PARTIAL_MATCH | D-EXIST, D-VACUOUS, D-NARROW | 精读 |
| gql-incremental-graphql-delivery | INVALID_SCRIPT | D-DEAD, D-ENV, D-CALIB | 精读 |
| httpx-multipart-response-parsing | STRONG_MATCH | （无明显主缺陷） | 精读 |
| httpx-streaming-json-iteration | STRONG_MATCH | （无明显主缺陷） | 精读 |
| igel-persist-feature-schema | INVALID_SCRIPT | D-STUB, D-CALIB | 精读 |
| ipython-session-bundle-replay | STRONG_MATCH | D-NARROW | 启发式 |
| kombu-single-active-consumer-priority | STRONG_MATCH | D-NARROW | 启发式 |
| kombu-virtual-queue-dead-lettering | STRONG_MATCH | D-NARROW | 启发式 |
| koota-entity-snapshot-rollback | INVALID_SCRIPT | D-NOOUT | 简报 |
| langchain-request-coalescing | INVALID_SCRIPT | D-NOOUT | 简报 |
| mashumaro-flattened-dataclass-fields | PARTIAL_MATCH | D-SWALLOW, D-NARROW | 启发式 |
| mnamer-daemon-watch-lifecycle | STRONG_MATCH | D-NARROW | 启发式 |
| mobly-grouped-test-barriers | STRONG_MATCH | D-NARROW | 启发式 |
| narwhals-rolling-window-suite | INVALID_SCRIPT | D-NOOUT | 简报 |
| numba-stencil-boundary-modes | INVALID_SCRIPT | D-NOOUT | 简报 |
| psd-tools-blend-range-api | INVALID_SCRIPT | D-ENV, D-CALIB | 启发式 |
| pwntools-tube-multiplexing | STRONG_MATCH | D-NARROW | 启发式 |
| python-statemachine-state-data-scoping | INVALID_SCRIPT | D-DEAD, D-ENV, D-CALIB | 启发式 |
| returns-validated-error-accumulation | PARTIAL_MATCH | D-EXIST, D-NARROW | 启发式 |
| skrub-duration-encoding | INVALID_SCRIPT | D-NOOUT | 简报 |
| sqlfmt-create-table-ddl-formatting | INVALID_SCRIPT | D-ENV, D-CALIB | 启发式 |
| sqlite-utils-safe-import-checkpoints | INVALID_SCRIPT | D-DEAD, D-CALIB | 启发式 |
| textual-kitty-key-phases | PARTIAL_MATCH | D-EXIST, D-NARROW | 启发式 |
| textual-richlog-follow-state | INVALID_SCRIPT | D-NOOUT | 简报 |
| tomlkit-toml-table-converters | PARTIAL_MATCH | D-EXIST, D-SWALLOW, D-NARROW | 启发式 |
| vulture-persistent-analysis-cache | PARTIAL_MATCH | D-EXIST, D-SWALLOW, D-NARROW | 启发式 |

---

## 结语（给 ver3.0 实施的一句话）

本批 calib 证明：**「能 fail」已被 P5 粗门禁满足，但「fail 得对、测得全、生成结构可执行」尚未被 P4 Prompt + P4.5 Lint + P5 语义 Gate 闭环**；优先落地 **ENV/Stub/Dead-AC 拦截** 与 **existence AC 治理**，再追求 PERFECT_MATCH 覆盖率。
