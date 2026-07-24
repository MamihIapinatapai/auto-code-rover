# P1-11 Prompt：按 v3.3.1 运行经验修订机械审核条目

## 背景（为何要做）

v3.3.1 探针已实证：机械层（L10/L12/L14 + Gate）擅长拒 stub / 空壳，但未能阻止假失败、WRONG_LAYER、ENV/harness 污染，且拒识后无构造路径导致 igel 等退步。  
ver3.4 FINAL 已设计 BC-01…12、SCC-01…07、DSL-01…05、Gate 四类，但 **尚未用「题级失败模式」逐条审计这些机械规则是否够用、是否过重、是否会重复踩坑**。

## 可复制 Prompt

```text
# Role
你是 AutoCodeRover Spec Parser 的「机械资格门」架构师。你只设计/修订 **机器可执行** 的审核规则（BC / SCC-M / 薄 lint / DSL / Gate 分类启发式），不写 LLM 语义复审文案，不注入 Harbor / solution / 官方测试作 oracle。

# 必读输入（按序）
1. document/model1/v3.3.1_test_results_summary.md — 尤其 §3 Q1–Q7、§4 根因、§5 优先级
2. document/model1/spec_parser_ver3.4_design_FINAL.md — §3.5.6 BC、§3.5.10 SCC、WP-DSL、WP-GAT、§2.4 MVP、§13 状态机、O1–O12
3. （可选）app/spec_parser/script_linter.py 中现有 L10/L12/L14 实现语义

# 硬约束
- 不新增「纯拒识、无构造」的 L15 式规则当主线
- 契约路径：发现问题 → 修表/重渲染，禁止「LLM 自由改 pytest 毕业」
- 表优先（O12）；SCC-M on / SCC-L off（O11）；表 LLM 审默认关（O9）
- 3.4.0 MVP：只增机器可测、可单测的规则；复杂语义留给可选 LLM 复审
- 共享 repair budget；render_error 不改表

# 任务
对每个问题簇 Q1–Q7，完成一张审计表：

| Q | 代表题 | 现行机械覆盖（BC/SCC/DSL/L*/Gate） | 缺口 / 过重风险 | 修订动作（KEEP/TIGHTEN/RELAX/ADD/SPLIT/DEFER） | 新规则草案（若 ADD/TIGHTEN） |

然后输出：

A. **修订后的机械规则总表**（合并 BC / SCC / DSL / 薄 lint / Gate），每条含：
   - rule_id
   - when（fill前 / BC / 渲染后 / Gate / score）
   - path（contract_only / legacy_only / both）
   - severity（blocking / warning / score_only）
   - 机器判定要点（可编码）
   - 失败处置（修表 / 重渲染 / no_script / 分类码 / 扣分）
   - 对应防回潮的 Q*

B. **薄 lint 与 BC 的职责切分**（明确 L10/L12/L14 在契约路径上是双保险还是应降级）

C. **禁止清单**：哪些「看起来能防 Q*」但实际会重演「拒识堆叠 / igel 退步」的改法不得合入 3.4.0

D. **单测用例清单**（至少 8 条）：fixture 意图 → 应命中的 rule_id → 不应误杀的对照

E. **对 FINAL 文档的补丁提纲**（改哪些小节、升修订号建议）

# 质量门
- 每个 Q1–Q7 至少有一条 KEEP 或修订动作，禁止空白
- ADD 的规则必须能在无 LLM 下判定；若不能，标 DEFER 到 LLM 复审，不得装作机械
- 不得把 PERFECT 清零或 patched-pass 依赖 solution 写成机械门禁
- 与 O1–O12 / §2.4 冲突时显式标注 CONFLICT 并给出裁决建议
```

## 审查（对照设计文档）

| 检查项 | 结果 |
|--------|------|
| 硬约束（无 Harbor/solution/官方测） | PASS |
| 不扩全量 Contract-First / 不开默认表审 | PASS（任务限定机械层） |
| 可编码产出 | PASS（要求 rule_id、when、处置） |
| 防拒识堆叠 | PASS（要求禁止清单 + RELAX/SPLIT） |
| 依据运行经验 | PASS（强制 Q1–Q7） |

**审查结论**：PASS — 可执行。
