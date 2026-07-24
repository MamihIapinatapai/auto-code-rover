# Spec Parser ver3.5 优化设计计划

| 项 | 值 |
|----|-----|
| 项目 | AutoCodeRover — 规范解析智能体（Module 1） |
| 基线版本 | **v3.4.0**（Contract-First 骨架已通；Renderer 假脚本为主溃点） |
| 目标版本 | **v3.5.0** |
| 文档性质 | **优化计划 / 实现规格草稿**（施工前可再升 FINAL；冲突时以本文 §2 决策与 §4–§5 FROZEN 为准） |
| 状态 | `3.5.0-DRAFT.7` |
| 修订日期 | 2026-07-24 |
| 题单（回归） | `conf/deepswe_python_tasks_v3.1_probes.txt`（15 题） |
| 实证输入 | [v3.4_test_results_summary.md](./v3.4_test_results_summary.md) · [v3.4_problem_checklist.md](./v3.4_problem_checklist.md) · [v3.4_llmrev_test_results_summary.md](./v3.4_llmrev_test_results_summary.md) |
| 基线设计 | [spec_parser_ver3.4_design_FINAL.md](./spec_parser_ver3.4_design_FINAL.md) |
| 工作汇总 | [work_report_spec_parser_v2_to_v3.4.md](./work_report_spec_parser_v2_to_v3.4.md) |

---

## 0. 一句话与主链路

**3.5 一句话**：把「假印刷机 + 假绿交卷」拆掉，改成 **仓库真实用法挖掘 → 真调用渲染 → 失败必须来自产品 → 印不成只交契约、不盖及格章**。

```text
γ 仓库挖掘  →  漏斗候选 + 并行采集 + Recipe 全程约束
              → 得到可印刷的 usage_snippets[]（真 API + 调用闭包）
        ↓
α 真印刷机  →  方案 A：CallPlan 绑定 + 字符串三段排放（不发明用法）
        ↓
δ 失败语义  →  三层执法 + SUT 第三方包算产品 Call + α/δ 自检 DRY + evidence 缺失默认态
        ↓
β 产物分层  →  降级序 + free_fallback(1b) + PersistGuard；下游只认正式 test_feature.py
```

**相对 3.4 的战略转向**：停止把「语义 LLM 审查」和「再填更多表字段」当主旋钮；主旋钮是 **可执行渲染 + 用法燃料 + 交卷诚实**。

**γ 结构原则（DRAFT.2）**：不做「L1 不够再挖 L2」的纯瀑布；改为 **L0 漏斗播种 → 有预算并行采集 → 统一融合排序 → sufficiency 停扫**。Recipe 既是 L0 种子，也是终态一票否决与印刷最高优先，不只是末闸滤网。

**α 结构原则（DRAFT.3→4）**：**方案 A（字符串模板填槽）** — 印刷机 **不发明用法**；只把 Recipe.`emit_template` / γ 显式占位 `call_pattern` **绑定**到契约 `inputs`/`expect` 并三段排放。禁止印刷阶段调 LLM；禁止对任意标识符子串替换；**档 3 签名弱印默认关闭**；类型/arrange 缺口宁可 `blocked` 不可假跑。AST 仅允许 Bind 辅助的「单末级 Call 改参」与自检，整文件 AST 拼装（方案 B）留作 3.5.1+。

**δ 结构原则（DRAFT.5→7）**：**红/绿语义必须诚实** — 伪造失败与伪造通过硬拦；弱绿允许交卷但必须打标、禁止假 raise 凑红。静态 EG 与 α 自检 **只经** `check_failure_semantics`；EG-02/03 以 **产品 Call** 为准（黑名单 + 符号启发 + **SUT 顶层包/已安装第三方**）；provenance 防误杀；evidence 缺失 ≠ EG-06 通过；有产品 Call 的弱断言 ≠ stub_pass。LLM 审失败真实性不进主路径（D3/D7）。

**β 结构原则（DRAFT.6→7）**：**交卷诚实 = 降级序 + free_fallback + PersistGuard** — 池空时可至多 1 次自由补生成；有 EG 合法候选优先落可执行卷；否则 BC 过才 `contract_only`；**下游/金标只认** `output_dir/test_feature.py`。废除「有表即可 s1」。审查拒收禁止空手（D2/D8）。
---

## 1. 基线问题（设计输入）

### 1.1 双口径（v3.4 关审查探针）

| 口径 | v3.4.0 | 含义 |
|------|--------|------|
| 磁盘有脚本 | 14/15 | 有文件 ≠ 金标 |
| `calibration_passed` | 8/15 | buggy 能挂；契约假桩会污染 |
| `s1_accept` | 6 | **≠ 可用金标**（当前常为假卷） |
| 卷面 PERFECT / STRONG / PARTIAL / INVALID | 0 / 3 / 5 / 7 | **主口径** |

### 1.2 主溃点定性（反常识）

| 表面现象 | 真实根因 |
|----------|----------|
| `result = None # invoke` | **`behavior_skeleton.py` 故意输出占位**，不是 LLM 偶发写坏 |
| Recipe 无效 | 卡只写入 `# hint` 注释，**从未展开** `call_graph_template` |
| 表审 pass、脚本仍桩 | 审查审表/软警告，**拦不住打印机** |
| `s1_accept` 批量 INVALID | `degraded_or_uncalib_s1_kept`：**有表即可交假卷** |
| 开审查卷面更差 | 假卷未清又撕掉较强自由稿（无降级交卷） |

**判决**：Contract-First 骨架「填表 → 渲染 → 落盘」已接通；缺的是 **IR→可执行代码的真编译**，以及 **交卷门禁与失败语义的诚实性**。

### 1.3 问题 ID → 3.5 工作包

| v3.4 ID | 人话 | 3.5 工作包 |
|---------|------|-----------|
| V34-P0-1 | 打印机假卷 | **WP-α** Real Renderer |
| V34-P0-2 | 假卷仍 s1_accept | **WP-β** + **WP-δ** |
| V34-P0-3 | 审严后空手 | **WP-β** 降级交卷（审查策略见 §2.3） |
| V34-P0-4 | 填表 JSON 崩 | **WP-β** contract_crash 收尾 + 轻量容错 |
| V34-P1-1 | Recipe 不作用于自由路径 | **WP-γ** 双路径注入 + 门禁 |
| V34-P1-2/3 | 表审/SCC-L 与假桩脱节 | **WP-δ** 机器硬拦优先于 LLM |
| V34-P1-4 | DraftPicker 过宽 | **WP-β** |
| V34-P2-* | 弱断言等 | **延后**；假脚本清零后再做 |

---

## 2. 决策集（FROZEN）

> 本节为 ver3.5 **已拍板**决策，实现不得再争论「要不要」；只允许讨论「怎么落地」。D1–D8 冲突时以编号较大且专指该子系统的条款为准（如交卷落盘以 D8 细化为准）。

### 2.1 决策 D1 — 测试文件可否挖掘？

| 项 | 决议 |
|----|------|
| **决议** | **允许从测试文件挖掘调用形态（Call-shape only）** |
| **允许** | `import` 路径、构造/调用链、参数关键字名、层入口写法（如 `Retort(recipe=[...]).load(...)`） |
| **禁止** | 复制 `assert` 期望值、官方测试意图原文、Harbor 隐藏测、`solution.patch` 相关答案 |
| **实现约束** | AST 抽取时：**保留 Call / Attribute / 赋值编排；丢弃 Assert / 带期望字面量的比较**；落盘字段不得含 `assert_source` |
| **来源优先级（排序用，非严格瀑布）** | 融合排序时：`examples/可解析 docstring` ≥ `business_call` ≥ `test_call_shape` ≥ `readme` ≥ `anchor_only`；README 默认不超过 medium，除非同时满足 Recipe required |
| **采集形态** | **并行采集 + 统一排序**（见 §5.1.2）；禁止无 L0 候选时全仓盲扫 |
| **相对 3.4 O4** | 修订 3.4「禁止读 pytest 金标目录」为：**禁止读断言意图；允许读调用形态**。硬约束「不注入官方测试断言意图」仍然成立 |

**理由**：许多库的真实用法只稳定出现在 tests；完全禁止会让 γ 在探针集上饿死。Call-shape 提供编排，expect 仍只来自 Issue/`issue_quote`，避免背答案。纯瀑布「文档不足再下沉 AST」易超时且噪声大； sufficiency 以「可印刷 call_pattern」为准，不以「文档字数」为准。

### 2.2 决策 D2 — `s1_accept` 语义

| 项 | 决议 |
|----|------|
| **决议** | **保留动作名 `s1_accept`，收紧语义** |
| **新语义** | 仅当脚本通过 **Executableity Gate（可执行性门禁）** 后，才允许 `final_action=s1_accept` |
| **新增动作** | `contract_only`：契约 **BC 过** 且无 EG 合法可执行候选时 → **只落盘 `behavior_contract.json` + 原因**；正式路径 **无** `test_feature.py`（详见 PersistGuard / D8） |
| **废除** | **删除** `degraded_or_uncalib_s1_kept` 全部分支；「有 `behavior_contract.items`」**不得**再触发 s1 |
| **`forbid_no_script_if_s1_ok`** | 修订：**仅当**已存在 EG 过的可执行候选时，禁止无意义地选 `no_script`；**≠**「有表就算 S1 ok」 |
| **弱绿** | F-weak-green 允许 `s1_accept`，但必须落盘 `weak_green=true`；**不得**计入金标/STRONG KPI |
| **与 calib 关系** | `s1_accept` **不要求** `calibration_passed`；但要求：非 stub 假绿、非 synthetic、存在产品 Call。`calib_pass` 仍为更优档 |
| **降级序** | 见 **D8**（优先自由/契约 EG 合法稿，再 `contract_only`，最后 `no_script`） |

**Executableity Gate（最小集，FROZEN）** — 细则与检测算法见 **§5.3 / D7**。

| 规则 ID | 条件 | 结果 |
|---------|------|------|
| EG-01 | 出现 `result = None  # invoke` 或等价注释桩 | **拒** → 不得 s1_accept |
| EG-02 | AC 段无 **产品 Call**（见 §5.3.3 黑名单/启发） | **拒** |
| EG-03 | `pytest.raises` 块内无产品 Call / 仅自抛任意异常 / 过宽 Exception 无 Call | **拒** |
| EG-04 | 无产品 Call 的 `NOT_IMPLEMENTED` / empty fail（含 L14） | **拒** |
| EG-05 | Recipe 命中但 `recipe_compliance=false` | **拒**（探针卡 blocking） |
| EG-06 | `failure_provenance` 为 stub_pass / synthetic（非 unknown） | **拒** |

### 2.3 决策 D3 — 本阶段是否动语义审查？

| 项 | 决议 |
|----|------|
| **决议** | **3.5.0 主路径默认关闭表 LLM 复审与 SCC-L**（保持代码开关，默认 off） |
| **禁止** | 把「打开/加严语义审查」列为 3.5 主优化手段或毕业条件 |
| **允许** | 假脚本簇清零后的 **可选消融跑**（`high_risk_only` / warning-only）；须单独报告，不计入 3.5 主对照账本 |
| **若开消融** | 拒收后必须走 **D8 降级序**（先 EG 合法 best-of，再 `contract_only`），**禁止空手**（修 V34-P0-3） |

**理由**：v3.4 开审查对照已证明接线有效但卷面不升、STRONG 回退；在假打印机未拆前加质检是沉没成本。

### 2.4 决策 D4 — γ UsageMiner 结构形态

| 项 | 决议 |
|----|------|
| **决议** | **采用「L0 漏斗 + 并行采集 + 统一融合」**；不采用「L1 文档不足再严格下沉 L2/L3」的纯瀑布 |
| **Recipe 双角色** | **播种**（强制入 L0 + `recipe_seed`）+ **硬闸**（forbidden drop / required 升权）+ **印刷最高优先** |
| **成功标准** | sufficiency 以是否具备 **可印刷** `call_pattern`+`import_path`（或 Recipe 可独立展开）为准，不以文档字数/片段条数为准 |
| **L3 签名** | 仅作 Prompt 附件（`confidence=low`）；**默认不作 α 印刷燃料**（档 3 开关默认关，见 D5/§5.2.6） |
| **时序** | γ 在契约填表与自由生成之前完成；不得依赖已填 `call_graph` |
| **预算** | 禁止无 L0 全仓盲扫；必须符号反查 + 文件/节点/超时上限；够印即停 |

**理由**：瀑布易超时且用「更多字」伪装进度；印刷机需要的是少量可执行调用闭包。详见 §4.3 / §5.1。

### 2.5 决策 D5 — α Real Renderer 架构形态

| 项 | 决议 |
|----|------|
| **决议** | **采用方案 A：CallPlan 绑定 + 字符串三段排放（imports / arrange+act / oracle）** |
| **角色** | 印刷机 **不发明用法**；用法只来自 Recipe.`emit_template` 或 γ `printable` snippet；期望只来自契约 `oracle_kind`+`expect` |
| **API** | `render_s1_script(...) -> RenderResult`；`ok=false` 时 **零假桩字符**，交 β `contract_only` |
| **多 AC** | 3.5.0 **All-or-nothing**：任一 must Bind 失败 → 整题 `render_blocked` |
| **档 2 重绑定** | **仅显式占位** `__SLOT_{key}__`（见 §5.2.5）；禁止任意标识符子串替换 |
| **档 1 槽位** | Recipe `slots_from_inputs` 与填表 `inputs` **契约闭合**（见 §5.2.4）；α 不改表，填表必须被槽位约束 |
| **arrange / 类型** | 按 §5.2.5a 优先级补强；未绑定 Name → blocked，禁止为跑通退回 `NOT_IMPLEMENTED` |
| **档 3** | **`enable_bind_mode_signature` 默认 False**（见 §5.2.6）；主 KPI 不以档 3 成功率为指标 |
| **禁止** | 印刷阶段调 LLM 润色；用 `call_graph` 字符串硬拼无 import 的调用；保留 `NOT_IMPLEMENTED` 凑红；部分 must 印桩 |
| **延后** | 方案 B（整文件 AST 拼装再 unparse）→ 3.5.1+；方案 C（LLM 整段写卷）→ **不做主路径** |
| **允许的窄 AST** | Bind：无占位时「单一末级 Call」改参；Emit 后自检 `ast.parse` — **均不算方案 B 主路径** |

**理由**：先闭合假脚本主溃点；字符串填槽可控可测；DRAFT.4 补齐重绑定/槽位/arrange/档 3 四条技术债，避免「语法对、语义错」比假桩更难查。详见 §5.2。

### 2.6 决策 D6 — 档 1/2 绑定与填表闭合（FROZEN）

| 项 | 决议 |
|----|------|
| **占位符** | 全局唯一格式：`__SLOT_{key}__`（避免与 f-string / `{data}` 字典字面量冲突） |
| **γ 职责** | 入库 `call_pattern` 时将可替换实参归一为占位；`printable=true` 须满足 §5.2.5 可印刷前提 |
| **填表职责** | 命中 `recipe_id` 时强制注入该卡 `slots_from_inputs` + `slot_aliases`；缺槽尽量在 BC/回填阶段失败，勿拖到 α 才爆 |
| **原因码** | `MISSING_SLOT`（键缺失）与 `RECIPE_UNSAT`（展开后触 forbidden / required 失败）分离；另增 `UNBOUND_NAME` |
| **闭环** | 3.5.0 假脚本主闭环 = **档 1 + 档 2 + blocked**；不依赖档 3 |

### 2.7 决策 D7 — δ 失败语义三层执法（FROZEN）

| 项 | 决议 |
|----|------|
| **决议** | **采用「失败分类学 + 静态 EG 引擎（主）+ 运行时 provenance（辅）」**；LLM 审失败真实性 **不进** 3.5.0 主路径 |
| **分类** | 必须区分 F-product / F-synthetic / F-stub-pass / F-env / F-weak-green（见 §5.3.1）；δ **主责** synthetic 与 stub-pass |
| **DRY** | `check_failure_semantics(script)` **唯一实现**；α Emit 自检与 `script_linter` **共用**（禁止双标准） |
| **静态** | EG-01…05 为 blocking；L14 为 EG-04 子集，blocking **并集** |
| **产品 Call** | EG-02/03：**非产品 Call 黑名单** + 符号启发 + **SUT 顶层包名 / Anchor 模块 / 已安装第三方 SUT**（不要求源码必在 repo 树内，见 §5.3.3） |
| **raises** | `pytest.raises` 块内 **必须 ≥1 产品 Call**；块内仅自抛任意异常 → blocking |
| **运行时** | `failure_provenance` + **`per_ac_provenance`**；整题聚合：任一 AC 为 synthetic/stub_pass → 不得 calib/s1；EG-06 消费 |
| **provenance 防误杀** | 「无产品包帧」单独 **不得**一票标 synthetic；优先显式 NOT_IMPLEMENTED / 无 Call；否则 `unknown` |
| **evidence 缺失** | sandbox 未跑或字段缺失 → `provenance=missing`（可归一为 `unknown`）；**不得**视为 EG-06 通过；**不得**据此 `calib_pass` |
| **弱断言 vs stub** | 有产品 Call 后的存在性/callable 弱断言 **≠** stub_pass；可 `weak_green` 或交弱断言 P2，**不得**用 EG-02 当断言强度门 |
| **α 自检** | Emit 后 **只调用** `check_failure_semantics`；禁止另写「源码字符串含 NOT_IMPLEMENTED 即拒」的独立文本禁令 |
| **弱绿** | 允许 EG 过的 `s1_accept`；必须 `weak_green=true`；**禁止**回补假 raise；**不计入**金标 KPI |
| **产品 NotImplementedError** | 按 traceback **帧位置**判 product，不得仅因异常名含 NotImplemented 判 synthetic |
| **表侧** | `raises` 默认禁止裸 `Exception`（除非 issue_quote 支持）；见 §5.3.5 |
| **自由路径** | 入选稿必须过 **完整 EG-01…05**；有 provenance 时 EG-06 同样生效（与契约路径同一标准） |
| **分期** | S1–S3：静态 EG 即可拒假桩并约束交卷；S4 起 provenance/EG-06 必达，方可版本毕业 |

**理由**：DRAFT.7 补齐第三方 SUT 产品 Call、α/δ 自检单一入口、evidence 缺失默认态与弱断言边界。详见 §5.3。

### 2.8 决策 D8 — β 产物分层与降级/落盘纪律（FROZEN）

| 项 | 决议 |
|----|------|
| **决议** | **交卷由「降级序 + PersistGuard」共同决定**；禁止含糊的「contract_only 或 best-of」 |
| **降级序** | 见 §5.4.0（含 **步骤 1b free_fallback**）；审查拒收 / render_blocked / EG 失败 **一律先回看** EG 合法候选，池空可补 1 次自由生成 |
| **PersistGuard** | 正式 `test_feature.py` **仅**在入选 `calib_pass`/`s1_accept`/`persist` 时写入；失败稿进 `artifacts/rejected/` 或不写 |
| **下游读盘** | **金标/下游模块只认** `output_dir/test_feature.py`（及 report 中 `official_script_path`）；`artifacts/rejected/**` **仅审计**，不得当交卷 |
| **可执行交卷集合** | ART：`final_action ∈ {calib_pass, s1_accept, persist}` ⇒ 正式路径有脚本且 EG 过；KPI 仍可拆开统计 |
| **`contract_crash`** | **中间原因码**，不是 final_action；BC 未过不得冒充 `contract_only` |
| **DraftPicker** | 分数序见 §5.4.3；EG 失败分 = −∞；`weak_green` 低于非弱绿 s1 |
| **旧策略** | 代码路径删除 `degraded_or_uncalib_s1_kept`；配置语义见 D2 |

**理由**：DRAFT.7 补 free_fallback（防 stub→契约后池空过多 contract_only）与下游读盘约定。详见 §5.4。

---
## 3. 目标与非目标

### 3.1 目标（可验收）

1. **γ**：每题产出 `usage_snippets.json`：真 API 名 + **可印刷** `call_pattern`/`import_path` + 置信度；含 sufficiency 判定与 Recipe 对齐结果。  
2. **α（方案 A）**：`render_s1_script` → `RenderResult`；经 CallPlan Bind 后三段排放真实 `import` + Call + oracle；探针 Recipe 卡具备可机械展开的 `emit_template`；不得退回假桩。  
3. **δ（D7）**：落地失败分类 + `check_failure_semantics`（EG-01…05，含产品 Call 定义）+ `failure_provenance`/`per_ac_provenance`（EG-06）+ `weak_green` 审计；伪造红/假绿不得 calib_pass / s1_accept；弱绿禁止假 raise 凑红。  
4. **β（D8）**：降级序（含 free_fallback 1b）+ PersistGuard；下游只认正式脚本；`s1_accept` ↔ EG + provenance；废除宽 s1；禁止假绿正式交卷与审查空手。  
5. **双路径**：自由路径与契约路径共享 γ 摘要；Recipe/挖掘 forbidden 对自由路径生效；**入选稿过完整 EG-01…05（及可用时 EG-06）**。  
6. **KPI**：主看「假脚本 INVALID 簇↓」「EG 通过率」「WRONG_LAYER↓」「可印刷 snippet 覆盖率」「档 1/2 Bind 成功率」「synthetic/stub_pass→0」；**单独统计** `weak_green` 率；不以「磁盘有脚本数」「开审查」「档 3 成功率」「calib 绝对数」「s1_accept 计数当金标」为主。

### 3.2 非目标（3.5.0 明确不做）

| 不做 | 原因 |
|------|------|
| 以语义审查抬卷面 | D3 |
| 完整 S2/S3 字段集强制 | 仍属后置；先闭合 S1 可执行 |
| 默认依赖 patched-pass / solution.patch | 硬约束不变 |
| 追求 15 题 PERFECT | 新功能/复杂题允许 `contract_only` 或 PARTIAL |
| 全仓库调用图 / Tier3 深挖 | 缺的是用法片段，不是更深符号表 |
| 无 L0 候选时全仓盲扫 AST | 成本爆、命中率差；必须符号反查 + 预算 |
| 重写整条自由生成模型 | 用 γ 燃料 + 门禁即可 |
| α 主路径整文件 AST 拼装 / LLM 整段写卷 | D5：方案 A 先行；B/C 非 3.5.0 主路径 |
| 默认开启档 3 签名弱印 | D5/D6：WRONG_LAYER 温床；与 D4 冲突 |
| 从仓库自动拖完整 Model/测试 fixture 定义 | 范围膨胀；用 arrange 窄版即可 |
| 对任意标识符做子串重绑定 | 误伤 `data`⊂`database`；见 §5.2.5 |
| LLM 审「失败是否真实」作主路径 | D3/D7；假失败用机械 EG |

### 3.3 设计红线（禁止再走）

| 红线 | 原因 |
|------|------|
| 保留 `None # invoke`「先保证有文件」 | 直接制造 INVALID 金标 |
| 用 `raise NOT_IMPLEMENTED` 保证 calib 红 | 失败语义造假；可与 Exception 自抛自接假绿 |
| 有 `behavior_contract.items` 就 s1_accept | KPI 倒置 |
| 审查拒收后无降级 → no_script | 产能破坏（aiomonitor 回归） |
| 把官方测试 assert 写入 expect | 金标污染 |
| 以「挖到更多文档字」代替「可印刷 call_pattern」 | γ 空转；印刷机仍假桩或乱猜 |
| Recipe 仅作末闸、不参与 L0 播种/排序 | 高频错误用法污染 call_graph |
| 印刷阶段 LLM 补全调用 / 多 snippet 随机选 | 不可回归；测错层 |
| Bind 失败仍输出装饰性脚本 | 违反 D2/D5；必须 `render_blocked` |
| 标识符子串替换充当「重绑定」 | 语义错且难查（DRAFT.4） |
| 为消除 NameError 退回 `NOT_IMPLEMENTED` | 违反 δ；应 `UNBOUND_NAME` blocked |
| 填表不受 Recipe 槽位约束却指望档 1 成功 | 档 1 名存实亡 |
| α 自检与 linter 两套 EG 标准 | 双标准漏拦（D7 DRY） |
| 仅因源码出现 `NOT_IMPLEMENTED` 字符串就拒 | 误伤注释/产品 `NotImplementedError` |
| 为消灭 F-weak-green 回补假 raise | 破坏 δ 铁律 |
| 把 `s1_accept`（含弱绿）当 STRONG/金标 | KPI 再次倒置 |
| EG 失败 / render_blocked 不回看自由 best-of 直接空手 | 违反 D8 / V34-P0-3 |
| 静态 EG 未过就写入正式 `test_feature.py` 并保留 | ART 与 contract_only 冲突 |
| 用 `print`/`mock`/`type` 等冒充产品 Call 过 EG-02 | 漏拦假绿 |
| 仅认 repo 树内路径、误杀已安装第三方 SUT 调用 | 产品 Call 定义过窄（DRAFT.7） |
| α 另写「字符串含 NOT_IMPLEMENTED 即拒」绕过 δ | 双标准；误伤注释/类名 |
| stub→契约后池空直接 contract_only、不做 free_fallback | 过多空手/无强自由稿（D8 1b） |
| 下游读取 `artifacts/rejected/` 当金标 | 违反正式路径约定 |

---

## 4. 架构与数据流（FROZEN 语义）

### 4.1 端到端

```text
Issue + Repo
    │
    ├─ ScriptAnchor（3.3.1 保留：符号/签名）
    ├─ γ UsageMiner（填表前；漏斗 + 并行采集，见 §4.3 / §5.1）
    │       └─ usage_snippets[] + sufficiency + format_for_prompt()
    │
    ├─ 自由路径 ──► Prompt(+γ+Recipe) → 完整 EG → calib → provenance → 候选池
    │
    └─ stub/拒识 → 契约路径
            ├─ fill BehaviorContract（Prompt 注入 γ + **Recipe 槽位表**）
            ├─ validate_contract（BC + Recipe；缺槽可机械拒）
            ├─ α Bind→CallPlan → Emit（方案 A）
            │       ├─ RenderResult.ok → check_failure_semantics →（PersistGuard 暂缓正式写盘）
            │       │         → sandbox → provenance / weak_green → 候选池
            │       └─ RenderResult.blocked → 不写正式脚本；进降级序
            └─ β D8 降级序（候选池 ∪ contract_only ∪ no_script）
                    calib_pass | s1_accept | persist | contract_only | no_script
```

**时序约束（FROZEN）**：γ **在契约填表之前**完成；γ **不得**依赖已填的 `call_graph`（防循环依赖）。填表应将 `call_graph` / `recipe_id` / **槽位 inputs** **优先约束为** snippets / Recipe 种子，而非先自由填再指望印刷机纠正。  
**α 约束（FROZEN）**：印刷机 **不**在 Emit 阶段扫仓库或调 LLM；只消费已绑定的 `CallPlan`。  
**δ 约束（FROZEN）**：静态 EG 与 α 自检共用 `check_failure_semantics`；运行时 provenance / `weak_green` 在 sandbox 后写入 evidence，供 β/EG-06 消费（见 §5.3）。  
**β 约束（FROZEN）**：正式落盘服从 PersistGuard；`render_blocked` **与**「Emit 成功但 EG/provenance 失败」**同等**进入 D8 降级序（先回看池 → **1b free_fallback** → contract_only）；下游只认正式 `test_feature.py`。

### 4.2 产物落盘约定

| 产物 | 何时 | 含义 |
|------|------|------|
| `behavior_contract.json` | 契约路径 BC 成功 | Layer-0：理解/期望 |
| `behavior_contract.partial.json`（可选） | `contract_crash` 且仍有残表 | **不算** `contract_only`；审计用 |
| `usage_snippets.json` | γ 跑完（建议每题都有） | 用法燃料审计；含 `sufficiency`、候选漏斗摘要 |
| `test_feature.py` | **仅** PersistGuard 放行的入选终态 | Layer-1：可执行卷；**唯一官方交卷路径** |
| `official_script_path`（run report 字段） | 收尾 | 指向正式 `test_feature.py` 或空；下游只认此字段 |
| `artifacts/rejected/rN_test_feature.py` | EG/provenance 失败或未入选 | **仅审计**；**禁止**下游/金标消费 |
| `execution_evidence.json`（或并入既有 evidence） | sandbox 后 | 含 `failure_provenance` / `per_ac_provenance` / `weak_green` / `synthetic_fail` / `stub_unexpected_pass` |
| `script_decision_trace.json` | 有决策 | 含降级序步骤、`render_blocked` / `contract_only` / EG / provenance |
| `artifact_consistency.json` | 收尾 | `s1_accept`/`calib_pass` ⇒ 正式脚本存在且 EG 一致；`contract_only` ⇒ 正式路径无 `test_feature.py` |

### 4.3 γ UsageMiner 数据流（FROZEN 结构）

> 相对早期「L1→L2→L3 瀑布下沉」草稿：**改为漏斗 + 并行采集 + 统一融合**。层号仅表示逻辑角色，不是强制串行阶段门。

```text
Issue / Recipe / Anchor
        │
        ▼
┌─ L0 候选漏斗 ─────────────────────────────────────┐
│ Issue∩Anchor ∪ Recipe.forced ∪ entrypoints          │
│ + Recipe required 形态作为「种子 pattern」            │
│ tier: recipe_forced > issue_named > anchor_hit      │
│ （无 L0 → 禁止全仓盲扫；仅可 anchor_only / blocked） │
└───────────────────────┬───────────────────────────┘
                        ▼
┌─ 并行采集（有预算；可按 sufficiency 提前停）──────────┐
│ A. examples / docstring / doctest（可解析 call 行）   │
│ B. 业务 Call-shape（按符号反查调用点，非全仓 walk）   │
│ C. 测试 Call-shape only（D1；丢 Assert）              │
│ D. Anchor signature + import（始终可作 low 附件）     │
│ E. README/*.md 代码围栏（默认可解析才入库；否则 hint） │
└───────────────────────┬───────────────────────────┘
                        ▼
┌─ 融合 / 排序 / Recipe 硬约束 ───────────────────────┐
│ 1) Recipe forbidden → drop（一票否决）               │
│ 2) required 满足 → 升权；未满足 → drop 或封顶 low   │
│ 3) source 序：examples≥business≥test≥readme≥sig     │
│ 4) 按规范化 call_pattern 聚类去重；每 api top-k(2–3) │
│ 5) sufficiency：是否已有「可印刷」燃料？够则停扩扫   │
└───────────────────────┬───────────────────────────┘
                        ▼
              usage_snippets[]
                 ├─ 契约 fill Prompt（high/medium 优先）
                 ├─ α Real Renderer（按 §5.2.1 印刷序）
                 └─ 自由路径 Prompt + lint（forbidden/required）
```

---

## 5. 工作包详设

### 5.1 WP-γ — UsageMiner（仓库真实 API 挖掘）

**模块**：新建 `app/spec_parser/usage_miner.py`（可小幅扩展 `script_anchor.py` / `recipe_loader.py`）。

**定位**：契约填表与自由生成之前的 **用法燃料层**。成功标准不是「挖到文档」，而是产出 **可被 α 印刷机消费** 的 `import_path` + `call_pattern`（或明确 `sufficiency=insufficient` 供 β `contract_only`）。

#### 5.1.1 输入 / 输出

**输入**：`repo_path`、`issue_text`、`ScriptAnchor`（可选）、已命中 `recipe_cards`、扫描预算（文件数 / AST 节点 / 超时）。

**输出**（schema，FROZEN 最小字段）：

```json
{
  "task_id": "...",
  "candidate_funnel": {
    "recipe_forced": ["Retort", "name_mapping", "load"],
    "issue_named": ["..."],
    "anchor_hit": ["..."]
  },
  "sufficiency": "printable|prompt_only|insufficient",
  "sufficiency_reason": "has_medium_call_pattern|recipe_expandable|sig_only|no_l0|ambiguous",
  "snippets": [
    {
      "snippet_id": "u1",
      "api_name": "adaptix.Retort.load",
      "import_path": "from adaptix import Retort, name_mapping",
      "signature": "(self, data, tp)",
      "call_pattern": "Retort(recipe=[name_mapping(__SLOT_name_mapping_args__)]).load(__SLOT_data__, __SLOT_model__)",
      "slot_keys": ["name_mapping_args", "data", "model"],
      "layer_hint": "lib",
      "source_kind": "test_call_shape|examples|readme|docstring|business_call|anchor_only|recipe_seed",
      "source_path": "relative/path.py",
      "source_lineno": 12,
      "confidence": "high|medium|low",
      "printable": true,
      "bind_ready": true,
      "forbidden_nearby": ["Retort(name_mapping="],
      "recipe_id": "adaptix.name_mapping",
      "recipe_aligned": true
    }
  ],
  "summary_for_prompt": "..."
}
```

**字段语义（关键）**：

| 字段 | 含义 |
|------|------|
| `printable` | 具备可解析 `import_path` + 可被 α 合法重绑定的 `call_pattern`；**仅 `printable=true` 可进 α 档 2** |
| `bind_ready` | `call_pattern` 已含 `__SLOT_*__` 占位，**或**满足「单一末级 Call + 签名可对齐」窄路径（§5.2.5）；`printable` 蕴含 `bind_ready` |
| `slot_keys` | pattern 中出现的槽名列表，供填表/审计 |
| `sufficiency=printable` | 已够印：≥1 条 medium+/printable，或 Recipe **`emit_template` 可独立展开** |
| `sufficiency=prompt_only` | 仅有 low / 签名 / 冲突未锁定 → 可填表，印刷默认 `render_blocked` 风险高 |
| `sufficiency=insufficient` | 无 L0 或无任何可用燃料 → 显式 `NO_USAGE_FUEL` |
| `recipe_seed` | 由 Recipe `call_graph_template` / required 合成的种子 pattern（可无仓库命中） |

缺 `call_pattern` 的纯文档摘要：**不得**标 `printable=true`；最多进 Prompt 作 medium/low hint。  
含裸标识符实参、未归一占位、又非「单末级 Call」窄路径的 pattern：**不得**标 `printable=true`（可降为 prompt hint）。

#### 5.1.2 挖掘算法（MVP，漏斗 + 并行）

##### A. L0 候选漏斗（必须先跑）

1. 收集候选：`Issue 实体 ∩ Anchor 公开符号` ∪ Recipe `call_graph_template` **强制** ∪ entrypoint 相关符号。  
2. 打 tier：`recipe_forced` > `issue_named` > `anchor_hit`。  
3. 若 Recipe 命中：把 `required_patterns` 规范化为 **种子** `source_kind=recipe_seed`（可先无 `source_path`）。  
4. **无 L0 候选** → 不启动业务/测试全量 Call 扫描；仅尝试 Anchor 签名附件或直接 `insufficient`。

##### B. 并行采集（有预算；非严格 L1→L2→L3 瀑布）

在 L0 非空时，按预算并行/分片采集（实现可串行但逻辑等价）：

| 通道 | 范围 | 入库条件 |
|------|------|----------|
| A 文档可执行行 | `examples/**`、定义处 docstring / doctest 调用行 | 命中 L0；优先能 `ast.parse` 的 call 行 |
| B 业务 Call-shape | 包内非测试；**符号反查**「谁调用了候选名」 | 命中 L0；收 1–3 句赋值/构造闭包 |
| C 测试 Call-shape | `tests/**`、`test_*.py`（D1） | 同上；**丢弃 Assert / 期望比较** |
| D 签名保底 | Anchor / 定义处 signature + 推断 import | 始终可附；`confidence=low`；**默认 `printable=false`**；不作 α 主印刷燃料（档 3 默认关） |
| E README/Markdown | `README*`、`*.md` 代码围栏 | 可解析 call → 入库；解析失败 → 仅 Prompt hint，不进印刷 |

**停止扩大扫描**：已达 `sufficiency=printable`，或触达文件数 / AST 节点 / 超时预算。  
**「不足」定义**：没有可印刷 `call_pattern`，**不是**「文档字少」。

##### C. Call-shape 提取细则

1. 匹配 L0 名的 `ast.Call` → 向上收集 1–3 层赋值/构造（例：`r = Retort(...); r.load(...)`）。  
2. `ast.unparse` → 原始形态；再将 **可替换实参** 归一为 `__SLOT_{key}__`（key 来自参数名 / 约定主 payload 名 / Recipe `slots_from_inputs` 对齐）。  
3. 仓库特有、不应被 inputs 覆盖的常量（如库 API 枚举、`False` 语义开关）可保留字面量，**不得**标成与 inputs 冲突的槽。  
4. **删除** Assert 与带期望字面量的 compare；落盘禁止 `assert_source`。  
5. 过滤：私有 `._`（除非 Issue 点名）；纯 `hasattr`/`getattr`；超长截断。  
6. 写出 `slot_keys`；能合法进档 2 则 `bind_ready=true` / `printable` 按融合规则标定。

##### D. 融合 / 排序 / Recipe 双角色（播种 + 硬闸）

Recipe **不是**仅末闸：

| 角色 | 行为 |
|------|------|
| 播种（L0） | `call_graph_template` / required → 强制候选 + `recipe_seed` |
| 硬闸（融合） | 违反 `forbidden_patterns` → **drop**（不是仅降权） |
| 升权 | 满足 `required_patterns` → confidence 升档；`recipe_aligned=true` |
| 封顶 | 卡命中但 required 未满足 → 不得标 high；可 drop 或封顶 low |
| 印刷 | Recipe 含可展开 `emit_template` 时优先级 **高于** 任意仓库 snippet（见 §5.2.1 / §5.2.4） |

排序键（稳定）：

1. `recipe_aligned` 且非 forbidden  
2. `printable`  
3. source：`examples` ≥ `business_call` ≥ `test_call_shape` ≥ `docstring` ≥ `readme` ≥ `anchor_only`  
4. confidence  
5. 规范化 `call_pattern` 聚类后，**每 `api_name` 保留 top-k（建议 2–3）**

置信度标定：

| 条件 | confidence |
|------|------------|
| examples/可解析 docstring，且 Recipe 对齐（或无卡） | high |
| business / test Call-shape，Recipe 对齐 | high 或 medium |
| README 可解析 call | **默认 medium**；仅 Recipe required 也满足才可 high |
| 仅签名 / 不可印刷文档摘要 | low |
| 与 Recipe forbidden 冲突 | **不入库** |

##### E. L3 签名保底的消费边界（FROZEN）

| 消费者 | 允许用法 |
|--------|----------|
| 填表 Prompt | ✅ 锁合法参数名，防瞎编 kwargs |
| α 主印刷（档 3） | ❌ **默认关闭**（`enable_bind_mode_signature=False`）；见 §5.2.6 |
| 自由路径 | hint-only，不得写成「必须照抄签名当完整用法」 |

#### 5.1.3 注入点

| 位置 | 用法 |
|------|------|
| 契约 fill Prompt | `summary_for_prompt` + top-k（优先 `printable`）；**若命中 recipe_id → 强制注入该卡 `slots_from_inputs` / `slot_aliases` / arrange 槽说明**；要求 `call_graph`/`recipe_id`/`inputs` 键齐全 |
| 自由生成 Prompt | γ 摘要 + Recipe forbidden/required |
| α Renderer | 档 1 `emit_template`；档 2 仅 `printable`+占位/窄 AST；档 3 默认不开 |
| Linter / EG | `forbidden_nearby` / Recipe forbidden → blocking；自由路径同样生效 |
| BC `validate_contract` | 可选/建议：Recipe 命中时校验 `inputs` 含全部 `slots_from_inputs`（经 alias 后） |

#### 5.1.4 DoD（γ）

- 单测：迷你假仓库 → 挖出 Call-shape 且不含 assert；可归一 `__SLOT_*__`。  
- 单测：无 L0 时不触发全仓盲扫；forbidden snippet 被 drop。  
- 单测：`sufficiency` / `printable`/`bind_ready` 在夹具上正确（无占位又非单Call → 不得 printable）。  
- 探针抽检：adaptix / mashumaro / sqlite / bandit 各 ≥1 条 medium+ **或** `emit_template` 可展开（允许 anchor_only 回退但须 `prompt_only`/`low` 且诚实落盘）。

---

### 5.2 WP-α — Real Renderer（真印刷机 · 方案 A）

**模块**：重写 `app/spec_parser/behavior_skeleton.py`（可拆 `call_plan.py`）；接线 `contract_path.py`；扩展 `recipe_cards/*.json` 的 `emit_template`。

**定位（FROZEN · D5）**：

> 印刷机 **不发明用法**。用法来自 Recipe.`emit_template` 或 γ `printable` snippet；期望来自契约 oracle。  
> 实现形态 = **CallPlan 绑定（Bind）+ 字符串三段排放（Emit）**。  
> 印不出 → `RenderResult(ok=False)`，**零假桩字符**。

**明确不采用（3.5.0）**：方案 B（AST 拼装）作主实现；方案 C（LLM 整段写卷）作主路径。

```text
contract item + recipes + usage_snippets + anchor
        │
        ▼
┌─ Bind（选燃料 → CallPlan）──────────────────┐
│ 档1 Recipe.emit_template（槽位+alias+arrange）│
│ 档2 printable：仅 __SLOT_*__ / 窄 AST 改参   │
│ 档3 signature：默认关闭                      │
│ 未绑定 Name / 缺槽 / parse 失败 → blocked    │
└──────────────────┬───────────────────────────┘
                   ▼
┌─ Emit（字符串三段）──────────────────────────┐
│ Header: 去重 imports + pytest/asyncio/re     │
│ per-AC: arrange + act(call_expr) + oracle    │
│ 内建自检失败 → 改 blocked                    │
└──────────────────┬───────────────────────────┘
                   ▼
         RenderOk(script) | RenderBlocked(code)
```

#### 5.2.1 印刷优先级 / Bind 档位（FROZEN）

```text
1. Recipe 卡 emit_template 可展开（高于任意仓库 snippet；与 γ 播种一致）
2. 高/中置信且 printable=true 的 UsageSnippet（显式占位或窄 AST 改参）
3. （可选，默认关）Anchor 签名弱印 — 见 §5.2.6
4. 否则 → render_blocked（不得输出假桩）
   原因码：NO_USAGE_FUEL | AMBIGUOUS_API | RECIPE_UNSAT | MISSING_SLOT
          | LAYER_UNSUPPORTED | BIND_INPUTS_FAIL | UNBOUND_NAME | SELF_CHECK_FAIL
```

**冲突处理**：同一 `api_name` 多条互斥 `call_pattern` 且无 Recipe 锁定 → **不得随机印**；记 `AMBIGUOUS_API`。

**与 γ sufficiency 对齐**：

| γ sufficiency | α 期望行为 |
|---------------|------------|
| `printable` | 应能走档 1 或档 2 印出真调用（失败则修模板/占位/填表槽，不回假桩） |
| `prompt_only` | 默认可 `render_blocked`；仅当档 1 可展开时印刷（**不**依赖默认关闭的档 3） |
| `insufficient` | `render_blocked` + `NO_USAGE_FUEL` |

**3.5.0 假脚本闭环**：档 1 + 档 2 + blocked。不以档 3 成功率为 KPI。

#### 5.2.2 中间表示：`CallPlan`（FROZEN）

每个 `must` / AC item 先编译为 `CallPlan`，再变成源码（便于单测 Bind/Emit 分离）：

```text
CallPlan:
  must_id: str
  imports: list[str]             # e.g. "from adaptix import Retort, name_mapping"
  arrange_lines: list[str]       # 类型桩 / prelude（缩进前内容）
  call_expr: str                 # 可放入 result= 或 raises 块的表达式
  bind_mode: recipe | snippet | signature
  layer: lib | async | web | cli
  needs_await: bool
  result_name: result | resp | stdout
  recipe_id: str | null
  source_snippet_id: str | null  # 审计
  bound_names: set[str]          # arrange/imports 已引入名，供 UNBOUND_NAME 检查
```

**Bind 失败** → 该 must 不产生装饰性 body；按 §5.2.7 All-or-nothing 整题 blocked。

#### 5.2.3 API：`RenderResult`（FROZEN）

```python
@dataclass
class RenderResult:
    ok: bool
    script: str | None = None
    reason_code: str | None = None
    per_must: dict[str, str] | None = None  # must_id → "ok" | reason_code

def render_s1_script(
    contract: dict,
    *,
    recipe_cards: dict | None = None,
    usage_snippets: dict | list | None = None,
    anchor: Any | None = None,
) -> RenderResult:
    ...
```

| `ok` | `script` | 上游（`contract_path` / β） |
|------|----------|------------------------------|
| `True` | 完整 pytest 源码 | 走自检已过的脚本 → lint/EG/sandbox |
| `False` | **必须为 `None`**（禁止半成品落盘） | `contract_only` 或自由路径 best-of |

**兼容**：旧调用方若仍期望 `str`，由适配层在 `ok` 时取 `.script`，`not ok` 时不得把假桩字符串塞回。

#### 5.2.4 档 1 — Recipe `emit_template` + 槽位闭合（FROZEN）

仅有 `hint` + `call_graph_template` **不足以**机械展开。3.5.0 探针四卡须补齐 `emit_template`，并与填表 **inputs 契约闭合**（D6）。

**Recipe schema 增量（FROZEN 最小集）**：

```json
{
  "id": "adaptix.name_mapping",
  "layer": "lib",
  "required_patterns": ["Retort(recipe=[", "name_mapping("],
  "forbidden_patterns": ["Retort(name_mapping="],
  "hint": "...",
  "call_graph_template": ["Retort", "name_mapping", "load"],
  "blocking": true,
  "emit_template": {
    "imports": ["from adaptix import Retort, name_mapping"],
    "arrange": [
      "class __SLOT_model__(object):\n    pass"
    ],
    "call_expr": "Retort(recipe=[name_mapping(__SLOT_name_mapping_args__)]).load(__SLOT_data__, __SLOT_model__)",
    "slots_from_inputs": ["name_mapping_args", "data", "model"],
    "slot_aliases": {"payload": "data", "tp": "model"},
    "result_name": "result",
    "needs_await": false
  }
}
```

| 规则 | 说明 |
|------|------|
| 何时用档 1 | `item.recipe_id` 命中且卡含可用 `emit_template` |
| `slots_from_inputs` | **有 emit_template 时必填**；声明必须从 `inputs` 提供的键 |
| `slot_aliases` | 可选；填表可用别名，Bind 前归一到规范槽名（如 `payload`→`data`） |
| 占位格式 | 模板内统一 `__SLOT_{key}__`（与档 2 一致）；也允许仅出现在 `slots_from_inputs` 的花括号风格，实现层须先归一成 `__SLOT_*__` 再替换 |
| 槽位填充 | 先 alias 归一 → `__SLOT_k__` ← `repr(inputs[k])`（或约定的 expr 槽规则） |
| 缺槽 | **`MISSING_SLOT`**（不是笼统 RECIPE_UNSAT） |
| 校验 | 展开后须满足 `required_patterns`；触 `forbidden_patterns` → **`RECIPE_UNSAT`**（不得降级乱印） |
| arrange | 见 §5.2.5a；可内嵌最小类型桩 |
| 无 `emit_template` | 该卡不当档 1，落入档 2 |

**填表闭合（FROZEN · α 不改表）**：

| 环节 | 约束 |
|------|------|
| Fill Prompt | 命中 `recipe_id` → **强制注入**该卡 `slots_from_inputs`、`slot_aliases`、arrange 所需槽说明；要求 `inputs` 键齐全 |
| `validate_contract` | Recipe 命中时：经 alias 后缺 `slots_from_inputs` → BC blocking 或强制回填（推荐在进 α 前失败） |
| Bind | 只消费已闭合的 inputs；仍缺 → `MISSING_SLOT` |

**四卡责任**：`adaptix.name_mapping` / `mashumaro.field_options` / `httpx.client_basic` / `aiohttp.testclient` 在 3.5.0 **必须**具备可测的 `emit_template`（含 `slots_from_inputs`；lib 两卡须含可用 arrange 或说明类型由 prelude 提供）。

#### 5.2.5 档 2 — printable snippet 重绑定（FROZEN · DRAFT.4）

> **禁止**对任意标识符做子串/同名替换（会误伤 `data`⊂`database`/`metadata`，且多 Call 闭包易绑错层）。

**流程**：

1. 过滤：`printable=true` 且 `bind_ready=true`，confidence ∈ {high, medium}；与 `call_graph` / `recipe_id` 对齐。  
2. 多条互斥且无 Recipe 锁 → `AMBIGUOUS_API`。  
3. `imports` ← snippet.`import_path`。  
4. 按下列 **唯一合法** 策略得到 `call_expr`（印刷阶段禁止 LLM）：  
5. 合并 arrange（§5.2.5a）后做未绑定 Name 检查；`ast.parse` 整段 act（+arrange）失败 → **丢弃该 snippet**，试下一条。  
6. 皆失败 → `BIND_INPUTS_FAIL`。

**重绑定策略（FROZEN）**：

| 策略 | 条件 | 行为 |
|------|------|------|
| **P1 显式占位** | `call_pattern` 含 `__SLOT_{key}__` | **只**替换这些占位为 `repr(inputs[key])`（经 `slot_aliases`）；**禁止**改其它标识符 |
| **P2 窄 AST 改参** | pattern **无**占位；且 AST 上为 **单一末级 Call**（闭包最后一次调用）；且 Call 关键字/位置参数名可与 `inputs`（或签名）对齐 | 用 `ast` 改该 Call 的参数节点后 `ast.unparse`；**不得**改闭包上游构造除非其参数也是对齐槽 |
| **P3 失败** | 其它一切 | 丢弃 snippet，不排放 |

**γ 入库前提**：欲标 `printable=true`，必须已完成 P1 占位归一，或可证明满足 P2 前置（实现可在 miner 侧打 `bind_mode_hint=slots|single_call_ast`）。

**自检**：替换/改参后的 `arrange + act` 必须 `ast.parse` 成功；失败视为该 snippet 无效。

> P2 的小范围 AST **不算方案 B**（方案 B = 整文件 AST 拼装主路径）。

#### 5.2.5a arrange / 类型符号（FROZEN · 3.5.0 窄版）

**问题**：`load(data, Model)` 无 `Model` → `NameError` → harness/env 噪声，calib 失真。

**优先级（按序尝试，勿并行三套同等实现）**：

| 序 | 来源 | 行为 |
|----|------|------|
| 1 | `emit_template.arrange` | 卡内最小类型桩/准备语句；槽位同样用 `__SLOT_*__` 填充 |
| 2 | `inputs["arrange_prelude"]` | 字符串；α **原样按行缩进排放**，**禁止** LLM 润色；可多行 |
| 3 | 硬闸 | Bind 完成后：对 `arrange_lines + call_expr` 收集 `NameLoad`；减去 builtins、imports 引入名、arrange 中赋值/类名 → 仍有未绑定 → **`UNBOUND_NAME`**，禁止硬印 |

**红线**：不得为消除 NameError 退回 `NOT_IMPLEMENTED` 或假桩。  
**非目标**：3.5.0 不从仓库自动拖完整 Model/fixture 源码。

#### 5.2.6 档 3 — Anchor 签名弱印（默认关闭 · FROZEN）

| 项 | 决议 |
|----|------|
| 默认 | `spec_parser_enable_bind_mode_signature=False` |
| 与 D4 | L3 签名 **不作**高置信印刷燃料；默认关与 D4 一致 |
| 主 KPI | **不以**档 3 成功率为指标 |
| 假脚本闭环 | 只靠档 1 + 档 2 + blocked |

若实验性打开，须 **同时**满足：

- `layer == "lib"`；  
- 单函数、**无**构造链；  
- 签名参数名与 `inputs` 键（经 alias）**完全一致**；  
- **无** Recipe 卡命中（有卡应走档 1）；  
- 仍过 §5.2.5a 未绑定 Name 检查与 EG。

async / web / cli：**禁止**档 3。  
实现上即使打开失败也只 `render_blocked`，不得降级假桩。

#### 5.2.7 多 AC 策略（FROZEN）

| 策略 | 3.5.0 |
|------|-------|
| **All-or-nothing** | **采用**：任一 must Bind 失败 → 整题 `RenderResult(ok=False)` |
| Partial drop must | 不做（覆盖假象） |
| Partial stub | **禁止** |

空 `items` → blocked（**禁止**再印「仅 `NOT_IMPLEMENTED` 的 AC-M1」占位函数）。

#### 5.2.8 Emit：三段字符串排放（FROZEN）

每个 AC 骨架：

```text
# --- AC-{must_id} ---
def test_ac_{must_id}():
    {arrange_lines}
    {act_block}
    {oracle_block}      # raises 类可将 call 放入 with 块，无尾部 equality
```

##### Act

| 情形 | 排放 |
|------|------|
| 普通 oracle | `{result_name} = {call_expr}`；async 则 `= await {call_expr}` |
| raises / attr_error | `with pytest.raises(Exc):\n    {call_expr}`（**禁止**块内自抛 AssertionError） |

layer 包装：

| layer | 要求 |
|-------|------|
| lib | 真实 import + call_expr；`result = ...` |
| async | `async def _body(): ...` + `asyncio.run`；禁止 `await None` |
| web | TestClient/路径来自 emit_template 或 snippet；禁止 `type('R', ...)` 冒充金标响应 |
| cli | subprocess/入口来自模板或 snippet；禁止 `stdout = ''` 空跑当金标 |
| 未支持 | `LAYER_UNSUPPORTED` → blocked |

##### Oracle（纯函数映射；无 NOT_IMPLEMENTED）

| oracle_kind | 排放 |
|-------------|------|
| equality | `assert {result_name} == {lit}` |
| contains | `assert {lit} in {result_name}` |
| field_path | `assert {result_name}.{path} == {lit}` |
| raises / attr_error | 仅 Act 中的 `pytest.raises`（可无额外 assert） |
| http_status | `assert resp.status == {n}` |
| stdout_regex | `assert re.search({pat}, stdout or '')` |

##### Header

- 合并全体 `CallPlan.imports` 去重排序。  
- 固定 `pytest`；按需 `asyncio` / `re`。  
- 文件头 docstring 标明 `v3.5 S1 / scheme A`。

#### 5.2.9 排放后内建自检（先于全局 EG）

Emit 完成后立刻检查；失败 → 将结果改为 `ok=False`，`reason_code=SELF_CHECK_FAIL`（或映射具体 EG-xx），**不落盘假脚本**：

| 检查 | 标准 |
|------|------|
| **失败语义（主）** | **必须调用** `check_failure_semantics`（§5.3.3）；blocking 非空 → 失败。**禁止**另维护「源码字符串含 `NOT_IMPLEMENTED` 即拒」的独立文本规则（与 EG-04「按 Raise 节点」冲突） |
| 语法 | 整文件 `ast.parse` 成功 |
| 未绑定 Name | 与 §5.2.5a 硬闸一致（可重复检查） |
| Recipe | 若未含于 failure_semantics：`recipe_id` 命中且 `blocking` → `recipe_compliance==True`（可并入 EG-05） |

桩模式（`None # invoke` / `await None` / 假 `type('R'` 等）由 **EG-01 / 产品 Call 规则**覆盖，不在 α 侧重复发明黑名单。  
EG-06 在 sandbox 后由 provenance 执法。

#### 5.2.10 `render_blocked` 原因码

| code | 含义 |
|------|------|
| `NO_USAGE_FUEL` | 无 printable snippet 且无 Recipe 可展开（档 3 默认关时亦不尝试） |
| `AMBIGUOUS_API` | 多候选冲突且无 Recipe 锁定 |
| `LAYER_UNSUPPORTED` | 该 layer 模板尚未支持该编排 |
| `MISSING_SLOT` | alias 归一后 `inputs` 缺少 `slots_from_inputs` 声明的键 |
| `RECIPE_UNSAT` | 展开后触 forbidden / 不满足 required（卡要求失败） |
| `BIND_INPUTS_FAIL` | 占位/窄 AST 重绑定失败，或 parse 失败丢光 snippet |
| `UNBOUND_NAME` | call/arrange 含未绑定类型或符号，禁止硬印 |
| `SELF_CHECK_FAIL` | 排放后内建自检失败 |

#### 5.2.11 与 γ / β / δ 边界

| 模块 | α 做 | α 不做 |
|------|------|--------|
| γ | 消费 `printable`（已占位）/ Recipe 燃料 | 不在 Emit 时再挖仓库；不负责填表补槽 |
| 契约填表 | 假定 call_graph/inputs/expect **已受槽位约束** | **不在 α 改表**；缺槽报 `MISSING_SLOT` |
| δ / EG | 遵守失败铁律；内建自检 | 不替代全局 linter |
| β | 返回 `RenderResult` | 不自行 `s1_accept` |

#### 5.2.12 落地分期（α 内部）

| 步 | 内容 |
|----|------|
| 1 | 删除假桩路径；Bind 失败 → blocked |
| 2 | lib + 四卡 `emit_template` + `slots_from_inputs` + 填表槽位注入 |
| 3 | 档 2：`__SLOT_*__` + P2 窄 AST；γ 占位归一 |
| 4 | arrange 优先级 + `UNBOUND_NAME` |
| 5 | 确认档 3 默认关；async 真 await |
| 6 | web/cli 最小真模板 |
| 7 | （可选，非毕业条件）方案 B 整文件 AST 拼装 |

#### 5.2.13 DoD（α）

- 单测：样例契约 → `RenderResult.ok` 且脚本 **无** `None # invoke` / `NOT_IMPLEMENTED`；AST 含 Call。  
- 单测：缺燃料 / 多候选冲突 / 缺槽 → `ok=False` 且 `script is None`；原因码区分 `MISSING_SLOT` vs `RECIPE_UNSAT`。  
- 单测：`data` 槽不得误替换 `database`/`metadata` 标识符（子串替换禁令）。  
- 单测：无占位且非单末级 Call → 不得排放；有占位替换后 `ast.parse` 失败 → 丢弃。  
- 单测：缺 `Model` 类且无 arrange/prelude → `UNBOUND_NAME`。  
- 单测：`enable_bind_mode_signature=False` 时不走档 3。  
- 单测：Recipe `emit_template` 展开后 `recipe_compliance==True`；All-or-nothing。  
- 禁止：任何路径返回「注释桩 + 装饰 assert」字符串。

---

### 5.3 WP-δ — 失败语义净化（FROZEN · DRAFT.7 / D7）

**模块**：`failure_semantics.py`（新建，推荐）或并入 `script_linter.py`；`behavior_skeleton` Emit 自检调用；`calibration_gate.py` / evidence；`agent.py` / DraftPicker 消费；表侧 BC/fill（轻量）。

**定位**：

```text
δ = 失败分类学
  + 静态 EG 引擎（主；与 α 自检 DRY）
  + 运行时 provenance（辅；EG-06）
  + 表侧 raises 收紧（辅助）
  + β 消费规则
```

> **铁律**：校准失败（红）可归因于 **真实产品调用** 的返回值/异常/输出与契约 `expect` 不一致时，才算 **F-product**。  
> 伪造红 / 伪造绿一律硬拦。δ ≠ 「保证 buggy 必红」——弱期望真绿（F-weak-green）禁止用假 raise 凑红。

#### 5.3.1 失败分类学（FROZEN）

| 类型 ID | 名称 | 典型信号 | `calib_pass` | `s1_accept` |
|---------|------|----------|--------------|-------------|
| **F-product** | 产品语义失败 | 真 Call 后 assert 失败 / Issue 相关异常；traceback 进入被测包或断言在返回值上 | ✅（Gate 认 feature） | ✅（静态 EG 过） |
| **F-synthetic** | 脚本伪造失败 | 测试内 `raise AssertionError('NOT_IMPLEMENTED')`；无 Call 的 empty fail | ❌ | ❌ |
| **F-stub-pass** | 脚本伪造通过 | 无产品 Call 却绿；`raises(Exception)` 吞自抛 | ❌ | ❌（EG-06） |
| **F-env** | 环境/脚手架 | ImportError、harness | ❌（非脚本胜利） | 视既有 triage |
| **F-weak-green** | 弱期望真绿 | 有产品 Call，expect 过弱导致 buggy 也绿 | 非 δ 主责 | ✅ 若静态 EG 过 + **`weak_green=true`**；**禁止**回补假 raise；**不计**金标 |

**δ 主责**：F-synthetic、F-stub-pass。  
**明确不管成「必须变红」**：F-weak-green（卷面/契约问题，不是伪造）。

#### 5.3.2 删除的反模式（排放与自由路径均禁）

1. `result = None  # invoke ...` / `await None`  
2. `raise AssertionError('NOT_IMPLEMENTED')` 作为保证红手段  
3. `with pytest.raises(Exception): raise AssertionError(...)`（自抛自接）  
4. 字符串字面量赋值冒充 API 符号而无 Call  
5. 无产品 Call 的 empty fail / 仅存在性检查冒充行为失败  

#### 5.3.3 静态 EG 引擎（主执法 · P0）

##### 单一 API（DRY · FROZEN）

```text
check_failure_semantics(script, *, recipe_id=None, recipe_cards=None)
  -> FailureSemanticsReport {
       blocking: list[str],      # EG-01 …
       warnings: list[str],
       per_ac: dict[str, ...]
     }
```

| 调用方 | 行为 |
|--------|------|
| α Emit 自检（§5.2.9） | `blocking` 非空 → `RenderResult(ok=False, reason_code=SELF_CHECK_FAIL)` 或映射具体 EG |
| `script_linter` | `blocking` 并入 lint blocking；自由路径同样生效 |
| PersistGuard / DraftPicker | EG 失败稿不得入选 `s1_accept` |

**禁止**：α 一套文本黑名单、linter 另一套互不一致规则。

##### EG 检测规格（FROZEN）

| 规则 | 推荐方法 | 通过 / 注意 |
|------|----------|-------------|
| **EG-01** | 文本/正则：`None\s*#\s*invoke`、等价注释桩、`await None`；可配置模式表 | 已知假桩 |
| **EG-02** | 按 AC 切段 + AST：≥1 个 **产品 Call**（定义见下） | 无产品 Call → blocking |
| **EG-03** | AST：`with pytest.raises(...):` 的 body 内 **必须 ≥1 产品 Call**；禁止块内仅 `Raise(...)`（任意异常，含 AssertionError / ValueError 自抛）；`raises(Exception\|BaseException)` 且无产品 Call → blocking | 放行 `raises(ValueError): api()`（api 为产品 Call） |
| **EG-04** | 扩展 L14：存在 `Raise(NOT_IMPLEMENTED / AssertionError('NOT_IMPLEMENTED'))` 且该 AC **无**产品 Call | **禁止**仅因源码字符串含 `NOT_IMPLEMENTED` 就杀（注释/产品异常类名） |
| **EG-05** | `recipe_compliance==False` 且卡 `blocking` | 与 α 自检一致 |

##### 产品 Call 定义（FROZEN · EG-02/03 共用）

**非产品 Call 黑名单（不得计入「有 Call」）** — 可配置扩展，默认至少包含：

| 类别 | 示例 |
|------|------|
| 内建/类型 | `print`, `len`, `list`, `dict`, `set`, `tuple`, `str`, `int`, `bool`, `type`, `isinstance`, `issubclass`, `getattr`, `setattr`, `hasattr`, `callable`, `open`, `repr`, `sorted`, `enumerate`, `range`, `iter`, `next`, `min`, `max`, `sum`, `any`, `all` |
| 测试框架 | `pytest.*`, `unittest.*`（含 `assert*` 辅助若以 Call 出现） |
| Mock | `unittest.mock.*`, `MagicMock`, `Mock`, `patch`, `AsyncMock` |
| 字面/空 | 无函数的 Call、仅字符串构造冒充 |

**产品 Call 启发（满足其一即可计为产品）**：

1. 被调名 / 接收者名 ∈ Anchor 公开符号 ∪ Recipe `call_graph_template` ∪ Issue 点名符号；或  
2. 其 `import` 来自 **本题 SUT**：  
   - 仓库被测包路径（`project_path` 内非测试文件）；**或**  
   - **SUT 顶层包名**（由 task/issue/Anchor 模块推断，如 `adaptix`、`httpx`）——**不要求**源码文件落在 repo 树内（已安装第三方包同样算产品）；或  
3. 属性链末级命中上述符号（如 `Retort(...).load(...)` 的 `load`/`Retort`）。

扫描范围：整 AC 函数 AST（**含** `async def` / 嵌套函数体内的 Call）。

仅存在黑名单内 Call → **视为无产品 Call**（EG-02/03 blocking）。

**弱断言边界（FROZEN）**：AC 已有产品 Call，但断言仅为存在性 / `is not None` / `callable` 等弱检查 → **不得**标 `stub_pass`；属卷面弱断言或可标 `weak_green` / 交 P2 弱断言规则。**EG-02 只回答「有没有产品 Call」，不回答「断言够不够强」。**

##### 与 L14 关系

- L14 保留，视为 EG-04 的 empty-fail 子集。  
- blocking **并集**上报；可同时出现 `L14-EMPTY-FAIL` 与 `EG-04`，避免互斥漏拦。

##### 过宽 raises（静态补充）

| 情形 | 处置 |
|------|------|
| 脚本 `pytest.raises(Exception\|BaseException)` + 无产品 Call | EG-03 → blocking |
| 脚本 `raises(具体异常)` + 产品 Call | 合法 |
| 脚本 `raises(Exception)` + 产品 Call | **允许但** evidence 可标 `broad_raises=true`（P2 warn，不默认 blocking） |
| 契约默认 `exception=Exception` 且 Issue 未点名 | 见 §5.3.5 表侧 |

#### 5.3.4 运行时 provenance（辅执法 · P1 规格 FROZEN）

##### 字段（写入 execution_evidence / Gate 结果）

```text
failure_provenance: product | synthetic | stub_pass | env | unknown | missing   # 整题聚合
per_ac_provenance: { must_id: product|synthetic|stub_pass|env|unknown|weak_green|missing }
synthetic_fail: bool
stub_unexpected_pass: bool
weak_green: bool   # 整题：有产品 Call + unexpected/overall pass + 静态 EG 过 + 非 stub_pass
```

**`missing`（FROZEN）**：该稿 **未跑 sandbox**，或 evidence 未写入 provenance 字段。行为：

- 归一处理上可与 `unknown` 同列为「非 synthetic/stub_pass」；  
- **不得**视为 EG-06 通过或「已证明非假绿」；  
- **不得**仅凭 missing 给予 `calibration_passed`；  
- 交卷仍可依赖 **静态 EG 过** 走 `s1_accept`（S4 前过渡）；毕业后应尽量避免长期 missing（每道入选稿应有 sandbox evidence）。
##### 判定启发式

**标 `synthetic`（伪造红）** — **优先**满足（防误杀）：

1. 运行失败；且  
2. 该 AC **无产品 Call**，或测试内显式 `Raise AssertionError('NOT_IMPLEMENTED')` / 等价凑红；或  
3. traceback **主要帧**在测试文件，**且**异常消息匹配 `NOT_IMPLEMENTED` 类凑红标记。

**不得单独**因「全程无产品包帧」一票标 `synthetic`（短 TB / `-tb=line` / 断言在测试文件但值来自产品时易误杀）→ 标 `unknown`，**不得**仅凭 unknown 否决 calib；可降为 warning 并依赖静态 EG。

**标 `stub_pass`（伪造绿）** — 满足其一：

1. overall pass / unexpected pass，且静态 EG-01/02/03 本应失败（或事后扫描仍命中 stub / 无产品 Call）；或  
2. 存在「零产品 Call」的 AC 却全部通过。

**标 `product`：**

1. 失败帧进入仓库被测包路径；或  
2. assert 失败且该 AC 有产品 Call（即使异常类型是 AssertionError）。

**标 `env`：** 沿用现有 ImportError / harness triage。

**标 `weak_green`（AC 或整题）**：该范围有产品 Call、静态 EG 过、运行为 pass/unexpected pass、且非 stub_pass。

##### 整题聚合（FROZEN）

| 规则 | 行为 |
|------|------|
| 任一 AC 为 `synthetic` / `stub_pass` | 整题不得 `calib_pass` / `s1_accept` |
| 其余 AC 均为 product/weak_green/unknown/env | 按最严重者上报；`weak_green` 若整题 pass 则 `weak_green=true` |
| 与 All-or-nothing | 对齐 α：局部假失败/假通过污染整题交卷 |

##### 与 `classify_gate_triage` 映射（FROZEN）

| provenance | triage / Gate |
|------------|---------------|
| `synthetic` | **不得**映射为 `feature_fail`；不计 `calibration_passed` |
| `stub_pass` | EG-06 blocking；非 feature 胜利 |
| `product` | 可走现有 `feature_fail` |
| `env` | `harness_error` / missing_* 等既有 |
| `unknown` / `missing` | 不单独当 feature 胜利；也不单独 EG-06 硬拒（依赖静态 EG）；`missing` 不得 calib_pass |

##### 关键区分（FROZEN）

| 现象 | 判定 |
|------|------|
| **产品**代码 `raise NotImplementedError` | **product**（看帧在包内） |
| **测试**里 `raise AssertionError('NOT_IMPLEMENTED')` | **synthetic** |
| 仅异常类名含 NotImplemented、帧在测试文件且无 Call | synthetic |
| 有产品 Call、buggy 上全绿（弱 expect） | **不是** stub_pass；属 F-weak-green（`weak_green=true`） |

##### Gate / EG-06 消费

| provenance | Gate / 交卷 |
|------------|-------------|
| `synthetic` | **不得** `calibration_passed`；不得当 feature_fail 胜利；不得 s1_accept |
| `stub_pass` | **EG-06 blocking**；不得 s1_accept |
| `product` | 走现有 feature_fail 逻辑 |
| `env` | 现有 env/harness triage |
| `unknown` / `missing` | 不单独硬拒；静态 EG 仍可拒；`missing` 不得 calib_pass |
| F-weak-green | 静态 EG 过则可 s1_accept + **`weak_green=true`**；**禁止**补假 raise；**不计**金标 KPI |
| 有产品 Call 的弱断言绿 | **不是** stub_pass（见 §5.3.3 弱断言边界） |

实现分期：S1 先落地静态 EG；S4 并行接入 provenance / per_ac / weak_green 与 EG-06（规格已 FROZEN）。**S4 前** unexpected pass 若静态 EG 过可暂允 s1，但毕业前必须具备 EG-06 字段与消费。

#### 5.3.5 表侧辅助（轻量）

挂 BC / contract fill（不必新开大包）：

1. `oracle_kind=raises` → 必须具体 `exception`；**禁止**默认裸 `Exception`，除非 `issue_quote` 明文支持宽捕获。  
2. 填表说明：期望不得依赖「调用未发生」；raises 块语义须对应真实产品调用。  
3. 与 Dual-State Lite 已有 false_fail 规则对齐，不重复造轮；**EG blocking 优先于** Dual-State 加分。

#### 5.3.6 δ → β 消费表（FROZEN）

| 条件 | final_action / 选稿（须服从 D8 降级序） |
|------|------------------------------------------|
| 静态 EG blocking（EG-01…05） | 不得 `s1_accept`；该稿剔除；**回看**其他 EG 合法候选 → 否则 `contract_only`（BC 过）或 `no_script` |
| `synthetic_fail` | 同上；且 **不算** `calib_pass` |
| `stub_unexpected_pass` / EG-06 | 同上 |
| 仅 F-weak-green（有产品 Call、真绿） | 允许 `s1_accept` + `weak_green=true`；禁止回补假 raise |
| α `render_blocked` | 不写正式脚本；进 D8（先 best-of，再 contract_only） |

DraftPicker：见 §5.4.3（EG/−∞、stub 剔除、weak_green 降权）。

#### 5.3.7 与 α / SCC-L / Dual-State 边界

| 模块 | δ 关系 |
|------|--------|
| α Emit | 遵守无凑红排放；自检调用 `check_failure_semantics` |
| SCC-L | 默认关（D3）；**不**承担发现假桩主责 |
| Dual-State Lite | 假失败风险分继续服务选稿；**不替代** EG；EG 失败分优先 |
| 自由路径 | **完整 EG-01…05**（及可用时 EG-06），与契约路径同一标准 |

#### 5.3.8 落地分期（δ 内部）

| 步 | 内容 | 优先级 |
|----|------|--------|
| 1 | 抽出 `check_failure_semantics`；EG-01…05 + 产品 Call 黑名单/启发 + 夹具 | P0 |
| 2 | α 自检与 linter 改调同一函数；废除 Emit 凑红 | P0 |
| 3 | agent/DraftPicker/PersistGuard 消费 EG；β D8 落地 | P0 |
| 4 | `failure_provenance` + `per_ac_provenance` + `weak_green` + EG-06 | P1 |
| 5 | 表侧 raises 收紧；`broad_raises` warn | P2 |

#### 5.3.9 DoD（δ）

- 单测夹具：注释桩 / 自抛自接 / **raises 块内自抛 ValueError** / empty NOT_IMPLEMENTED / `print` 冒充 Call / **已安装 SUT 包 Call 算产品** / 有产品 Call 的真 raises / 有 Call 弱断言 ≠ stub_pass / 好脚本 — EG 判定正确。  
- 单测：α Emit 自检与 linter **仅**经 `check_failure_semantics`（无独立 NOT_IMPLEMENTED 字符串禁令）。  
- 单测：产品帧 `NotImplementedError` **不**被标 synthetic；「仅无产品帧」→ `unknown`；**missing 不得 calib_pass**（P1）。  
- 单测：多 AC 其一 synthetic → 整题不得 s1/calib（P1）。  
- 单测：EG 失败稿不得标记 `s1_accept` / `calib_pass`；弱绿稿带 `weak_green=true`。  
- 回归：契约样例不再出现 stub 型 unexpected pass；不得为弱绿回补 `NOT_IMPLEMENTED`。

---

### 5.4 WP-β — 产物分层与交卷纪律（FROZEN · DRAFT.7 / D8）

**模块**：`agent.py`、`draft_picker.py`、`artifact_store.py`、契约 JSON 容错；消费 δ EG/provenance。

**定位**：Layer-0（契约）与 Layer-1（可执行卷）分离；**降级序**决定交什么，**PersistGuard** 决定写不写盘。

#### 5.4.0 降级序（FROZEN）

```text
1. 候选池中存在「静态 EG 过」且 provenance ∉ {synthetic, stub_pass} 的稿
      （自由路径或契约路径均可；含历史 round 保留稿，不因进入契约路径而清空池）
      → DraftPicker 按 §5.4.3 选最优
      → calib_pass | s1_accept | persist
      → PersistGuard 写入正式 test_feature.py

1b. 否则，若候选池无 EG 合法稿，且本轮尚未做过 free_fallback
      → 触发至多 1 次自由生成（注入 γ + Recipe；完整 EG）
      → 成功则入池并回到步骤 1；失败则继续步骤 2
      （开关：spec_parser_free_fallback_on_contract_fail，默认 True）

2. 否则，契约 BC 过，且（render_blocked | 契约稿 EG/provenance 失败 | 无其他合法稿 | free_fallback 已用尽）
      → final_action=contract_only
      → 落盘 behavior_contract.json + 原因；正式路径无 test_feature.py
      → decision_trace 记 rejected_draft_ids（若有）

3. 否则 → no_script
```

**强制适用场景**（均走完整 1→1b→2→3，禁止跳过 1/1b 直接空手）：

- α `render_blocked`  
- 契约稿静态 EG 失败  
- sandbox 后 synthetic / stub_pass  
- 审查消融拒收（D3）  
- 填表 `contract_crash` 后（若自由路径产生合法稿，仍走 1；池空走 1b）

**候选池纪律（FROZEN）**：进入契约路径 **不得**仅为「走 stub 分支」而丢弃既有 EG 合法自由稿；历史 round 保留直至终态选定。
#### 5.4.1 final_action 状态机（FROZEN）

| final_action | 前提 | 磁盘 |
|--------------|------|------|
| `calib_pass` | 静态 EG 过 + feature calib 过 + provenance∉{synthetic,stub_pass,missing 作 calib} | 正式有真脚本 |
| `s1_accept` | 静态 EG 过 + provenance∉{synthetic,stub_pass} +（calib 未过或非必须）；可 `weak_green` | 正式有真脚本；evidence 含 `weak_green` |
| `persist` | 自由路径 EG 合法入选（既有命名） | 正式有真脚本；与 s1/calib 同属 **可执行交卷** |
| `contract_only` | **BC 过** + 降级序走到步骤 2 | **正式无** `test_feature.py`；可有 rejected/ |
| `no_script` | 降级序走到步骤 3 | 正式无入选脚本 |

| 中间原因码（非 final_action） | 含义 |
|------------------------------|------|
| `contract_crash` | JSON/填表崩溃；可落 `behavior_contract.partial.json`；**≠** `contract_only` |
| `render_blocked` | α 未产出；进入降级序 |
| `eg_reject` / `provenance_reject` | 稿被 δ 否决；进入降级序 |
| `free_fallback_done` | 已执行步骤 1b（成功或失败均记 trace） |

> β 必须遵守 §5.3.6 与本节降级序；不得用 F-synthetic / F-stub-pass 稿正式交卷。  
> **废除**：一切 `degraded_or_uncalib_s1_kept` /「有表即 s1」逻辑。  
> **ART 可执行交卷集合（FROZEN）**：`final_action ∈ {calib_pass, s1_accept, persist}` ⇒ 正式路径有脚本、静态 EG 过、provenance∉{synthetic,stub_pass}；报表 KPI 仍可拆开三类计数。

#### 5.4.2 PersistGuard（FROZEN）

| 阶段 | 正式 `output_dir/test_feature.py` | 可选调试 |
|------|-----------------------------------|----------|
| Bind/Emit 失败 / `render_blocked` | **不写** | — |
| 静态 EG 失败 | **不写** | `artifacts/rejected/r{N}_test_feature.py` |
| sandbox 后 synthetic / stub_pass | **删除或移入 rejected**（若曾临时写入） | 保留 rejected |
| 入选 `calib_pass` / `s1_accept` / `persist` | **写入或保留**正式文件 | — |
| `contract_only` / `no_script` | **确保正式路径无**交卷脚本 | rejected 可保留 |

临时跑 sandbox 可用工作副本；**不得**在 EG 未通过时把工作副本当作 ART 意义上的交卷文件；进程结束应清理，**禁止**残留覆盖正式 `test_feature.py`。

**下游读盘（FROZEN）**：

| 消费者 | 允许读取 |
|--------|----------|
| 金标 / 后续修复 Agent / 卷面审计默认入口 | **仅** `output_dir/test_feature.py`（或 report.`official_script_path`） |
| 人工调试 / 决策审计 | `artifacts/rejected/**`、`behavior_contract*.json`、`script_decision_trace.json` |
| **禁止** | 将 `rejected/` 下文件当作「本题已交卷脚本」喂给下游 |

#### 5.4.3 决策节点变更

| 节点 | 3.4 行为 | 3.5 行为 |
|------|----------|----------|
| `D_pick_draft` / s1 | `degraded_or_uncalib_s1_kept` | **删除该分支**；仅 EG+provenance 合法才 s1/calib |
| `D_contract_render` | 总有脚本字符串 | 可 `render_blocked`；不写正式盘 |
| `D_eg` / persist | 易先落盘再认 | PersistGuard：先判定再正式写 |
| 审查拒收（若消融开启） | 易无脚本 | **D8 降级序**（先 best-of） |
| 填表 JSON 崩 | 整题空 | 见 §5.4.5；`contract_crash` → 自由路径 → 再 no_script |
| `forbid_no_script_if_s1_ok` | 有表也算 ok | **仅**存在 EG 合法可执行候选时阻止妄选 no_script |

#### 5.4.4 DraftPicker（v35 · FROZEN 序）

**一票否决（分 = −∞ / 剔除）**：静态 EG blocking；`synthetic_fail`；`stub_unexpected_pass`；正式交卷候选中的假桩特征。

**优先级（高 → 低）**：

1. `calib_pass` 且非 synthetic/stub_pass  
2. `s1_accept` 且 `weak_green=false`  
3. `s1_accept` 且 `weak_green=true`（可交卷，报表降权）  
4. 其他 EG 合法 `persist`  
5. （非候选）`contract_only` / `no_script` — **不进入**「有脚本」候选集  

附加：`contract_path_s1` 加权 **不得**覆盖 EG 失败；同等条件下具体 expect / recipe 合规加分可沿用 v34 权重。

#### 5.4.5 契约 JSON 容错（FROZEN 最小规格）

| 步 | 行为 |
|----|------|
| 1 | 抽取 JSON 子串 / trailing comma 等 **sanitize**（最多 1 次自动） |
| 2 | 仍失败 → **局部重填**（同一 fill 提示 + 错误反馈，最多 `N=2` 轮，可配置） |
| 3 | 仍失败 → 记 `contract_crash`；可选落盘 `behavior_contract.partial.json` |
| 4 | **尝试自由路径**生成并入候选池（走完整 EG） |
| 5 | 按 D8 降级序收尾 → 合法稿交卷 / 否则 `no_script`（**不是**静默空终态） |

`contract_only` **仅**在 BC `validate_contract` 通过时可用；crash 残表不得冒充。

#### 5.4.6 DoD（β）

- ART：`final_action ∈ {calib_pass, s1_accept, persist}` ⇒ 正式路径有真调用脚本且 EG 一致；provenance∉{stub_pass,synthetic}；弱绿带 `weak_green`。  
- ART：`contract_only` ⇒ 正式路径 **无** `test_feature.py`；有 `behavior_contract.json`；BC 过；`official_script_path` 为空。  
- 单测：EG 失败 / render_blocked 且池空 → **触发 free_fallback(1b)**（开关开时）；有自由合法稿 → **不得**直接 no_script/空手。  
- 单测：不存在 `degraded_or_uncalib_s1_kept` 决策路径。  
- 单测：下游约定 — rejected 路径不得被标为 official。  
- dateutil 类 JSON 失败走 §5.4.5 五步，有显式 reason。  
- run report 含 `weak_green_count`（或等价字段）与 `official_script_path`。

---

### 5.5 WP-XPATH — 双路径统一吃 γ（附属）

- 自由路径 Prompt：注入 `summary_for_prompt`（优先 printable / high/medium）。  
- 自由路径 lint：Recipe forbidden/required；无卡时用 snippet `forbidden_nearby`。  
- 不强制自由路径改走契约；**入选稿必须过完整 EG-01…05**；provenance 可用时 EG-06 同样生效。  
- 与契约路径共享同一份 `usage_snippets.json`（一次挖掘，两处消费）；共同进入 D8 候选池。

---

## 6. 实施阶段与排期

| 阶段 | 内容 | 工作包 | 建议工期 | 入口条件 |
|------|------|--------|----------|----------|
| **S0** | 口径冻结 + `check_failure_semantics` 夹具 + Renderer/EG 离线单测骨架 | α/δ 测试先行 | 0.5–1 天 | — |
| **S1** | δ 静态 EG-01…05 DRY 合入 linter/α自检；废除假桩排放 | δ + α 止血 | 1 天 | S0 |
| **S2** | γ UsageMiner MVP：L0 漏斗 + 并行采集 + sufficiency + 落盘 + Prompt 注入 | γ | 2–3 天 | S1 可并行启动挖掘 |
| **S3** | α：档1槽位闭合 + 档2 `__SLOT_*__`/窄AST + arrange/`UNBOUND_NAME`；档3默认关 | α | 2–3 天 | S2 有燃料或 Recipe 可展开 |
| **S4** | β D8：降级序+free_fallback+PersistGuard+DraftPicker+JSON 五步；δ provenance/per_ac/weak_green/EG-06/missing | β + δ P1 | 1.5–2 天 | S3 |
| **S5** | 双路径门禁 + 关审查主跑批 | XPATH | 1–2 天 | S4 |
| **S6** | 15 题探针审计；可选审查消融（不计主账） | 验证 | 1 天 | S5 |

**合计**：约 **1.5–2 周**（单人主路径）。

**并行**：S1 的 EG lint 可与 S2 挖掘并行；**S3 合入主跑批前**必须具备「Recipe `emit_template`+槽位闭合 **或** printable 占位 snippet」之一；档 3 保持默认关。大量 `contract_only` 若因缺槽/缺占位，属预期，报告中说明。

---

## 7. 验证计划

### 7.1 必过门禁（合入前）

| ID | 验证 | 通过标准 |
|----|------|----------|
| V1 | 单测：禁止假桩字符串/自抛自接（EG-01…04 夹具） | 全绿 |
| V1b | 单测：`check_failure_semantics` 与 α自检 DRY（α 无独立 NOT_IMPLEMENTED 字符串禁令）；SUT 第三方包 Call 算产品；raises 块自抛 ValueError 拒；有 Call 弱断言 ≠ stub_pass | 全绿 |
| V1c | 单测：provenance — synthetic vs 产品 NotImplementedError；无产品帧→unknown；missing 不得 calib；per_ac 聚合；stub_pass；weak_green（P1，S4 前可 xfail 标规格） | 全绿或规格挂起注明 |
| V2 | 单测：方案 A — CallPlan Bind/Emit；样例契约发射 Call；blocked 时 script is None | 全绿 |
| V2b | 单测：emit_template + slots/alias/`MISSING_SLOT`；recipe_compliance；All-or-nothing | 全绿 |
| V2c | 单测：档2 禁止子串误伤；占位替换；无占位非单Call不得印；parse 失败丢弃 | 全绿 |
| V2d | 单测：arrange/`UNBOUND_NAME`；档3默认关 | 全绿 |
| V3 | 单测：UsageMiner Call-shape 无 assert；forbidden drop；无 L0 不盲扫 | 全绿 |
| V3b | 单测：sufficiency / printable 字段在夹具上正确 | 全绿 |
| V4 | 单测：EG 失败不得标 s1_accept；无 degraded s1；池空时 free_fallback；有合法稿不空手 | 全绿 |
| V5 | ART：contract_only 正式无脚本；可执行交卷集合有脚本；rejected 非 official；weak_green / official_script_path | 全绿 |
| V5b | 单测：PersistGuard — EG 失败不写正式盘；contract_crash 五步；下游只认正式路径 | 全绿 |

### 7.2 探针主跑批（3.5 对照）

| 项 | 值 |
|----|-----|
| 跑批名建议 | `deepswe-spec-parser-python-v3.5-probes` |
| 语义审查 | **默认关**（D3） |
| 对照 | v3.4 关审查汇总 |

**主看指标**

| 指标 | 期望（相对 v3.4 关审查） |
|------|--------------------------|
| 契约假脚本簇（sqlite/psd/bandit/gql/igel/sqlfmt 等） | **显著下降 / 接近清零**（转为真调用或 contract_only） |
| stub 型 unexpected pass / synthetic_fail | → **0**（主跑批抽检） |
| STRONG | 不回退；争取 ≥3 |
| adaptix / mashumaro WRONG_LAYER | 减轻（γ 主战场） |
| `s1_accept` 中 EG 不合格占比 | → **0** |
| `weak_green` 占比 | **单独报表**；不计入金标胜利 |
| 磁盘有脚本数 | **允许下降**（假卷变 contract_only 算进步） |

### 7.3 停损与回滚

| 触发 | 动作 |
|------|------|
| `contract_only` 暴涨且 Recipe/snippet 明显可印 | 修 α 展开，不重开假桩 |
| 真调用后 calib 全红但脚本可审 | 允许 `s1_accept`（EG 过）；勿为红而加 NOT_IMPLEMENTED |
| 真调用后弱绿（F-weak-green） | 允许 s1_accept + **打标**；**禁止**假 raise 凑 calib；卷面另审；不计金标 |
| 自由路径 STRONG 回退 | 检查 γ 注入是否过约束；放宽 low 置信为 hint-only |
| 任何 PR 重新引入 `None # invoke` / Emit 凑红 | **拒绝合入** |

---

## 8. 模块改动清单（预期）

| 模块 | 变更 |
|------|------|
| `app/spec_parser/usage_miner.py` | **新建** γ：漏斗、并行采集、融合、sufficiency |
| `app/spec_parser/behavior_skeleton.py` | **重写** α 方案 A：CallPlan Bind/Emit；`RenderResult`；删除假桩 |
| `app/spec_parser/call_plan.py` | **可选新建**：CallPlan / Bind 纯函数，便于单测 |
| `app/spec_parser/contract_path.py` | 填表前跑 γ；消费 `RenderResult`；`render_blocked` → contract_only 分支 |
| `app/spec_parser/failure_semantics.py` | **新建（推荐）**：`check_failure_semantics`；EG-01…05；产品 Call 黑名单/启发；供 α/linter DRY |
| `app/spec_parser/script_linter.py` | 调用 failure_semantics；L14 与 EG 并集；自由路径完整 EG |
| `app/spec_parser/calibration_gate.py` | `failure_provenance` / `per_ac_provenance` / `weak_green` / synthetic / stub_pass；与 triage 映射；EG-06 |
| `app/spec_parser/script_contract_align.py` | stub → blocking（机器侧；可委托 failure_semantics） |
| `app/spec_parser/agent.py` | D8 降级序含 free_fallback；PersistGuard；废除 degraded s1；`contract_only`；消费 EG+provenance；γ 先于生成 |
| `app/spec_parser/draft_picker.py` | `draft_score_v35`；EG/−∞；weak_green 降权；分数序 §5.4.4 |
| `app/spec_parser/artifact_store.py` | final_action；ART；`rejected/`；`official_script_path`；provenance/weak_green；`usage_snippets.json` |
| `app/spec_parser/script_prompts_v3.py` / contract fill prompts | 注入 γ；**强制注入 Recipe 槽位表**；约束 call_graph/inputs；raises 具体异常 |
| `app/spec_parser/behavior_contract.py` | 建议：Recipe 命中时校验 slots（经 alias）；裸 Exception 收紧 |
| `app/spec_parser/recipe_loader.py` | L0 播种；加载/校验 `emit_template`/`slots_from_inputs` |
| `app/spec_parser/recipe_cards/*.json` | 四卡补齐 `emit_template` + slots + 必要 arrange（§5.2.4） |
| `app/spec_parser/schema.py` | `contract_only`、snippet / sufficiency / RenderResult / provenance 类型（如需） |
| `test/app/spec_parser/test_v35_*.py` | V1–V5（含 V1b/V1c、V2b–V2d、V3b） |
| `app` config | usage_miner 默认 True；表审/SCC-L 默认 False；renderer_scheme=A；failure_semantics/provenance 见 §9 |

---

## 9. 配置开关（建议）

| 开关 | 3.5.0 默认 | 说明 |
|------|------------|------|
| `spec_parser_enable_usage_miner` | `True` | γ |
| `spec_parser_usage_mine_tests_call_shape` | `True` | D1 |
| `spec_parser_usage_mine_budget_files` | 建议 `80` | γ 扫描文件上限（可调） |
| `spec_parser_usage_snippet_topk_per_api` | 建议 `3` | 聚类后每 API 保留条数 |
| `spec_parser_enable_contract_llm_review` | `False` | D3 |
| `spec_parser_enable_script_contract_llm` | `False` | D3 |
| `spec_parser_forbid_renderer_stub` | `True` | α/δ |
| `spec_parser_enable_failure_semantics_check` | `True` | D7：静态 EG |
| `spec_parser_enable_failure_provenance` | `True`（S4 起） | D7：运行时 provenance / EG-06 |
| `spec_parser_forbid_bare_raises_exception` | `True` | 表侧/脚本过宽 raises |
| `spec_parser_renderer_scheme` | `A` | D5：CallPlan + 字符串三段排放 |
| `spec_parser_renderer_all_or_nothing` | `True` | 任一 must Bind 失败整题 blocked |
| `spec_parser_enable_bind_mode_signature` | **`False`** | D5：档 3 默认关 |
| `spec_parser_slot_placeholder_format` | `__SLOT_{key}__` | D6：唯一占位格式 |
| `spec_parser_s1_require_exec_gate` | `True` | β / D2 |
| `spec_parser_allow_contract_only` | `True` | β / D8 |
| `spec_parser_free_fallback_on_contract_fail` | **`True`** | D8 步骤 1b：池空时至多 1 次自由补生成 |
| `spec_parser_forbid_no_script_if_s1_ok` | `True`（修订语义） | **仅**存在 EG 合法可执行候选时阻止妄选 no_script；≠有表 |
| `spec_parser_persist_rejected_scripts` | `True` | PersistGuard：失败稿写入 `artifacts/rejected/` |
| `spec_parser_official_script_only` | `True` | 下游/金标只认正式 `test_feature.py` |
| `spec_parser_contract_json_repair_rounds` | 建议 `2` | §5.4.5 局部重填轮数 |

---

## 10. 成功定义（版本毕业）

同时满足：

1. **V1–V5** 单测/一致性全绿。  
2. 主跑批：**契约路径不再批量交付注释桩脚本**；`s1_accept` 样本抽检 EG 全过。  
3. 卷面：假脚本导致的 INVALID **明显下降**；STRONG **不因 3.5 回退**。  
4. 决策诚实：存在 `contract_only` 案例且 ART 一致（证明 β 生效，而非再次假交卷）。  
5. 文档：本计划升为 `3.5.0-FINAL` 并与开关一致；含 D1–D8 与 γ/α/δ/β 落地说明。  
6. 毕业前：provenance/EG-06 与 PersistGuard/降级序单测（V1c/V5/V5b）不得长期 xfail。

**不要求**：PERFECT>0；开审查优于关审查；α 升到整文件 AST 拼装（方案 B）；档 3 打开或档 3 成功率；LLM 审失败真实性；`weak_green` 清零。

---

## 11. 风险登记

| 风险 | 影响 | 缓解 |
|------|------|------|
| 测试 Call-shape 仍泄漏期望 | 金标偏置 | AST 丢 Assert；人工抽检 snippets |
| 挖掘噪声导致仍 WRONG_LAYER | 自由路径改善有限 | Recipe 播种+一票否决；只印 printable；confidence 过滤 |
| 多形态冲突随机印刷 | 测错层 | `AMBIGUOUS_API` → contract_only；Recipe 锁定优先 |
| render_blocked 过多 | 有脚本↓ | 先保证四卡 `emit_template`+槽位闭合；档3默认关不强充 |
| emit_template 槽位与 inputs 对不齐 | `MISSING_SLOT` | 填表强制注入槽位表；BC 预检；`slot_aliases` |
| 标识符子串重绑定 | 语义错难查 | 仅 `__SLOT_*__`；单测防 `data`/`database` 误伤 |
| 缺 Model/类型 NameError | calib 失真 | arrange → prelude → `UNBOUND_NAME`；禁 NOT_IMPLEMENTED |
| 档3 打开导致 WRONG_LAYER | 测错层 | 默认 `enable_bind_mode_signature=False` |
| 全仓 AST / README 噪声 | 超时、假 call | L0 漏斗 + 符号反查预算；README 默认可解析才入库 |
| 挖到了但印刷机不用 | γ 无效 | α 强制消费 printable（占位）/ emit_template；禁止退回 `None # invoke` |
| 印刷阶段再引入 LLM | 不可回归 | D5 红线；code review 拒 |
| web/cli 模板不足 | 部分题 contract_only | 分期；先啃 lib 契约簇 |
| 指标误读 | 管理误判退步 | 报告强制双口径 + 「假卷→contract_only」算质量进步；calib↓ 若因拆凑红属预期 |
| α/linter EG 双标准 | 漏拦假失败 | D7：单一 `check_failure_semantics` |
| 字符串误杀 NOT_IMPLEMENTED | 误伤产品异常/注释 | 按 Raise 节点 + 帧位置；见 §5.3.3/§5.3.4 |
| 为弱绿凑红回潮 | 破坏 δ | F-weak-green 允许 s1 + 打标；禁止假 raise；KPI 单独统计 |
| `print`/mock 冒充产品 Call | 漏拦假绿 | EG-02 黑名单 + 符号启发 + SUT 顶层包 |
| 第三方 SUT 被 EG-02 误杀 | 好卷 blocked | 产品 Call 含已安装 SUT 包名（DRAFT.7） |
| raises 块自抛具体异常 | 伪造红/假绿 | EG-03：块内必须产品 Call |
| provenance「无产品帧」误杀 | 错杀好卷 | 标 unknown；synthetic 优先显式凑红/无 Call |
| evidence 缺失当 calib | 假胜利 | `missing` 不得 calib_pass |
| 降级「或」含糊 → 空手/乱交 | P0-3 回潮 | D8 降级序 + free_fallback 1b |
| stub→契约池空过多 contract_only | 无强自由稿 | `free_fallback_on_contract_fail` 默认开 |
| EG 未过写入正式 test_feature | ART 假一致 | PersistGuard + rejected/ |
| 下游读 rejected 当金标 | 假交卷外泄 | `official_script_only` + official_script_path |
| 把 s1_accept/弱绿当金标 | 指标误读 | weak_green 报表；主口径仍是卷面 |

---

## 12. 附录

### 12.1 与 v3.4 设计条款的关系

| 3.4 条款 | 3.5 处置 |
|----------|----------|
| S1 Renderer MVP | **作废假桩**；按本文 α **方案 A**（CallPlan + 三段排放）重做 |
| UsageRecipe 轻量挖掘（默认关） | **升级为默认开的 γ（漏斗+并行）**；并按 D1 允许 test Call-shape |
| O4 不读官方测试正文 | **修订为**不读断言意图 / 可读 Call-shape |
| 表审 / SCC-L | 代码保留，**默认关**（D3） |
| `s1_accept` / forbid_no_script | **语义收紧**（D2/D8）；废除 degraded s1 |
| Recipe 四卡 | **保留**；补 `emit_template` 真展开；并作为 γ L0 种子与融合硬闸 |

### 12.2 决策一览（给评审）

| ID | 决策 | 一句话 |
|----|------|--------|
| D1 | 测试可挖 Call-shape；并行采集排序非纯瀑布 | 要用法不要答案 |
| D2 | 保留 s1_accept，加 EG；弱绿打标；废除宽 s1 | 交卷必须可执行 |
| D3 | 语义审查默认关 | 先修印刷机 |
| D4 | γ：漏斗+并行+Recipe 双角色；sufficiency 以可印刷为准 | 燃料要能印，不是挖更多字 |
| D5 | α：方案 A CallPlan + 三段排放；档3默认关；窄AST仅辅助 | 不发明用法，印不出就 blocked |
| D6 | 显式占位重绑定 + Recipe 槽位↔填表闭合 + arrange 窄版 | 防瞎 replace / 名存实亡档1 / NameError |
| D7 | δ：SUT 第三方算产品 Call + α 只调 check_failure_semantics + missing/弱断言边界 | 红绿诚实，防误杀误放 |
| D8 | β：降级序含 free_fallback + PersistGuard + 下游只认正式脚本 | 先抢合法卷，再交契约，禁止假盘/空手 |

### 12.3 修订历史

| 版本 | 日期 | 说明 |
|------|------|------|
| `3.5.0-DRAFT.1` | 2026-07-22 | 初稿：γ→α→δ→β + D1/D2/D3 + 工作包与排期 |
| `3.5.0-DRAFT.2` | 2026-07-22 | γ 改为漏斗+并行采集+Recipe 全程约束；补 sufficiency/`printable`/时序；α 冲突与消费边界；新增 D4 |
| `3.5.0-DRAFT.3` | 2026-07-22 | α 锁定方案 A：CallPlan/`RenderResult`/`emit_template`/三段 Emit/All-or-nothing；新增 D5；同步排期与验证 |
| `3.5.0-DRAFT.4` | 2026-07-22 | 落实四条 α 技术债：①档2仅`__SLOT_*__`/窄AST ②槽位↔填表闭合/`MISSING_SLOT` ③arrange/`UNBOUND_NAME` ④档3默认关；新增 D6 |
| `3.5.0-DRAFT.5` | 2026-07-22 | δ 扩写 §5.3：失败分类学、EG 检测 DRY、provenance/EG-06、β 消费表；新增 D7；同步排期/验证/开关 |
| `3.5.0-DRAFT.6` | 2026-07-22 | 落实 δ/β 审查补丁：产品 Call 黑名单、raises 自抛全覆盖、provenance 防误杀/per-AC/weak_green；D8 降级序+PersistGuard+DraftPicker 序+JSON 五步；同步 D2/端到端/验证/开关 |
| `3.5.0-DRAFT.7` | 2026-07-24 | δ/β 小补丁：SUT 第三方产品 Call；α 自检只走 failure_semantics；provenance `missing`；弱断言≠stub_pass；D8 free_fallback(1b)；下游只认正式脚本；ART 可执行交卷集合；同步开关/验证/风险 |