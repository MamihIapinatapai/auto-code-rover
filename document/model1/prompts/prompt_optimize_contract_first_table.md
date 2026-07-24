# Prompt：细化与优化「切入点 α — Contract-First 行为契约表」

> **用途**：丢给架构/设计 LLM（或人工工作坊），产出可落地的 BehaviorContract 表格/Schema 设计，而不是空泛原则。  
> **关联**：[spec_parser_ver3.4_design.md](./spec_parser_ver3.4_design.md) §3.1 α、§4 WP-S1 / WP-CF  
> **使用方式**：整段复制为 User Message；可将附录中的「当前草稿 Schema」与 1～2 个真实 Issue 作为附加上下文粘贴在末尾。

---

## 可复制 Prompt 正文

```text
# Role
你是资深测试架构师 + 规格工程师，擅长把自然语言 Issue 编译成「可机器校验、可确定性渲染成 pytest」的行为契约（Behavior Contract）。你熟悉 AutoCodeRover Spec Parser 的目标：生成的复现/验收脚本必须能当金标用（与 Issue 同构），而不是只在 buggy 仓库上「能挂」。

# Context（必须内化）
我们要优化设计切入点 α：**Contract-First（契约优先）**。
- 旧路径：LLM 自由生成整份 test_feature.py → lint 拒 stub/弱断言 → 仅在 buggy 上校准。
- 新路径：先让模型（或抽取器）填写结构化「行为契约表」→ Schema 校验不合格则不出卷 → 再用确定性 Renderer/强约束模板生成 pytest。

历史失败模式（表格设计必须针对性消掉）：
1. EXISTENCE_ONLY：只测 hasattr / in dir，无行为。
2. STUB_AC：空壳 NotImplemented，无产品调用+期望。
3. WEAK_ASSERT：有调用但无具体期望值。
4. WRONG_LAYER：符号对了，调用编排错（如 adaptix 应 Retort(recipe=[name_mapping...])）。
5. FALSE_FAIL：断言方向与 Issue 相反，或 async/Web 脚手架自崩，导致正确实现也被杀。
6. NARROW/OVER_SPEC：漏 Must，或测私有 _internal / 臆造 API。
7. FEATURE 题符号不存在时易空手；需要从 Issue 明文 quote 抽出示例输入/输出。

硬约束：
- 不注入官方测试文件正文、Harbor 隐藏测、solution.patch 作为 oracle。
- 允许：Issue 原文、ScriptAnchor（符号/签名/入口）、Recipe Cards / README·docstring·examples 用法片段。
- 表格必须服务分层交卷：S1（最小可交卷）→ S2（Must 覆盖）→ S3（边角）；S1 是底线。

# Goal
请**详细设计并优化「行为契约表」**，使填表质量直接转化为脚本质量。输出必须达到「实现同学可按此写 JSON Schema / Pydantic / Renderer」的粒度。

重点回答：怎样设计字段、约束、枚举、校验规则与填表流程，才能最大化提升：
- S1 可达率（有具体期望的最小 oracle）
- 与 Issue 语义同构率（降假失败）
- 正确调用层命中率（降 WRONG_LAYER）
- 对 LLM 填表的可操作性（字段少而硬、少歧义、可自动拒填）

# Design Requirements（必须覆盖）

## A. 表结构（核心）
设计 `BehaviorContract`（文档级）与 `BehaviorContractItem`（每条 Must/AC 一行）的完整字段表：
对每个字段给出：
- 字段名（snake_case）
- 类型 / 枚举
- 是否必填（按 S1 / S2 / S3 分别标注）
- 填写来源（Issue quote / Anchor / Recipe / LLM 推断 / 禁止推断）
- 反例：坏填写长什么样
- 该字段如何防止上述失败模式之一

至少包含（可增删，但需论证）：
- must 锚定（must_id、issue_quote、优先级）
- layer（lib|cli|web|async|…）与允许的 call_graph / entrypoint
- setup / inputs（结构化，而非散文）
- expect（**必须 concrete**；禁止空、禁止 “should work”）
- fail_mode（buggy/未实现时预期失败形态）
- recipe_id / forbidden_patterns（用法锁）
- tier、confidence、degraded 原因
- 可选：oracle_kind（equality|raises|field_path|stdout_regex|http_status|…）

## B. expect 子系统（效果关键，请加重篇幅）
「具体期望」是整张表的胜负手。请设计：
1. expect 的正规形式（推荐 JSON 可判别结构，不要自由文本为主）。
2. 支持的 oracle_kind 清单 + 各自必填子字段。
3. 什么情况允许 `expect_confidence=low` 仍交 S1；什么情况必须拒填。
4. 如何用 issue_quote 绑定防止「期望写反」（false_fail）。
5. FEATURE（API 尚不存在）与 BUG_FIX 在 expect 上的差异策略。
6. 嵌套对象 / 流式 / CLI stdout / HTTP JSON 等难测形态的 expect 模板。

## C. 校验器（机器可执行）
给出 `validate_contract(contract) -> list[Violation]` 的规则清单：
- blocking（不能渲染脚本）vs warning
- 每条规则对应消除哪种历史失败模式
- 与现有 L10/L12/L14 的关系：哪些前置到契约层，让 lint 变薄

## D. 填表工作流（谁填什么）
设计 2～3 步流水，而不是「一次让 LLM 填完整张表」：
例：Must 抽取 → 层/Recipe 锁定 → expect 槽填充 → 自动校验 → 修槽。
说明每步输入输出、允许的上下文、失败重试策略（禁止空想三轮）。

## E. 渲染契约（表 → pytest）
规定 Renderer 的确定性规则：
- 哪些字段一对一映射到代码结构
- LLM 是否还允许改代码（建议：默认不允许改骨架，只允许改槽位数据）
- S1 最小脚本长什么样（给 1 个伪代码模板）

## F. 最小字段集 vs 完整字段集
给出：
- **MVP 字段集**（只服务 S1，3.4 先落地）
- **完整字段集**（S2/S3 / Contract-First 全链路）
并论证：为什么 MVP 这些字段对提升效果「足够且必要」（删掉哪个会立刻回到旧失败）。

## G. 用 3 类题做思想实验（各给填表示例）
对下列类型各构造 1 条「合格 S1 表行」+ 1 条「应被校验拒绝的坏表行」：
1. 库 API 编排题（类 adaptix：需要 recipe/Retort）
2. FEATURE 新行为题（类 dateutil/psd：符号可能不存在，靠 Issue 示例）
3. async/Web 题（类 aiomonitor：脚手架易假失败）

不要写空泛描述，要写出接近真实 JSON 的字段值。

# Output Format（严格按此结构输出）
1. **设计判决（≤10 行）**：这张表靠什么机制提升效果；最大风险是什么。
2. **MVP Schema**：字段表 + JSON Schema 或 Pydantic 风格定义。
3. **完整 Schema**：增量字段说明。
4. **expect 正规形式与 oracle_kind 目录**。
5. **校验规则表**（rule_id | 条件 | blocking? | 消哪种失败）。
6. **填表流水时序图（mermaid 或步骤列表）**。
7. **Renderer 映射表 + S1 伪代码模板**。
8. **三类题的好/坏填表示例（JSON）**。
9. **开放问题与 A/B 实验建议**（哪些字段需要探针验证再定）。
10. **给实现的一周落地清单**（只列 MVP）。

# Quality Bar
- 禁止只复述「要具体、要结构化」而不给字段与校验。
- 禁止引入违反硬约束的方案（读官方测试当 oracle）。
- 字段能少则少：每个字段必须能指出「删了会回到哪种失败」。
- 优先可机器判定，少依赖二次 LLM 裁判。
- 若某能力现有技术栈做不到，明确标 **降级方案（Workaround）**，不要装完美。

# Optional Addendum（若用户随后粘贴则优先使用）
- 当前草稿 BehaviorContractItem
- 1～2 个真实 Issue 原文 + ScriptAnchor 摘要
- v3.3.1 某题 audit 结论
请用这些真实材料改表，而不是只玩抽象例子。
```

---

## 使用建议（给人看的，不必贴进模型）

1. **第一轮**：只跑正文，要 MVP Schema + 校验规则。  
2. **第二轮**：把 `adaptix` / `dateutil` / `aiomonitor` 的 Issue 片段 + audit 结论贴进 Addendum，逼模型改字段。  
3. **第三轮**：要求输出「删字段消融表」——逐个去掉字段预测失败率变化，防表格过度设计。  
4. 产出满意后，把「MVP Schema + 校验规则」回写进 `spec_parser_ver3.4_design.md` 的 WP-S1 / WP-CF，并标 `Status: Spec`。  
   **（已完成 2026-07-22）**：见设计文档 **§3.5** 与修订记录 `3.4-plan-draft.α`。后续迭代请直接改 §3.5，避免双源。
