# Spec Parser ver3.0 — 复现脚本质量优化计划

**基于**: `v3_calib_script_quality_synthesis.md`（34 题横截面）  
**对照代码**: `app/spec_parser/{calibration_gate,script_linter,script_prompts_v3}.py`  
**日期**: 2026-07-15  
**状态**: 计划草案（待实施）

---

## 0. 问题诊断摘要

本批 calib 核心矛盾：

> 系统很会让脚本在 buggy 上 **exit≠0**，但不保证失败语义对味、结构可执行、与 Issue Must 对齐。

判定分布：**STRONG 9 / PARTIAL 9 / INVALID 16 / PERFECT 0**。

| 技术根因（已核对代码） | 后果 |
|------------------------|------|
| FEATURE 校准近似「exit≠0 即过」 | pytest/sympy 的 `ModuleNotFoundError` 可假校准 |
| `classify_stderr_script_error` 只匹配字符串 `"ImportError"` | `ModuleNotFoundError` 可能漏拦 |
| `spec_parser_use_v3_prompts` 默认 `False` | L10-EXISTENCE-ONLY、v3 Prompt **默认未启用** |
| L4 仅拦 `except`+`return False` | `except: pass` 拦不住 |
| 无 L11/L12 | 死代码 AC、Stub 无静态闸 |

**结论**：优先 **Gate/Lint 止血**，再 Prompt，再 P1 规格；不要先上大而全的「Issue 对话澄清」来解决本批主缺陷（见 §5）。

---

## 1. 目标与非目标

### 1.1 目标

| 指标 | 基线（本 calib） | Phase 1 目标 | Phase 2 目标 |
|------|------------------|--------------|--------------|
| INVALID 中「假校准」占比 | 高（ENV/Stub/DEAD+calib_passed） | 探针集上坏卷 `calibration_passed=false` | 同左稳定 |
| 有意失败占比 | 混杂 ENV | stderr 含 `AC-xxx FAIL` 为主 | ≥80% 过校准脚本 |
| existence-only must AC | 常见 | L10 blocking 生效 | P1 少产出 existence must |
| PERFECT_MATCH | 0 | 不强制 | 精读子集出现 ≥1 |

### 1.2 非目标（本计划不做）

- 恢复 P2 AST / SymPy 全家桶  
- 以 LLM-as-judge 作为 Phase 1 唯一门禁  
- 用「向用户提问」作为默认路径（DeepSWE 无人类在环）

---

## 2. 分阶段实施计划

### Phase 1 — 止血假校准（P0，约 2–3 天）

#### P0-1 Gate：有意 AC 失败判定

**文件**: `calibration_gate.py`

**改动要点**:

1. `classify_stderr_script_error`：将 `ModuleNotFoundError` / `No module named` 与 `ImportError` 同等处理。  
2. FEATURE：`exit!=0` **且**（`AC-.*FAIL` 或 `NOT_IMPLEMENTED`+`AssertionError`）；拒绝纯 ENV。  
3. 可选黑名单：`pytest`、`sympy` 等与 Issue/仓库无关的缺包 → 一律 script error。

**验收**: 探针 `aiomonitor` / `gql` / `sqlfmt` / `psd-tools` / `bandit-structured` 上坏卷不得 `calibration_passed=true`。

#### P0-2 Lint：L11-DEAD-AC + L12-STUB-AC + 修 L10

**文件**: `script_linter.py`

| 规则 | 逻辑（摘要） | 级别 |
|------|--------------|------|
| L11-DEAD-AC | 存在 `def test_*` 且执行路径未 Call | blocking |
| L12-STUB-AC | AC 段仅 `raise AssertionError("Stub...")` | blocking |
| L10-EXISTENCE-ONLY | 修判定：仅 `assert hasattr/callable/True` 不算行为；**默认启用**（与 v3 开关解耦或默认打开 v3） | blocking |
| L13-VACUOUS | `assert True` | blocking |

**验收**: `sqlite-utils` / `igel` / `adaptix` 类模式被 preflight 打回。

#### P0-3 Prompt 补强

**文件**: `script_prompts_v3.py`

新增硬禁止 bullet：

- 禁止只定义不调用的 `test_*`  
- 禁止 `assert True` / 无条件 Stub  
- 禁止无关 `import pytest`  
- 禁止宽 `except Exception: pass`  
- FEATURE：≥1 happy + ≥1 negative 行为断言  

并评估将 `spec_parser_use_v3_prompts` 默认改为 `True`（或 calib 强制 True）。

#### P0-4 回归探针集（12 题）

见 `v3_calib_script_quality_synthesis.md` §7；另保留金标：`httpx-multipart`、`httpx-streaming`、`cattrs`。

---

### Phase 2 — 提高卷面质量（P1，约 1 周）

| ID | 项 | 落点 | 验收 |
|----|-----|------|------|
| P1-1 | 硬化 L4：`except: pass` / 无 `raise AssertionError` 的宽捕获 | script_linter | mashumaro 类被拦 |
| P1-2 | must AC 禁止纯 existence observable | P1 validator / contract_refiner | existence must 占比↓ |
| P1-3 | NO_SCRIPT → `calibration_error=NO_SCRIPT`，禁止标定通过 | agent + gate | D-NOOUT 不进成功计数 |
| P1-4 | repair_draft 增加 `behavioral_examples[{input,expect}]` | repair_draft.py | 生成侧少空断言 |

---

### Phase 3 — 覆盖与测偏（P2，可选）

| ID | 项 | 说明 |
|----|-----|------|
| P2-1 | AC 角色 `happy/negative/edge` 强制各 ≥1 | 抬 D-NARROW |
| P2-2 | sample_test_excerpt + L9 扩展 | 减 D-WRONG |
| P2-3 | symptom_aligner heuristic 落地 | 对齐 ver3 文档 M18；**BUG_FIX 优先** |

---

## 3. 效果–可行性矩阵（决策）

| 方案 | 主缺陷 | 效果 | 可行性 | 优先级 |
|------|--------|------|--------|--------|
| Gate 有意失败 + ModuleNotFoundError | D-ENV/D-CALIB | ★★★★★ | ★★★★★ | P0 |
| L11 死代码 | D-DEAD | ★★★★★ | ★★★★★ | P0 |
| L12 Stub | D-STUB | ★★★★★ | ★★★★☆ | P0 |
| 启用/修 L10 + assert True | D-EXIST/VACUOUS | ★★★★☆ | ★★★★★ | P0 |
| Prompt 硬禁止 | 生成侧 | ★★★☆☆ | ★★★★★ | P0 伴随 |
| 硬化 L4 | D-SWALLOW | ★★★☆☆ | ★★★★☆ | P1 |
| NO_SCRIPT 闸 | D-NOOUT | ★★☆☆☆ | ★★★★★ | P1 |
| P1 AC 行为化 | D-EXIST/NARROW | ★★★★☆ | ★★★☆☆ | P1–P2 |
| 角色覆盖 / 测偏 grounding | D-NARROW/WRONG | ★★★☆☆ | ★★☆☆☆ | P2 |
| Issue 主动澄清（全量） | 见 §5 | 场景依赖 | 中 | **非本批主药** |

---

## 4. 模块改动清单（实施 checklist）

- [x] `calibration_gate.py`：ModuleNotFoundError；FEATURE 有意失败（**v3.1 已落地**）  
- [x] `script_linter.py`：L11/L12/L13；修 L10；硬化 L4（**v3.1 已落地**）  
- [x] `script_prompts_v3.py`：硬禁止 bullet（**v3.1 已落地**）  
- [x] `config.py`：`spec_parser_use_v3_prompts` 默认 `True`；`pipeline.V3_PARSER_VERSION=3.1.0`  
- [x] `test/app/spec_parser/`：gate + linter v3.1 单测  
- [ ] 重跑探针 12 题 calib，更新本目录 `AUDIT_INDEX` / 合成报告附录  

**明确不做（除非新产品需求）**：为 Phase 1 引入多轮「向用户提问」的人机澄清环。

**Git 基线**：
- Tag `spec-parser-v3.0.0` @ branch `feat/spec-parser-v3.0-baseline`
- Tag `spec-parser-v3.1.0` @ branch `feat/spec-parser-v3.1-script-quality`（本改动）

---

## 5. 专题：Issue 歧义 / 信息噪声 vs「主动澄清」方案

> 回应问题：Issue 是否常有误导性最小复现、不准栈、多 bug 混写？当前 Agent 是否应对所有文本一视同仁？能否用「需求引出式主动澄清 + 执行片段验证 → Failure Specification」解决？

### 5.1 本批 DeepSWE Python calib 的证据

| 观察 | 含义 |
|------|------|
| 任务类型以 **FEATURE** 为主 | 多数是「规格说明书」而非「带错误栈的 bug 报告」 |
| SWM 中 `issue_completeness.completeness` 常为 `full`，`reporter_drafts` 多为 `[]` | Parser 自身也未标出大量 reporter 噪声 |
| 主缺陷是 **脚本结构/门禁**（DEAD/ENV/STUB/EXIST），不是「信了错误栈」 | 优化 ROI 在 Gate/Lint，不在澄清对话 |
| 存在的「歧义」偏规格型 | 如「creation 时报错」是构造期还是 `get_loader`；返回 dict 还是属性对象——**欠具体**，未必是**误导** |

因此：

- **「用户 Issue 经常含错误最小复现 / 干扰栈 / 双 bug 混写」** 在经典 SWE-bench **BUG_FIX**、真实工单中成立，是重要研究方向。  
- **在本批 DeepSWE FEATURE calib 中并非主因**；把主动澄清当本批主修复路径会 **错配问题**。

### 5.2 噪声类型细分（建议 Agent 分类信任，而非一视同仁）

| 层级 | 内容 | 建议信任策略 |
|------|------|----------------|
| L0 权威 | Issue 正文对「期望行为」的陈述 | 高信任（硬锚） |
| L1 可证伪 | Issue 内代码块 / 声称的复现步骤 | **中信任**：应用执行验证，失败则降权而非盲从 |
| L2 定位暗示 | 栈帧、文件:行号、归咎模块 | **低信任**：易被中间件/装饰器污染；只作搜索种子 |
| L3 草稿 | reporter patch、半截修复 | **hint only**（ver3 已写：reporter_drafts 非权威） |
| L4 流程噪声 | 「开新分支并 commit」类 IMPORTANT | 过滤（已有 out-of-scope 思路） |

ver3 文档已有信任序：

`Issue 原文 > AC.observable > repair_goals > reporter_drafts > covers_entity`

缺口是：**L1 代码块缺少「跑一下再信」**，以及 **L2 栈缺少显式降权**——这与「一视同仁」批评一致，但应用 **执行校验 + 分级信任** 补，而不是默认开启多轮澄清问答。

### 5.3 对「主动澄清 + Failure Specification」方案的评估

**方案摘要（用户提议）**：定位前分析歧义 → 生成消解问题 → 执行 Issue 片段验证复现 → 输出结构化 Failure Spec（前置条件、触发路径、预期行为）。

#### 可取之处

1. **与软件工程「需求引出」同构**，适合 BUG_FIX：症状不清、复现不稳、多因混杂时，先收敛 Failure Spec 再搜补丁，方向正确。  
2. **「执行片段验证」是关键**：把 L1 从文本断言变成可证伪证据，比纯 LLM 自评可信度强。  
3. **输出三元组**与 ver3 已有概念可对齐：  
   - 前置条件 ≈ sandbox 环境 / fixture  
   - 触发路径 ≈ failure_anchor + repro 步骤  
   - 预期行为 ≈ RepairDraft / AC.observable  
   不必另起一套完全独立的 ontology。  
4. **可缓解**：错 repro、混 bug、栈指向装饰器而非根因等 **BUG_FIX** 痛点。

#### 风险与局限

| 风险 | 说明 |
|------|------|
| **无人在环** | DeepSWE/自动 Agent 不能「问用户」；澄清问题必须改成 **自问自答**（对仓库执行假设 / 对比多假设），否则流水线卡住 |
| **FEATURE 无「失败」可引出** | 本批多数题是新行为规格；Failure Spec 模型别扭，应叫 **Acceptance Spec**（输入→期望），与 FEATURE 校准一致 |
| **执行不可信片段** | Issue 代码可能依赖未声明环境、网络、私钥；需沙箱、超时、只读、禁网（与现 P5 sandbox 同约束） |
| **澄清问题质量** | LLM 生成的「是否涉及 X 模块 Y 行为」易空转；应绑定 **可执行探针**（跑 A 还是跑 B）而非是非题 |
| **成本** | 多一轮 LLM + 多次执行；若放在每题默认路径，延迟/token 上升明显 |
| **不能替代 Gate/Lint** | 即使 Failure Spec 完美，DEAD/Stub/ENV 假校准仍会发生——那是生成与门禁问题 |

#### 可行性结论

| 场景 | 是否采用该方案 | 建议形态 |
|------|----------------|----------|
| 本批 FEATURE calib 主缺陷 | **否（不作主路径）** | 先落地本文 Phase 1 Gate/Lint |
| 未来 BUG_FIX / 真实噪声工单 | **是（精简版）** | 见 §5.4「静默自澄清」 |
| 全量默认「生成澄清问题等人答」 | **否** | 无人类在环产品不适用 |

**总评**：思路 **方向正确、宜作 BUG_FIX 前置模块**；对当前 calib **ROI 低于 Phase 1**；落地时应改为 **无人类在环的执行驱动自澄清**，输出并入现有 `RepairDraft` / `failure_anchor`，避免平行两套规格。

### 5.4 推荐的精简落地（若做「可信度」，放 Phase 2–3）

命名建议：**Silent Elicitation / Evidence-weighted Issue Parse**（静默引出），不做聊天式 Q&A。

```text
P1 结构化
  → P1.4 claim_extractor：区分行为声明 / 代码块 / 栈帧 / 草稿
  → P1.5 claim_verifier（sandbox）：对可运行代码块试跑
        成功复现 → 升权写入 Failure/Acceptance Spec
        失败/环境不足 → 降权为 hint，不硬锚 assert
  → P1.6 repair_draft：只含「已验证或高信任」条款
  → P4 脚本生成（仍受 Lint/Gate 约束）
```

**Failure/Acceptance Spec 最小字段**（可嵌进 RepairDraft）：

```python
class VerifiedClaim(BaseModel):
    kind: Literal["behavior", "repro_snippet", "stack_hint", "draft"]
    trust: Literal["anchor", "verified", "hint", "discard"]
    precondition: str | None
    trigger: str | None          # 触发路径 / 调用
    expected: str | None         # 期望行为或异常
    evidence: str | None         # stderr / exit / 未跑原因
```

**歧义消解**用「竞争假设 + 执行」代替「问用户」：

- 假设 A：异常在业务函数 X  
- 假设 B：异常仅中间件包装  
- 各生成最小探针，看哪条与 Issue 声称症状一致  

这与 ver3 规划的 `symptom_aligner`、reporter_drafts 降权 **同族**，应合并进 M18，而不是另起「对话 Agent」。

### 5.5 与 Phase 1 的优先级关系

```text
现在（本 calib）：Phase 1 Gate/Lint/Prompt  → 消灭假卷
并行可选调研：在 1–2 个真实 BUG_FIX 噪声样例上试 P1.5 claim_verifier
之后：噪声工单占比高时，再把静默引出升为默认前置阶段
```

**一句话回答用户疑问**：

1. **Issue 噪声/歧义在真实 BUG 场景确实存在**；本批 FEATURE calib **不是主因**。  
2. **不应**对所有 Issue 文本同等信任——应用分级信任 + 执行证伪。  
3. **主动澄清思路可采用，但须改成无人类在环的执行驱动自澄清**，输出并入 Failure/Acceptance Spec / RepairDraft；**不能替代** 本文 Phase 1 的脚本门禁优化，也 **不宜** 作为当前 FEATURE calib 的第一优先。

---

## 6. 里程碑与退出标准

| 里程碑 | 退出标准 |
|--------|----------|
| M-P0 | 12 探针上：DEAD/Stub/ENV 坏卷无法 calibration_passed；金标 3 题仍能合理 fail |
| M-P1 | L4/L10 稳定；existence must 明显下降；NO_SCRIPT 可观测 |
| M-P2 | 可选：claim_verifier 在 ≥5 个 BUG_FIX 噪声样例上 trust 分级正确率可报告 |

---

## 7. 参考

- `v3_calib_script_quality_synthesis.md`  
- `document/model1/spec_parser_ver3_dev_plan.md` §2.2–2.3（Prompt / Lint / Gate / symptom_aligner）  
- `app/spec_parser/calibration_gate.py`、`script_linter.py`、`script_prompts_v3.py`
