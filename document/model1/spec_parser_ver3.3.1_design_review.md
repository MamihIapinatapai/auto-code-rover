# Spec Parser ver3.3.1 设计审查报告

> **审查对象**：[`spec_parser_ver3.3.1_design.md`](./spec_parser_ver3.3.1_design.md)  
> **审查 Prompt**：[`prompts/review_ver3.3.1_design_prompt.md`](./prompts/review_ver3.3.1_design_prompt.md)  
> **基线**：ver3.3.0（证据链 + 决策链，已落地）；探针失败模式见 v3.2 synthesis  
> **日期**：2026-07-16

---

## 0. 一句话裁决

**有条件开工（Conditional Go）**：ScriptAnchor **能**针对当前最大卷面短板（OVER_SPEC / WRONG_LAYER）形成真实因果提升，且与 3.3 双链互补而非重复；但须先消化下文 **Blocking** 项（尤其 v3 默认无 enrich 时的索引来源、Tier2 时序、验收度量、错误锚定防护），否则存在「带着错签名更自信地写错脚本」的净负风险。

---

## 1. 执行摘要

1. **对症**：3.3 解决「知不知道测到了」；3.3.1 补「仓库里真实入口/签名是什么」——这正是 v3.2 audit 里 adaptix `Retort(name_mapping=…)`、aiomonitor CLI 代理的根因缺口。
2. **预期收益不均**：对 **OVER_SPEC、WRONG_LAYER** 高；对 **WEAK_ASSERT / NARROW / PERFECT** 低；对 Stub/ENV 多为间接或无直接帮助。
3. **Tier1 是 P0 价值核**：pyproject console_scripts + Issue 符号 AST 签名即可解释大部分「猜错参数/测错层」；Tier2 是增强，不应阻塞 D。
4. **设计优点**：Issue 驱动、限量注入、排除测试路径、不 calib_fail 于 Anchor 缺失、与决策链节点挂钩——方向正确。
5. **最大风险**：符号重名 / 错文件 → 错误 `signature_ast` 被 Prompt 写成硬事实；设计有 confidence，但**缺少「冲突时 Issue 示例优先 + 低置信不注入 kwargs 细则」的生成侧硬规则**。
6. **代码偏差**：v3 pipeline **默认关闭** `repo_enrichment`（`pipeline.should_run_repo_enrichment`），设计写「enrich 后或并行」易误导实现者以为索引已在路上——Tier1 必须**自建/缓存 `symbol_index`**，不能依赖 P2 enrich。
7. **Tier2 时序偏晚**：首次生成已用错签名时，要等 sandbox 后才有 runtime；需明确「首轮仅 Tier1、Tier2 只服务 regen」或「轻量 pre-gen import 探针（可选）」。
8. **验收偏软**：`script_anchor.json` 15/15 有文件 ≠ 质量提升；缺可自动统计的 **signature-consistency / wrong_layer-with-entry-present** 指标。
9. **score_v331 签名违规启发式**易误报，设计已标 soft——建议 **Phase G 默认权重 0 或延后**，避免 best-of 被噪声支配。
10. **建议**：修完 Blocking 后按 **Phase D → E → F → G** 开工；先用 adaptix / aiomonitor / httpx 三题冒烟验证「签名一致率 + CLI entry 点名」。

---

## 2. 质量提升有效性评估

### 2.1 按失败模式（D1–D6）映射

| 模式 | 代表题 | Anchor 帮助 | 评级 | 说明 |
|------|--------|-------------|------|------|
| **OVER_SPEC**（猜错签名/参数） | adaptix Retort、cattrs partial | 直接提供 AST/inspect 签名 | **高** | audit 已证 `Retort(*, recipe=())` vs 脚本 `name_mapping=`；正是 Tier1/2 靶心 |
| **WRONG_LAYER**（CLI/Web 用底层 API） | aiomonitor AC-007/008 | console_scripts + layer_gap + 生成约束 | **高** | 3.3 只会事后 warning；入口元数据才能在**生成前**改测层 |
| **WEAK_ASSERT** | aiomonitor diff 只验键 | 几乎无 | **低** | 签名对了仍可能弱断言；仍靠 Issue/coverage_chain |
| **NARROW**（漏边角 Must） | httpx aiter 等 | 间接 | **低** | Anchor 不扩展 Must 列表；可能略助「知道有哪些公开方法」 |
| **Stub / existence** | gql/dateutil/psd | 间接（给最小合法调用模板） | **中低** | 有助于 blocking_fixes 例题；不替代 L14/early-stop |
| **骗 Lint / ENV** | sqlfmt、bandit yaml | 无直接 | **无** | 已由 3.3 L14/ENV 覆盖；Tier2 需避免二次污染 |
| **越修越差** | narwhals | 弱（score 软项） | **低** | 勿指望 Anchor 修选稿；保持 3.3 best-of |

**结论**：能提高「契约正确性与测层正确性」相关的脚本质量；**不能**单独把 PARTIAL 全面推到 STRONG/PERFECT。与 3.3 叠加后，预期是 **STRONG 更稳、OVER_SPEC/WRONG_LAYER 类 PARTIAL 下降**，而非产出率暴涨。

### 2.2 因果链验证

```text
Issue 点名符号/CLI
  → Tier1 定位 + AST 签名 / console_scripts   （确定性事实）
  → 注入 ScriptAnchor 块到生成 Prompt
  → 模型少编造 kwargs、优先 CliRunner/entrypoint
  → 审视 coverage + layer_gap 用同一事实纠偏
  → audit：OVER_SPEC / WRONG_LAYER 下降
```

**成立条件**：

1. 注入的签名/入口**正确**（否则因果反向）；
2. Prompt 约束被遵守（软约束需审视回灌 + 可选启发式，不能只靠一段 Rules）；
3. Issue 行为期望仍优先（设计 §12 已写，需落到生成绝对约束更醒目）。

adaptix 案例证明：仅有 Issue 明文不足以阻止错误接线；**仓库签名是缺失的第二 oracle**。因果成立。

### 2.3 预期指标变化（相对 3.3）

| 指标 | 相对 3.3 | 信心 |
|------|----------|------|
| 产出率 | 持平或微降（设计已允许 ≥11/15） | 中 |
| STRONG | 微升或更稳（尤其库 API 题） | 中 |
| OVER_SPEC 类 PARTIAL | **明显下降**（若 Tier1 命中） | 中高 |
| WRONG_LAYER（有 entry 的题） | **下降** | 中高 |
| WEAK/NARROW | 基本不变 | 高 |
| `script_anchor.json` 覆盖 | 易达成但**不证明质量** | — |

---

## 3. Rubric 打分表（R1–R10）

| ID | 维度 | 判定 | 理由 |
|----|------|------|------|
| R1 | 问题对齐 | **Pass** | 明确对准 OVER_SPEC/WRONG_LAYER；不重复造 L14/ENV |
| R2 | 因果有效性 | **Partial** | 对签名/入口成立；需强化「错锚定防护」才稳 |
| R3 | 覆盖缺口 | **Partial** | 对 D1 子集强；对 WEAK/NARROW/Stub 弱——文档已承认，可接受 |
| R4 | 双链集成 | **Pass** | D_anchor_* + coverage bridge + 审视注入结构清楚 |
| R5 | 仓库复用 | **Fail→须改** | 复用模块存在，但 **v3 默认无 enrich**；未写死「Anchor 自建 index」 |
| R6 | 时序 | **Partial** | Tier1 前、Tier2 后合理；「首轮已错签」的再注入策略不够硬 |
| R7 | 硬约束 | **Pass** | 禁测文件、禁 solution、sample_test 不作 oracle |
| R8 | 成本风险 | **Partial** | 有截断/上限；缺「低置信不注入详细签名」策略 |
| R9 | 验收可证伪 | **Partial** | 有抽检意图；缺自动 proxy 指标 |
| R10 | 分期 | **Pass** | D→E→F→G 清晰；Tier1 可独立 |

---

## 4. 必须修改（Blocking）

### B1. 写清：v3 下 Tier1 **独立构建 symbol_index**（不依赖 repo_enrichment）

- **问题**：`pipeline.configure_repo_enrichment` 在 v3 默认 `enable_repo_enrichment=False`；设计 §3.2「enrich 后」易让实现者漏建索引。  
- **为何阻塞**：无 index → Anchor 空或仅靠慢 grep → 收益归零或噪声。  
- **改法**：在 §5.1 / §10 增加：

> Tier1 **必须**调用 `build_symbol_index(task.project_path)`（可 LRU 缓存）；`repo_enrichment` 仅可选共享已解析路径，**非前置依赖**。v3 默认关闭 P2 不影响 Anchor。

### B2. 低置信 / 多命中时的注入策略（防「错签名害人」）

- **问题**：错 `Retort` 定义文件或重名函数 → 错误 AST 被写成「prefer these signatures」。  
- **为何阻塞**：比无 Anchor 更糟（模型更敢用错 kwargs）。  
- **改法**：补充规则：
  - `confidence < 0.5`：**只注入 name + rel_path**，不注入参数列表；或标 `AMBIGUOUS`；
  - 多命中：注入 top-1 **并**列出 alternate paths（≤2），禁止假装唯一；
  - 生成绝对约束加一句：`If ScriptAnchor marks ambiguous/low-confidence, prefer Issue code blocks over signature_* for call shape.`

### B3. Tier2 与首轮生成的关系写死

- **问题**：图上 Tier2 在 sandbox 后；首轮生成看不到 `signature_runtime`。adaptix 类题首轮就可能写错。  
- **改法**（二选一，文档须选定默认）：
  - **推荐**：Tier1 足够支撑首轮；Tier2 **仅** enrich 后写入 anchor，并在 **regen feedback** 置顶 runtime 签名冲突提示（`D_anchor_inspect` + 自动 diff AST vs 脚本调用）。
  - **可选加速**：生成前对 top-N 符号做一次「轻量 import+inspect」（失败则 skip），与校准 sandbox 隔离超时；成功则首轮即用 runtime。  
- 明确：**禁止**因等 Tier2 而推迟首轮生成。

### B4. 验收增加「质量 proxy」，避免只数 json

- **问题**：`15/15 script_anchor.json` 不能证明脚本变好。  
- **改法**：在 §14 增加至少两项可统计目标（可用启发式，允许噪声）：
  1. **Signature consistency（抽检+启发式）**：对 Anchor `confidence≥0.8` 的符号，脚本调用的关键字参数名 ⊆ signature 形参名的比例（adaptix/cattrs/httpx 子集报告）。  
  2. **Entry-aware wrong_layer**：`layer_hints.cli==present` 且 Issue 含 CLI 时，脚本含 CliRunner/console 名 / entrypoint 的题数 ↑。  
  3. 人工：adaptix 不得再出现 `Retort(name_mapping=` 作为主路径（对照已知 audit）。

### B5. `flag_over_spec_calls` / score 签名违规：默认关闭或极低权重

- **问题**：静态扫「脚本里有、Issue/Anchor 没有的 attr」误报极高（本地变量、测试夹具名）。  
- **改法**：Phase E bridge **只产出 reviewer hints**；`anchor_signature_violations` **默认不计入** `draft_score`（权重 0），Phase G 再 A/B。

---

## 5. 建议微调（Non-blocking）

| ID | 建议 |
|----|------|
| N1 | Prompt 中 ScriptAnchor 块放在 **Issue 之后、AC 表之前或紧后**，并用一行加粗：`Issue behavior overrides Anchor when they conflict on expected values`（设计已有，建议排版更醒目） |
| N2 | `layer_hints` 对「Issue 要 CLI 但只有 library」→ `absent` vs `unknown` 语义表再写清，避免审视过度 panic |
| N3 | Tier2 探针白名单强调：只 inspect Anchor 内符号；stdout JSON 大小上限 |
| N4 | httpx 金标冒烟：确认 Anchor 不把内部 `_client.py` 私有细节过度注入导致 OVER_SPEC 反向（偏好公开 `Client` API） |
| N5 | `public_export` / `__all__` 标为可选；P0 可不做，以免拖延 Phase D |
| N6 | 设计状态与 3.3 交叉引用已较好；实现后把 §14 产出目录 conf 样例一并提交 |
| N7 | 审视 Prompt 注入 `anchor_json_compact` 时同样受 `anchor_prompt_max_chars` 约束，避免 double 膨胀 |

---

## 6. 可保留的优点

1. **问题定义清晰**：运行/入口/契约/语义四层，且拒绝全库 AST——符合验收脚本场景。  
2. **与 3.3 分工正确**：行为 oracle=Issue；调用契约=Anchor；门禁仍 lint/Gate。  
3. **失败降级友好**：Anchor 空仍生成；Tier2 degraded；layer_gap 默认不拒落盘。  
4. **安全边界清楚**：排除 test 路径；不把 sample_test 写入 Anchor。  
5. **分期合理**：Phase D 可独立交付可见价值（prompt 注入）。  
6. **有真实靶心**：adaptix Retort 签名错误是已文档化的致命问题，本设计直接可打。

---

## 7. 实现优先级建议（有条件开工）

```text
先改设计文档 Blocking B1–B5（小补丁即可）
    ↓
Phase D（Tier1 + prompt 注入 + D_anchor_build）  ← 最大 ROI
    ↓
Phase E（layer_gap + 审视 compact Anchor）       ← 打 WRONG_LAYER
    ↓
Phase F（Tier2 inspect → regen 优先）            ← 加固 OVER_SPEC
    ↓
Phase G（探针回归；score 软项默认关）
```

**若只能做一层：只做 Tier1。** Tier2 在 import 路径混乱（如 adaptix 需 `PYTHONPATH=src`）时易 degraded，不能当首依赖。

**冒烟最小集**：

| 题 | 验证点 |
|----|--------|
| adaptix | Anchor 含 `Retort(..., recipe=...)`；生成/再生不再主用 `name_mapping=` 构造 |
| aiomonitor | entrypoints/cli hint present 时，feedback/生成提及 CLI 入口 |
| httpx-multipart | 公开 API 签名可见且金标不回归 |

---

## 8. 审查附录：与代码现状偏差

| 设计假设 | 代码事实 | 审查结论 |
|----------|----------|----------|
| enrich 后做 Anchor | v3 默认 `spec_parser_enable_repo_enrichment=False` | **B1**：Anchor 自建 index |
| 复用 `symbol_index` / `entity_extraction` | 模块存在且已排除 test 文件 | 可行，直接复用 |
| `collect_entities(issue, draft, index)` | API 匹配 | 可行；需补充 AC/Issue token 种子策略的单测 |
| 3.3 coverage / decision 已存在 | 已落地 | E/F 可接；D 可不依赖 coverage 解析 |
| sample_test_excerpt 仍在 RepoContext | `repo_context` 仍有 excerpt | 设计禁止写入 Anchor——实现时勿「顺手」抄进 script_anchor.json |

### 8.1 对「是否真正提高复现脚本质量」的最终回答

| 问题 | 回答 |
|------|------|
| 能否提高？ | **能，但是结构性、有偏的提升**（契约层 + 入口层），不是全面卷面升级 |
| 最大收益 | **Tier1**（AST 签名 + console_scripts） |
| 最大风险 | **错误锚定被当作事实**（B2） |
| 与 3.3 关系 | **互补**：3.3 管覆盖与门禁；3.3.1 管「怎么合法调用仓库」 |
| 是否建议实现 | **是，有条件开工**（先补 B1–B5） |

---

## 附录：建议贴回设计文档的补丁提纲（供作者编辑）

1. §3.2 / §5.1：增加「Tier1 独立 `build_symbol_index`，不依赖 P2 enrich」。  
2. §4.1 / §5.4：增加低置信与 ambiguous 注入规则。  
3. §6：增加「Tier2 默认仅服务 regen；首轮不阻塞」及可选 pre-gen inspect。  
4. §8.3：`anchor_signature_violations` 默认权重 0。  
5. §14：增加 signature-consistency 与 entry-aware 指标。  

---

*本报告由审查 Prompt 驱动完成；未改业务代码。*
