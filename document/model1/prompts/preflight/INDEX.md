# ver3.4 实现前设计收口 — Prompt 索引与审查日志

> 对应「实现前建议优先补的设计」P0①–⑤、P1⑥–⑩。  
> 每点流程：**编写补齐 Prompt → 对照设计文档审查 → 执行产出**。  
> **实现唯一设计**：[spec_parser_ver3.4_design_FINAL.md](../spec_parser_ver3.4_design_FINAL.md)  
> 执行结果汇总（溯源）：[spec_parser_ver3.4_preflight_closure.md](../spec_parser_ver3.4_preflight_closure.md)  
> 历史计划稿：[spec_parser_ver3.4_design.md](../spec_parser_ver3.4_design.md)

| ID | 主题 | Prompt 文件 | 审查 | 执行入档 |
|----|------|-------------|------|----------|
| P0-1 | 3.4.0 MVP 边界冻结 | [P0_01_mvp_boundary.md](./P0_01_mvp_boundary.md) | PASS | FINAL §2.4 / closure §1 |
| P0-2 | Agent 编排状态机 | [P0_02_agent_state_machine.md](./P0_02_agent_state_machine.md) | PASS | FINAL §13.2 |
| P0-3 | TableGenFeedback + apply API | [P0_03_feedback_apply_api.md](./P0_03_feedback_apply_api.md) | PASS | FINAL §13.3 |
| P0-4 | Renderer 模板表 | [P0_04_renderer_templates.md](./P0_04_renderer_templates.md) | PASS | FINAL §13.4 |
| P0-5 | 旧 script_reviewer 交接 | [P0_05_legacy_reviewer_handoff.md](./P0_05_legacy_reviewer_handoff.md) | PASS | FINAL §13.5 |
| P1-6 | O1–O12 拍板 | [P1_06_open_questions_decisions.md](./P1_06_open_questions_decisions.md) | PASS | FINAL §9.2 |
| P1-7 | Recipe Cards 最小集 | [P1_07_recipe_cards.md](./P1_07_recipe_cards.md) | PASS | FINAL WP-RCP |
| P1-8 | Dual-State Lite 规则 | [P1_08_dual_state_lite.md](./P1_08_dual_state_lite.md) | PASS | FINAL WP-DSL |
| P1-9 | Gate 三分类决策表 | [P1_09_gate_triage.md](./P1_09_gate_triage.md) | PASS | FINAL WP-GAT |
| P1-10 | draft_score_v34 冻结 | [P1_10_draft_score_v34.md](./P1_10_draft_score_v34.md) | PASS | FINAL WP-SCR |
| P1-11 | 机械规则按运行经验修订 | [P1_11_mechanical_rules_from_runtime.md](./P1_11_mechanical_rules_from_runtime.md) | PASS | FINAL §14 · [mech_runtime](../spec_parser_ver3.4_preflight_mech_runtime.md) |

## 统一审查清单（每份 Prompt 必须满足）

对照 `spec_parser_ver3.4_design_FINAL.md`（历史审查对照过 `design.md`）：

- [ ] 不违反硬约束（无 Harbor/solution/官方测作 oracle）
- [ ] 不扩大超出 3.4.0 MVP（全量 Contract-First / UsageRecipe 挖掘标为非本版）
- [ ] 与 §3.5 BC / §3.5.8 表审 / §3.5.10 SCC / 修表 Prompt 分离一致
- [ ] 产出可编码（字段名、枚举、失败转移明确）
- [ ] 与已 CONFIRMED 的 O* / C-O* 不无故冲突；若冲突需显式标注「变更建议」并升 FINAL 修订号
