# BehaviorContract LLM 语义复审 Prompt — v1（证据链强制）

> **Status**: Spec / 可合入  
> **来源元 Prompt**：[prompt_optimize_contract_llm_review.md](./prompt_optimize_contract_llm_review.md)  
> **设计对齐**：[spec_parser_ver3.4_design.md](../spec_parser_ver3.4_design.md) §3.5.8  
> **代码落点**：[`app/spec_parser/contract_review_prompts.py`](../../../app/spec_parser/contract_review_prompts.py)

---

## 1. 诊断（弱复审 → 本版如何修）

| 弱复审失败模式 | 本版对策 |
|----------------|----------|
| 「整体不错」无列点 | 强制 `item_findings` 完整列表 + `findings_complete` 自检 |
| 指控无原文 | 每条非 ok 必须 `evidence_chain`，`span_text` 须为输入子串 |
| 用常识当证据 | 禁止训练数据「标准用法」；Recipe/Anchor 仅当输入非空 |
| 只报最严重一条 | 明文禁止合并；taxonomy 逐项跑 |
| 同谋放行 | System：审计官非协作者；不得协助通过审核 |
| 重复机械 BC | 明确「不审空 expect/hasattr…」 |

---

## 2. Evidence Chain 规范终稿

| 字段 | 要求 |
|------|------|
| `step_id` | `E1`, `E2`, … |
| `claim` | 单步断言 |
| `source_type` | `issue_span` \| `contract_field` \| `recipe_hint` \| `anchor_entry` \| `derived` |
| `source_ref` | 可定位路径（Issue 偏移 / `items[i].expect.value` / …） |
| `span_text` | ≤120；**必须是输入原文子串** |
| `support` | `supports` \| `contradicts` \| `neutral` |

**最低条数**：false_fail / off_must / weak_degraded / recipe_misaligned / quote_drift / multi_item_inconsistency ≥ **2**；insufficient_evidence ≥ **1**；ok 可为 0。  

**derived**：全链最多 1 步，且不得单独成链。  

**闭合**：最后一步须说明「由上述 span 如何推出问题」。  

**机器 sanitize**：span 非子串 → 丢弃该 step / 整条降为 `insufficient_evidence`；空 chain 的非 ok → 丢弃或降级；**不得**当 `pass`。

---

## 3. Issue Taxonomy

| issue | 定义 | 证据模板（最少） | verdict 倾向 |
|-------|------|------------------|--------------|
| `false_fail` | expect 与 quote/Must **反向或冲突** | E1 issue/quote 方向；E2 expect 字段 contradict | `reject_false_fail` |
| `off_must` | 未打主 Must | E1 主 Must span；E2 call_graph/expect 偏题 | `reject_off_must` 或 warning（边角） |
| `weak_degraded` | low/raises 但 quote 已有可升格字面量 | E1 quote 字面量；E2 当前 oracle_kind/confidence | `revise_expect` |
| `recipe_misaligned` | BC 合法但相对 recipe_hint 偏集成意图 | E1 recipe_hint；E2 call_graph/expect | `reject_off_must` / `revise_expect` |
| `quote_drift` | quote 断章导致绑错期望 | E1 更长 Issue 上下文；E2 过短 quote | `revise_expect` |
| `multi_item_inconsistency` | 行间矛盾 | E1 itemA 字段；E2 itemB 字段 | `revise_expect` |
| `insufficient_evidence` | 怀疑但不够 span | ≥1 步说明缺什么 | **仅 warning**，禁止伪装 reject |
| `ok` | 无语义问题 | 可空链 | — |

**反例（应 insufficient_evidence）**：仅凭「这类库一般测 CLI」而 Issue 未写 CLI —— 不得 `reject_off_must`。

---

## 4. 强制复审步骤

见代码内 `CONTRACT_REVIEW_SEMANTICS_SYSTEM` 的 Mandatory workflow §1–7。

**总 verdict 优先级**：`reject_false_fail` > `reject_off_must` > `revise_expect` > `warning` > `pass`。

---

## 5. 升级 JSON Schema

见 `CONTRACT_REVIEW_SEMANTICS_SYSTEM` 内嵌 schema；相对 §3.5.8 初稿新增：

- `finding_id` / `severity` / `claim` / `confidence`
- **`evidence_chain[]`（强制）**
- `must_coverage_notes[]`
- `self_checks.{all_spans_substring_verified,no_external_oracle_used,findings_complete}`

---

## 6–7. System / User 全文

以代码为准（单一真相源）：

- `CONTRACT_REVIEW_SEMANTICS_SYSTEM`
- `CONTRACT_REVIEW_SEMANTICS_USER`
- 填充函数：`format_contract_review_user(...)`

下面为只读副本（若与 `.py` 冲突，**以 `.py` 为准**）。

### SYSTEM（摘要指针）

完整字符串见 [`contract_review_prompts.py`](../../../app/spec_parser/contract_review_prompts.py) 中 `CONTRACT_REVIEW_SEMANTICS_SYSTEM`。

### USER 模板

```text
Audit the BehaviorContract below for SEMANTIC gold-standard risks.
...
## Issue text
{issue_text}
## BehaviorContract JSON (BC-passed)
{contract_json}
## Recipe hints ...
{recipe_hints}
## Anchor summary ...
{anchor_summary}
## High-risk trigger reasons ...
{trigger_reasons}
```

---

## 8. sanitize / 后处理建议（实现 `contract_llm_review.py`）

| 规则 | 动作 |
|------|------|
| JSON 解析失败 | `verdict=revise_expect`, `llm_review_parse_error=true`，不得 pass |
| BC 未过仍调用 | **禁止调用**；调用则算实现 bug |
| finding 非 ok 且 chain 空 / 低于 MIN | 降级 `insufficient_evidence` 或丢弃；重算 verdict |
| `span_text` 不在 issue+contract+hints+anchor 拼接文本中（空白归一化后） | 剔除 step；不足则降级 finding |
| `self_checks.all_spans_substring_verified=false` | 不得维持 reject_*；降为 warning 或 revise_expect |
| 存在 `reject_false_fail` finding 但 evidence <2 | 降为 `insufficient_evidence` |
| 总 verdict 与 findings 不一致 | **以 findings 重算为准** |
| 与机械 BC 冲突 | **BC 优先**（本层不应见到 BC fail） |

---

## 9. 三场景期望输出要点

### ① cattrs 类 false_fail

- Issue/quote：`required missing → value should be None`  
- expect：`field_path=value, value={...}` 或非 null  
- 期望 finding：`false_fail`；E1=`issue_span` 含 None；E2=`contract_field` expect.value contradict  
- 劣质 Prompt 易错：只说「嵌套测法不对」无 span；或发明官方测期望

### ② adaptix 类 off_must / recipe_misaligned

- recipe_hint：`Retort(recipe=[name_mapping`  
- expect 与 alias 无关（例如只 assert Retort 可构造）  
- 期望：`off_must` 或 `recipe_misaligned`；E1 recipe/Issue alias；E2 expect/call_graph  
- 劣质 Prompt 易错：因 BC 已过就 `pass`；或用训练记忆报「应这样写」无输入 hint

### ③ 证据不足（不得强行 reject）

- 模型「觉得」该测 CLI，Issue 未强调  
- 期望：`insufficient_evidence` 或 `must_coverage_notes.uncertain` + 总 `warning`/`pass`  
- 劣质 Prompt 易错：直接 `reject_off_must`

---

## 10. 一周落地清单

1. ✅ Prompt 常量落入 `app/spec_parser/contract_review_prompts.py`  
2. ✅ 本文档 + 回写设计 §3.5.8 输出契约  
3. ⬜ `contract_llm_review.py`：调用 + sanitize（子串核验 + MIN_EVIDENCE）  
4. ⬜ 单测 V5：非法 verdict、空 chain、BC fail 不调用  
5. ⬜ 探针 ablation：`enable=False` vs `high_risk_only`  

---

## Ablation（去掉哪条会变差）

| 去掉条款 | 风险 |
|----------|------|
| evidence_chain 强制 | 幻觉指控上升 |
| 「完整列点」 | 漏报次严重但致命 false_fail |
| 「禁止标准用法记忆」 | 偏移 / 与 Issue 无关的「正确用法」 |
| 「审计官非协作者」 | 同谋假 pass |
| insufficient_evidence 类型 | 证据不够时硬 reject |
