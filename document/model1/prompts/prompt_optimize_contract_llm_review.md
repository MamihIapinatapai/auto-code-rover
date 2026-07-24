# Prompt：分析与优化「表格 LLM 语义复审」Prompt（证据链强制）

> **用途**：丢给架构/Prompt 工程师 LLM，专门打磨 `contract_review_semantics_*`（BehaviorContract 语义复审）的 System/User Prompt，使复审能**精准抓语义问题、完整列点、每点带证据链**，降低偏移与幻觉。  
> **关联**：  
> - 设计规格：[spec_parser_ver3.4_design.md](../spec_parser_ver3.4_design.md) **§3.5.8**  
> - 契约表优化 prompt：[prompt_optimize_contract_first_table.md](./prompt_optimize_contract_first_table.md)  
> **使用方式**：整段复制「可复制 Prompt 正文」为 User Message；末尾粘贴：当前复审 Prompt 草稿、1～2 份已过 BC 的坏/好契约 JSON、对应 Issue 片段。  
> **产出目标**：可直接落地的 `CONTRACT_REVIEW_SEMANTICS_SYSTEM` + `USER` 模板 + 证据链 JSON Schema + 拒幻觉规则。

---

## 可复制 Prompt 正文

```text
# Role
你是资深规格审计官 + Prompt 工程师。你的任务不是「直接审一张表」，而是**设计/改写「表格 LLM 语义复审 Prompt」**，使执行该 Prompt 的复审模型能够：
1. 精准抓取 BehaviorContract 的**语义问题**（不是再做机械 lint）；
2. **完整列出**每个问题点（不合并糊弄、不漏高危）；
3. 每个问题点必须附带**可核验的证据链（Evidence Chain）**，防止凭空指控与偏移；
4. 无证据则不得下结论；证据不足只能标 `insufficient_evidence`，不得假装 `reject_*`。

你熟悉 AutoCodeRover Spec Parser v3.4：机械 `validate_contract`（BC-xx）已是资格门；LLM 复审只审「意思对不对」，且**不能放行 BC 未过的表**。

# Context（必须内化）

## 复审在流水线中的位置
填表(LLM) → validate_contract(机械, blocking) →【本 Prompt 优化对象】语义复审(LLM, 可选) → Renderer → lint/sandbox

## 复审该抓什么（语义）vs 不该抓什么（机械已管）
应抓（语义金标风险）：
- false_fail：expect 与 issue_quote / Issue Must **方向相反或冲突**
- off_must：测的是边角/相关 API，但不是当前 S1 应对准的主 Must
- weak_degraded：confidence=low / raises 探测，但 Issue quote **已有**可升格的具体样例却未用
- recipe_misaligned：BC 形状合法，但 call_graph 相对 Recipe hint / Issue 集成意图「合法却偏题」
- quote_drift：行内 issue_quote 虽是原文子串，但截取导致期望被错误绑定（断章取义）
- multi_item_inconsistency：多行之间 expect/layer 互相矛盾

不应重复机械 BC（除非指出「机械可能漏掉的语义变体」）：
- 空 expect、existence-only、私有 _internal、明显 forbidden_patterns、缺 quote 等
若复审 Prompt 鼓励重复报这些，视为设计失败。

## 历史翻车（复审 Prompt 必须针对性消掉）
1. 复审只说「整体不错 / 建议加强」——无问题列表
2. 指控 false_fail 但不引用 Issue 原句与 expect 字段 ——幻觉
3. 用「常识/库文档记忆」代替 Issue 证据 ——偏移
4. 发明 Issue 未出现的数字/异常类型当「正确期望」
5. 与填表模型同谋：协助通过审核、淡化问题
6. 把脚手架偏好（asyncio.run）当成语义问题，或反过来漏掉 expect 写反

## 硬约束
- 禁止以官方测试 / Harbor / solution.patch 为证据
- 允许证据源仅限：Issue 原文、契约行字段（issue_quote/expect/call_graph/…）、可选 Anchor/Recipe 摘要
- 每个 finding 必须自带 evidence_chain；无链则无效
- verdict 枚举保持与设计一致：pass | warning | revise_expect | reject_false_fail | reject_off_must

# Goal
请**分析并优化「表格 LLM 语义复审 Prompt」**，输出达到可粘贴进代码的粒度。核心优化目标：

| 目标 | 衡量 |
|------|------|
| 精准 | 高危语义问题召回高；对已机械覆盖的形状问题少误报 |
| 完整 | 多问题并列完整列出，禁止「主要问题是…」只写一条了事 |
| 可证伪 | 每条问题有证据链；第三方只看证据链即可复核，不依赖模型「感觉」 |
| 抗幻觉 | 无证据不得 reject；禁止外部知识冒充 Issue 证据 |

# Design Requirements（必须覆盖）

## A. 证据链（Evidence Chain）规范 —— 本任务重心
设计强制结构（建议每条 finding 内嵌）：

```json
"evidence_chain": [
  {
    "step_id": "E1",
    "claim": "一句话断言",
    "source_type": "issue_span | contract_field | recipe_hint | anchor_entry | derived",
    "source_ref": "定位：Issue 行号或字符偏移 / 字段路径如 items[0].expect.value",
    "span_text": "≤120 chars 原文摘录（必须从输入中可找到）",
    "support": "supports | contradicts | neutral"
  }
]
```

要求你规定：
1. **最少证据条数**：例如 false_fail ≥2（一条 Issue/quote，一条 expect 字段）；off_must ≥2（一条主 Must 表述，一条 call_graph/expect 偏题点）。
2. **闭合规则**：最后一步必须显式写出「为何由上述 span 推出问题」；禁止只有结论没有 span_text。
3. **抗幻觉校验指令**（写进复审 Prompt）：模型必须自检 span_text 是否为输入子串；若否，删除该 finding 或改 `insufficient_evidence`。
4. **derived 限制**：`source_type=derived` 最多 1 步，且必须依赖前面非 derived 步骤；不得单独成链。
5. **完整列出**：`item_findings` 中每个非 ok 问题独立一条；同一 must_id 可有多条不同 `issue` 类型；禁止合并成笼统一条。

## B. 问题类型目录（Issue Taxonomy）
给出稳定枚举（可扩展但需固定 id），每种类型规定：
- 定义
- 必查字段
- 最低证据链模板（E1/E2/E3 各看什么）
- 对应 verdict 倾向（revise / reject_false_fail / reject_off_must / warning）
- 反例：什么样的「看起来不对」其实证据不足，应标 insufficient_evidence

至少覆盖：false_fail, off_must, weak_degraded, recipe_misaligned, quote_drift, multi_item_inconsistency, insufficient_evidence, ok

## C. 复审工作流程（写进 Prompt，逐步执行）
不要开放「请审一下」。设计强制步骤，例如：
1. 逐行提取：must_id、issue_quote、expect 摘要、call_graph
2. 在 Issue 全文定位 quote（或归一化后子串）；失败 → quote_drift / insufficient_evidence
3. 对照主 Must 列表（可要求复审先列出「Issue Must 候选」为 evidence 的派生起点，但每条 Must 须带 issue span）
4. 对每个 item 跑 Taxonomy 检查表
5. 汇总全部 findings（完整列表）
6. 再映射总 verdict（规则：存在 reject_false_fail → 总 verdict 同；否则存在 reject_off_must → …；仅 warning → warning；全 ok → pass）
7. 输出前自检：每条 finding 的 span_text 子串核验 + 证据数量门槛

## D. 输出 JSON Schema（升级版，含证据链）
在设计文档现有字段上扩展，至少包含：

```json
{
  "verdict": "pass|warning|revise_expect|reject_false_fail|reject_off_must",
  "blocking": true,
  "item_findings": [
    {
      "finding_id": "F1",
      "must_id": "M1-...",
      "issue": "false_fail|off_must|weak_degraded|recipe_misaligned|quote_drift|multi_item_inconsistency|insufficient_evidence|ok",
      "severity": "blocking|warning|info",
      "claim": "≤200 chars 问题陈述",
      "evidence_chain": [ /* 见上 */ ],
      "fix": "只允许改 expect/fail_mode/confidence 的具体建议；禁止改 call_graph/recipe（除非 issue=recipe_misaligned 且设计允许——默认仍只建议改 expect 或换 must 行）",
      "confidence": "high|medium|low"
    }
  ],
  "must_coverage_notes": [
    {
      "must_candidate_span": "Issue 原文 ≤120",
      "covered_by_must_id": "M1-...|null",
      "note": "主 Must 未覆盖|已覆盖|不确定"
    }
  ],
  "self_checks": {
    "all_spans_substring_verified": true,
    "no_external_oracle_used": true,
    "findings_complete": true
  },
  "summary": "≤200 chars"
}
```

说明：`must_coverage_notes` 用于「完整列出」覆盖缺口，避免只盯单行。

## E. System / User Prompt 正文（最终交付物）
分别写出：
1. `CONTRACT_REVIEW_SEMANTICS_SYSTEM`（完整可粘贴）
2. `CONTRACT_REVIEW_SEMANTICS_USER` 模板（占位符：`{{issue_text}}` `{{contract_json}}` `{{recipe_hints}}` `{{anchor_summary}}`）
要求 System 内明确：
- 你是审计官不是协作者；禁止帮助「通过审核」
- 无证据不得拒绝；有冲突证据必须列出
- 不得引用训练数据中的库「标准用法」作为唯一证据（Recipe hint 仅当输入提供时可用）
- temperature 语义：只输出 JSON，无 Markdown 围栏外的散文

## F. 反幻觉 / 反偏移条款（必须写入复审 Prompt）
用「违反则无效输出」的口吻写清：
- 禁止：无 span_text 的结论
- 禁止：span_text 无法在输入中定位
- 禁止：用「一般应该」「通常 API」替代 Issue
- 禁止：建议阅读 tests/ 或 patch
- 禁止：一次性只报「最严重一条」而隐藏其余
- 强制：先列 evidence_chain，后写 claim（或在 JSON 中 chain 不得为空）

## G. 用 3 个思想实验验收「优化后的复审 Prompt」
对每个场景，给出：
- 输入摘要（Issue 一句 + 契约行关键字段）
- **期望**复审输出的 findings（含证据链要点）
- 若用劣质复审 Prompt 会犯的错（幻觉/漏报/偏移）

场景：
1. cattrs 类：quote 说 required→value None，expect 却要求 partial 有值（false_fail）
2. adaptix 类：BC 合法但仍偏题（例如 expect 与 alias 无关）
3. 证据不足：模型「觉得」该测 CLI，但 Issue 未强调 —— 应 insufficient_evidence / warning，不得强行 reject

## H. Ablation 建议
说明去掉哪些 Prompt 条款会导致：漏报、幻觉上升、同谋；便于我们做开关实验。

# Output Format（严格按此结构）
1. **诊断（≤15 行）**：当前/典型弱复审 Prompt 的失败模式；证据链如何针对修复。
2. **Evidence Chain 规范终稿**（字段表 + 最低条数规则 + 子串自检规则）。
3. **Issue Taxonomy 表**（类型 | 定义 | 证据模板 | verdict 映射）。
4. **强制复审步骤**（逐步，可写进 System）。
5. **升级后 JSON Schema**（完整）。
6. **`CONTRACT_REVIEW_SEMANTICS_SYSTEM` 全文**。
7. **`CONTRACT_REVIEW_SEMANTICS_USER` 模板全文**。
8. **sanitize / 机器后处理建议**（例如：span 非子串 → 降级 finding；空 chain → 丢弃；与 BC 结果冲突时谁优先——必须 BC 优先）。
9. **三场景期望输出要点**（含证据链）。
10. **一周落地清单**（Prompt 合入、单测、ablation）。

# Quality Bar
- 禁止只写「要有证据」而不给 JSON 字段与最低条数。
- 禁止让复审重新成为自由散文考官。
- 禁止复审 Prompt 鼓励使用官方测试或模型内置「标准答案」。
- 每个问题类型都必须能指出：没有证据链时会如何幻觉。
- 交付的 System/User Prompt 必须可直接试用；不要只给提纲。

# Optional Addendum（用户随后粘贴则优先）
- 当前 `contract_review_semantics` Prompt 草稿
- §3.5.8 摘录
- 真实 Issue + 已过 BC 的 contract JSON（好/坏各一）
- v3.3.1 audit 中 false_fail / WRONG_LAYER 案例摘要
请用真实材料改 Prompt，并在场景 G 中替换为真实字段名。
```

---

## 使用建议（给人看的，不必贴进模型）

1. **第一轮**：不贴真实题，先产出 System/User + Evidence Chain Schema。  
2. **第二轮**：贴 cattrs / adaptix / aiomonitor 的 Issue+契约，要求「用你写的复审 Prompt 真审一遍」，检查是否每条 finding 都有可核验 span。  
3. **第三轮**：故意加入「模型常识正确但 Issue 未写」的陷阱，验证是否落到 `insufficient_evidence` 而非幻觉 reject。  
4. 产出满意后：把 System/User 落进 `app/spec_parser/`（或 `document/model1/prompts/contract_review_semantics_v1.md`），并把升级 JSON 回写 §3.5.8 输出契约；修订设计文档版本号。  
   **（已完成 2026-07-22 / α3）**：见 [`contract_review_prompts.py`](../../../app/spec_parser/contract_review_prompts.py) 与 [contract_review_semantics_v1.md](./contract_review_semantics_v1.md)。

## 与设计文档的对齐检查表

| 设计约束（§3.5.8） | 本元 Prompt 是否覆盖 |
|--------------------|----------------------|
| 不能放行 BC 未过 | ✅（复审输入假定已过；sanitize 强调 BC 优先） |
| 结构化 verdict | ✅ |
| 禁止开放「完美吗」 | ✅ 强制步骤 + Taxonomy |
| 不读官方测 | ✅ 硬约束 + 反幻觉条款 |
| 修槽只改 expect | ✅ fix 字段约束 |
| 证据防幻觉 | ✅ 本文件核心（evidence_chain） |
