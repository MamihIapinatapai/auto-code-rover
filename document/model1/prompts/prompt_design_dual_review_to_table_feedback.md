# Prompt：专门化设计「表格质量审视 LLM」与「脚本质量审视 LLM」Prompt  
# （并统一提炼 → 回写表格生成 LLM 的错误信息）

> **用途**：丢给架构/Prompt 工程师 LLM，**同时**设计并区分两套审视 Prompt，使其按各自定位查错，并产出**可直接喂给表格生成 LLM**的结构化反馈（而非改脚本散文）。  
> **关联**：  
> - [spec_parser_ver3.4_design.md](../spec_parser_ver3.4_design.md) **§3.5.7–3.5.10**（填表流水 / 表语义复审 / Renderer / 脚本一致性→回写）  
> - 已有表复审落地：[contract_review_semantics_v1.md](./contract_review_semantics_v1.md) · `app/spec_parser/contract_review_prompts.py`  
> - 表结构元 Prompt：[prompt_optimize_contract_first_table.md](./prompt_optimize_contract_first_table.md)  
> - 表复审证据链元 Prompt：[prompt_optimize_contract_llm_review.md](./prompt_optimize_contract_llm_review.md)  
> **使用方式**：整段复制「可复制 Prompt 正文」；末尾可粘贴：当前两套 Prompt 草稿、Issue、契约 JSON、渲染脚本片段。  
> **产出目标**：  
> 1. `TABLE_REVIEW_*`（表格质量审视）System/User  
> 2. `SCRIPT_REVIEW_*`（脚本质量审视，契约路径 = SCC-L 语义层）System/User  
> 3. 统一的 **`TableGenFeedback`**（回写表格生成 LLM 的错误信息包）Schema + 映射规则  
> 4. 二者分工表、禁止重叠/越权条款、抗幻觉证据链要求

---

## 可复制 Prompt 正文

```text
# Role
你是资深规格审计官 + Prompt 工程师。你的任务不是直接审某一张表或某一份脚本，而是：

**专门化设计两套审视 LLM 的 Prompt**，并设计它们如何把发现问题**提炼成表格生成 LLM 可消费的迭代信号**。

两套审视必须：
1. 严格按自身作用定位查错（不串岗、不重复机械 BC/SCC-M 已覆盖的形状检查为主业）；
2. 完整列出问题点，每点带可核验证据链；
3. 每个问题最终都能映射为对 BehaviorContract 槽位的修改建议（或明确「纯渲染 bug、不改表」）；
4. 产出统一格式的反馈包，供表格生成 LLM（Step3 expect 填充 / 修槽）直接使用。

你熟悉 AutoCodeRover Spec Parser v3.4 Contract-First：
填表LLM → BC机械 →【表审视LLM】→ Renderer → 薄lint → SCC-M机械 →【脚本审视LLM可选】→ contract_patch → 回填表LLM修槽 → 重渲染。

硬约束：
- 不读官方测试 / Harbor / solution.patch
- 禁止以「重写整份 pytest」作为主修复建议
- 脚本与表冲突时默认表优先重渲染；仅当证据证明表语义错误时才 patch 表
- 机械层（BC、SCC-M）资格/对齐门优先；LLM 不得放行机械未过的产物

###############################################################################
# Part 0 — 作用定位（必须先写清，再写 Prompt）
###############################################################################

先用表格固定分工（你输出时也必须包含此表的终稿版）：

| 维度 | 表格质量审视 LLM（Table Review） | 脚本质量审视 LLM（Script Review / SCC-L） |
|------|----------------------------------|------------------------------------------|
| 主问题 | Issue ↔ BehaviorContract 语义是否同构 | 已渲染脚本 ↔ Contract 是否忠实；兼捕表审漏网的语义残留 |
| 输入 | Issue + Contract（BC已过）+ 可选 Recipe/Anchor | Issue + Contract + Script（建议按 must 切段）+ SCC-M findings |
| 不审什么 | 空 expect、hasattr-only、缺 quote 等 BC 形状问题（除非语义变体） | L10/L12/L14 空壳形状；SCC-M 已报的字面量缺失（可引用但不要重复劳动） |
| 成功标准 | 找出 false_fail / off_must / weak_degraded / quote_drift… | 找出 invented_literal / assert-contract mismatch 语义型 / 渲染忠实度之外的偏题 |
| 修复落点 | 只建议改 Contract 槽位 | 优先 contract_patch；render_error 则标不改表 |
| 对表格生成LLM | 直接提供修表指令 | 提供修表指令或「勿改表、属渲染」 |

若两套 Prompt 出现「都在用常识教人怎么写测试」或「都建议改脚本」，视为设计失败。

###############################################################################
# Part 1 — 设计目标
###############################################################################

请设计并优化：

A. **TABLE_REVIEW_SYSTEM / TABLE_REVIEW_USER**
   - 定位：表格质量审视（对齐 §3.5.8）
   - 能力：从「Issue↔表」角度找全语义错误与修改点
   - 输出：含证据链的 findings + 可映射的 TableGenFeedback 片段

B. **SCRIPT_REVIEW_SYSTEM / SCRIPT_REVIEW_USER**
   - 定位：脚本质量审视（契约路径，对齐 §3.5.10 SCC-L；不是旧的自由改脚本 reviewer）
   - 能力：从「脚本↔表（+Issue）」角度找全错误与修改点
   - 输出：contract_patch 风格 findings + 可映射的 TableGenFeedback 片段
   - 明确禁止：输出「请这样改 pytest 代码」作为唯一 fix

C. **统一 TableGenFeedback Schema**（回写表格生成 LLM 的唯一推荐接口）
   - 两套审视的 findings 都必须能 `reduce` 成此结构
   - 表格生成 LLM 的修槽 User 消息应主要吃此结构，而不是吃两套不同方言

###############################################################################
# Part 2 — TableGenFeedback（回写表格生成 LLM）设计要求 —— 核心
###############################################################################

设计一个机器可解析、对填表模型友好的反馈包，例如：

```json
{
  "feedback_id": "TF-...",
  "source": "table_review | script_review | merged",
  "blocking": true,
  "summary_for_filler": "<=200 chars, imperative, Chinese or English consistent with filler prompts",
  "items": [
    {
      "must_id": "M1-...",
      "error_type": "false_fail | off_must | weak_degraded | quote_drift | recipe_misaligned | script_contract_mismatch | invented_expect | insufficient_evidence | ...",
      "severity": "blocking | warning",
      "what_is_wrong": "<=200 chars",
      "evidence_digest": [
        {"source": "issue|contract|script", "span": "<=80 chars"}
      ],
      "allowed_edits": ["expect", "fail_mode", "expect_confidence"],
      "forbidden_edits": ["call_graph", "recipe_id", "layer"],
      "suggested_patch": {
        "path": "items[must_id=M1].expect.value",
        "next_value_hint": "null | <literal from issue span only>",
        "oracle_kind_hint": "field_path|equality|raises|keep",
        "rationale": "<=150 chars"
      },
      "do_not": ["rewrite pytest", "invent numbers not in Issue", "change call_graph freely"]
    }
  ],
  "filler_instructions": [
    "Only edit allowed fields listed per item",
    "Re-emit full expect envelope for patched must_ids",
    "If insufficient_evidence only: keep prior expect unless quote clearly supports upgrade"
  ]
}
```

你必须规定：
1. **如何从 Table Review 原始 JSON → TableGenFeedback**（字段映射表）
2. **如何从 Script Review / contract_patch → TableGenFeedback**（含 render_error 时 items 为空、只带 summary「勿改表」）
3. **合并策略**：表审 + 脚本审同时存在时如何 merge（同 must_id 去重、severity 取高、证据合并、冲突时以 false_fail 类优先）
4. **喂给表格生成 LLM 的 User 模板**（`TABLE_FILL_REPAIR_USER`）：只含 Issue 相关 quote、当前 item JSON、TableGenFeedback；禁止附整份混乱脚本除非 script_review 且必须引用的短 span
5. **反同谋**：repair 提示不得写「为了通过审核请……」；应写「根据下列证据修正契约……」

###############################################################################
# Part 3 — 表格质量审视 Prompt 专门化要求
###############################################################################

设计 TABLE_REVIEW_* 时强制：

## 3.1 查找视角（只允许这些问题入口）
- expect 与 issue_quote / Must **方向是否一致**
- 是否打在**主 Must**
- degraded/low 是否可升格（quote 已有字面量）
- quote 是否断章（quote_drift）
- recipe_hint 存在时是否语义偏题（不是重复 BC-08 字符串禁式，而是意图）
- 多 item 互相矛盾

## 3.2 工作流程（写进 System，逐步）
Must 候选抽取（带 span）→ 逐行对照 quote/expect/call_graph → taxonomy 逐项检查 → 完整列 findings → 映射 TableGenFeedback.items → self_check 证据子串

## 3.3 证据链
与既有规范一致：每条非 ok finding 强制 evidence_chain；span 必须为输入子串；derived≤1。
可复用/改进现有 `CONTRACT_REVIEW_SEMANTICS_*`，但必须新增「**导出 TableGenFeedback**」段落或后处理映射说明。

## 3.4 明确越权禁止
- 不要审脚本（此时可能尚无脚本）
- 不要建议改 pytest
- 不要用训练数据「标准库用法」当唯一证据

###############################################################################
# Part 4 — 脚本质量审视 Prompt 专门化要求
###############################################################################

设计 SCRIPT_REVIEW_* 时强制：

## 4.1 查找视角（只允许这些入口）
- 脚本断言/调用是否与 contract 对应字段**语义一致**（不仅字符串相等）
- 脚本是否出现 **contract 未授权的期望字面量**（invented）
- 在 SCC-M 已通过的前提下，是否仍存在「表看起来合法但脚本暴露的偏 Must / 假失败」
- 区分：`render_error`（模板没映上） vs `contract_error`（表就写错，需回写）

## 4.2 工作流程（写进 System）
按 must_id 切分脚本 → 对齐 call_graph/expect/oracle_kind → 对照 Issue quote → 列出 findings（完整）→ 标注 patch.action（update_expect vs noop_rerender/mark_render_bug）→ 导出 TableGenFeedback（仅 contract_error 类进入 items）

## 4.3 证据链硬约束
每条 finding 至少包含：
- E1: script_span
- E2: contract_field
- （若主张表错）E3: issue_span
缺 issue_span 时不得输出 false_fail 类改表建议（只能 insufficient_evidence 或 render_error）

## 4.4 明确越权禁止
- 禁止唯一 fix = 重写测试函数
- 禁止在 SCC-M blocking 未清时假装「脚本语义通过」
- 禁止把脚手架风格偏好（命名、注释）当成 blocking 语义问题
- 禁止建议读取 tests/

###############################################################################
# Part 5 — 专门化对比与消歧（必须输出）
###############################################################################

输出一张「易混淆场景」表：同一现象下，Table Review vs Script Review 各自该报什么、不该报什么，以及最终 TableGenFeedback 长什么样。

至少覆盖场景：
1. expect 与 Issue 反向（表错，尚未渲染或已渲染）
2. 表对，模板漏了 expect 字面量（纯渲染）
3. 表对，脚本却多了发明字面量（脚本侧）
4. 证据不足「感觉该测 CLI」（双方都不得硬 reject）
5. recipe 合法但偏题（表审主责；脚本审可辅助确认脚本也偏了）

###############################################################################
# Part 6 — 交付物格式（严格按序）
###############################################################################

1. **定位终稿表**（Part 0 升级版）+ 一句话红线
2. **TableGenFeedback Schema 终稿** + 字段说明 + 合并规则
3. **映射表**：TableReviewJSON → Feedback；ScriptReviewJSON → Feedback
4. **`TABLE_FILL_REPAIR_USER` 模板全文**（给表格生成 LLM 修槽用）
5. **`TABLE_REVIEW_SYSTEM` 全文** + **`TABLE_REVIEW_USER` 模板**
6. **`SCRIPT_REVIEW_SYSTEM` 全文** + **`SCRIPT_REVIEW_USER` 模板**
7. **sanitize / 后处理建议**（两套 + Feedback 合并器）
8. **五场景期望 Feedback 要点**（含证据 digest）
9. **与现有资产关系**：如何演进 `contract_review_prompts.py`；SCC-L 是否新建 `script_contract_align_prompts.py`
10. **一周落地清单** + ablation（关表审 / 关脚本审 / 只 Feedback 不修槽 的对照）

# Quality Bar
- 禁止两套 Prompt 口吻雷同、职责不清
- 禁止只有「要反馈给填表模型」而无 TableGenFeedback 字段
- 禁止脚本审视 Prompt 教人改 pytest 作为主路径
- 禁止无证据链的改表建议
- 交付的 System/User 必须可直接试用；不要只给提纲
- 若某能力做不到，标明 Workaround（例如脚本审视先只做 contract_error 分类，字面量对齐交给 SCC-M）

# Optional Addendum（用户随后粘贴则优先）
- 当前 CONTRACT_REVIEW_SEMANTICS_* 全文
- §3.5.8 / §3.5.10 摘录
- 真实 Issue + contract JSON + 渲染脚本（好/坏）
- 旧 script_review_prompts.py 片段（指出哪些必须废弃于契约路径）
请基于真实材料改写，并在场景中使用真实字段名（must_id、oracle_kind、expect.value 等）。
```

---

## 使用建议（给人看）

1. **第一轮**：不贴真实题，先产出两套 System/User + `TableGenFeedback` Schema + 修槽 User 模板。  
2. **第二轮**：贴 cattrs（表错）+ 故意残缺渲染（纯 render_error）+ 发明字面量脚本，检查两套审视是否**串岗**。  
3. **第三轮**：只把 `TableGenFeedback` 喂给表格生成/修槽 Prompt，看修槽是否只动 `allowed_edits`。  
4. 落地建议：  
   - 表审：演进 [`contract_review_prompts.py`](../../../app/spec_parser/contract_review_prompts.py) 或增加 `to_table_gen_feedback()`  
   - 脚本审：新建 `script_contract_align_prompts.py`  
   - 合并器：`table_gen_feedback.py`  
   - 回写设计文档 §3.5.8 / §3.5.10「Feedback 回填表」小节  

## 与现有设计的对齐检查

| 设计约束 | 本元 Prompt |
|----------|-------------|
| 表审 = Issue↔表 | ✅ Part 3 |
| 脚本审 = 脚本↔表，回写契约 | ✅ Part 4 |
| 禁止润色脚本毕业 | ✅ 全文红线 |
| 证据链防幻觉 | ✅ Part 3.3 / 4.3 |
| 修槽只改 expect 等 | ✅ TableGenFeedback.allowed_edits |
| 共用迭代目标：优化表格 | ✅ Part 2 核心 |
