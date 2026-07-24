# Prompt：审查 Spec Parser ver3.3.1 设计（ScriptAnchor）

> 用途：交给 Agent / 人工评审员，对 `document/model1/spec_parser_ver3.3.1_design.md` 做**可落地性 + 质量提升有效性**审查。  
> 产出：结构化审查报告（可写入 `document/model1/spec_parser_ver3.3.1_design_review.md`）。

---

## Role

你是 AutoCodeRover Spec Parser 的技术评审负责人，专长：

1. LLM Agent 脚本生成管线（lint / Gate / 审视 / 证据链 / 决策链）
2. 静态分析与运行时契约锚定（AST / pyproject / inspect）对生成质量的真实贡献
3. 识别「看起来合理但抬不了 STRONG」的设计空洞与过设计

## Mission

审查 `document/model1/spec_parser_ver3.3.1_design.md`：判断在已落地的 **ver3.3（证据链+决策链）** 之上加入 **ScriptAnchor（Tier1 静态 + Tier2 inspect）**，是否**真正提高复现/验收脚本质量**；并给出**必须修改 / 建议微调 / 可保留**清单。

**本任务只写审查结论，不改业务代码、不重写整份设计文档。**

## Mandatory Reading

按顺序阅读，审查结论必须引用真实路径/现象：

1. `document/model1/spec_parser_ver3.3.1_design.md`（审查对象）
2. `document/model1/spec_parser_ver3.3_design.md`（基线：双链已覆盖什么）
3. `outputs/deepswe_spec_parser/deepswe-spec-parser-python-v3.2-probes/v3.2_probe_audit_synthesis.md`（D1–D6 真实失败模式）
4. 代码事实核对（至少扫一眼）：
   - `app/spec_parser/agent.py`（校准环时序；v3 默认关 repo_enrichment）
   - `app/spec_parser/pipeline.py`（`should_run_repo_enrichment`）
   - `app/spec_parser/entity_extraction.py` / `symbol_index.py` / `target_resolution.py`
   - `app/spec_parser/script_prompts_v3.py` / `script_review_prompts.py`
   - `app/spec_parser/coverage_heuristics.py` / `draft_picker.py`
5. 任选 1 个 OVER_SPEC / WRONG_LAYER 审计样例加深判断，例如：
   - `.../v3.2-probes/aiomonitor-task-snapshots-diff/issue_script_match_audit.md`
   - 或 adaptix / cattrs 的 `issue_script_match_audit.md`

## Review Rubric（必须逐项打分）

对下列维度给出：**Pass / Partial / Fail** + 1–3 句理由：

| ID | 维度 |
|----|------|
| R1 | **问题对齐**：是否对准 v3.2/3.3 后的主矛盾（PARTIAL: OVER_SPEC / WRONG_LAYER），而非重复造 3.3 已有轮子 |
| R2 | **因果有效性**：ScriptAnchor → 脚本质量提升的因果链是否成立（不只「有信息」） |
| R3 | **覆盖缺口**：对 WEAK_ASSERT / NARROW / Stub 顽固题帮助有多大；哪些质量问题**几乎无帮助** |
| R4 | **与 3.3 双链集成**：证据链/决策链接入是否清晰，会不会互相打架或只堆 JSON |
| R5 | **仓库复用真实性**：声称复用的模块是否真能支撑 Tier1；v3 默认关 enrich 时如何拿到 index |
| R6 | **时序正确性**：Tier1 生成前、Tier2 sandbox 后是否可行；与校准环/regen 的再注入是否说清 |
| R7 | **硬约束合规**：不注入官方测/solution；不把 sample_test 当 oracle；测试路径排除 |
| R8 | **成本与风险**：prompt 膨胀、定位错文件、误报签名、产出率下降是否有足够缓解 |
| R9 | **验收可证伪**：指标能否证明「质量提升」而非「多了个 json」；STRONG/OVER_SPEC 如何度量 |
| R10 | **分期可落地**：Phase D→G 是否可独立合入；P0 是否过大或过小 |

## Critical Questions（必须明确回答）

1. **能不能真正提高脚本质量？** 分场景：OVER_SPEC、WRONG_LAYER、WEAK_ASSERT、Stub、ENV。每项：高/中/低/无。
2. **最大收益来自 Tier1 还是 Tier2？** 若只能先做一层，做哪层？
3. **最大风险是什么？**（定位错误导致「带着错签名自信地写错脚本」是否比不锚定更糟）
4. **设计文档哪些地方必须改**才建议开工实现？
5. **哪些是微调即可**（不必阻塞实现）？
6. **哪些应砍掉或降级为后续版本**以免稀释 3.3 收益？

## Output Structure（严格按此写审查报告）

写入：`document/model1/spec_parser_ver3.3.1_design_review.md`

```markdown
# Spec Parser ver3.3.1 设计审查报告

## 0. 一句话裁决
（开工 / 有条件开工 / 回炉）+ 理由

## 1. 执行摘要（≤10 条 bullet）

## 2. 质量提升有效性评估
### 2.1 按失败模式（D1–D6）映射表
### 2.2 因果链验证（Anchor 信息如何变成更好的 AC）
### 2.3 预期指标变化（相对 3.3）

## 3. Rubric 打分表（R1–R10）

## 4. 必须修改（Blocking）
编号列表：问题 → 为何阻塞 → 建议改法（可粘贴进设计文档的段落级建议）

## 5. 建议微调（Non-blocking）
## 6. 可保留的优点
## 7. 实现优先级建议（若有条件开工）
## 8. 审查附录：与代码现状偏差
```

## Style

- 像设计评审纪要，不要科普文；少形容词，多「对哪类题、抬哪类指标」。
- 每个 Blocking 项必须可操作。
- 若设计已足够好，也要写清「保留理由」，不要为找茬而找茬。

## Do NOT

- 不要开始实现 3.3.1 代码
- 不要删除或重写整个 3.3.1 设计文档（审查报告可建议补丁段落）
- 不要建议注入官方测试来刷 STRONG
```

