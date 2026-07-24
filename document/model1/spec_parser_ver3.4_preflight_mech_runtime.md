# Spec Parser ver3.4.0 — 机械审核条目运行经验修订（P1-11 执行产出）

> **Prompt**：[prompts/preflight/P1_11_mechanical_rules_from_runtime.md](./prompts/preflight/P1_11_mechanical_rules_from_runtime.md)  
> **审查**：PASS（见 prompt 文件）  
> **执行日期**：2026-07-22  
> **效力**：FROZEN 候选 — 已建议并入 [spec_parser_ver3.4_design_FINAL.md](./spec_parser_ver3.4_design_FINAL.md) §3.5.6 / §3.5.10 / §14  
> **依据**：`v3.3.1_test_results_summary.md` Q1–Q7 + FINAL 现行 BC/SCC/DSL/Gate + `script_linter.py` L10/L12/L14

---

## 0. 总裁决

**需要修订，但是「定向补洞 + 防拒识回潮」，不是推倒重来。**

| 判断 | 说明 |
|------|------|
| 已覆盖较好 | Q1 的「空壳形状」→ BC-04/05；Q3 的配方禁式 → BC-08 + Recipe；Q2 的 async/web → DSL-01/03；Q4 → Gate 四类；Q7 → ART |
| 仍会重演旧坑 | ① 契约路径上若仍用 **legacy 强度的 L10/L12 blocking**，会再次「拒完就死」；② BC-09 关键词表过粗，**挡不住 cattrs 类 nested required 假失败**；③ 渲染后缺 **recipe 文本合规 / 私有导入** 的 SCC；④ **非 stub 弱断言题**（httpx-streaming）因 O8 不走契约，机械层几乎只靠旧 L10 — 易回到「拒或放过」二元 |
| 明确不做 | 不加 L15「语义同构」；不把 patched-pass/solution 写成机械门；不默认打开表 LLM / SCC-L |

---

## 1. Q1–Q7 审计表

| Q | 代表题 | 现行机械覆盖 | 缺口 / 过重风险 | 修订动作 | 新规则草案 |
|---|--------|--------------|-----------------|----------|------------|
| **Q1** 无脚本 | gql L10；igel/dateutil/psd L12 | L10/L12 blocking；stub→契约路径（O8）；BC-04/05/11 | **过重**：契约渲染成功后若薄 lint 仍按 legacy L10/L12 **整卷 blocking→no_script**，重演 igel 退步。**缺口**：契约路径触发条件与「L10 命中但已有部分行为 AC」边界不清 | **SPLIT** L10/L12 为 `legacy_blocking` vs `contract_thin`；**KEEP** stub→S_FILL | **L10c / L12c**：契约路径上 existence/stub 视为 **render/contract bug → S_REPAIR 或重渲染**，不得直接记「自由 gen 失败轮」；仅 budget=0 才 no_script |
| **Q2** 假失败 | cattrs nested；aiomonitor loop/Web | BC-09；DSL-01/02/03；BC-10 warning | BC-09「None vs required」关键词 **太弱**：Issue 写「required 无默认 → value=None」而 expect 要 partial dict 时，简单词表可能漏检。DSL-01 已覆盖 loop；DSL-03 覆盖臆造 Handler | **TIGHTEN** BC-09；**KEEP** DSL-01/03；**ADD** BC-09b | **BC-09b**：若 `issue_quote`（归一化）同时含 `required`/`must` 与 `none`/`null`，且 `oracle_kind∈{equality,field_path}` 的 `expect.value` 为 **非 null 的 mapping/list** → blocking（cattrs 模式）。复杂句式 **DEFER** 表 LLM |
| **Q3** WRONG_LAYER | adaptix；mashumaro；aiomonitor Web | BC-08；Recipe×4；SCC-02；DSL-03 | BC-08 查 call_graph/forbidden；**渲染后脚本文本**仍可能写出 Provider 直调而表表面合规。mashumaro metadata 同理 | **ADD** SCC-08；**KEEP** BC-08；**TIGHTEN** BC-07 S1 | **SCC-08**：若 `recipe_id` 非空，AC 段源码须匹配 card `required_patterns` 且不得匹配 `forbidden_patterns`（字符串级）。**BC-07**：web/cli S1 **blocking** 缺 entrypoint（对齐 O6，不再仅 warning） |
| **Q4** ENV/harness | sqlite；sqlfmt；narwhals；bandit | Gate 四类；bandit JSON 适配 | Gate 已定；机械缺口主要在 **分类启发式可编码性** 与「缺包名单」 | **KEEP** Gate；**ADD** GAT-M1；**TIGHTEN** 配置默认列表 | **GAT-M1**：`ImportError` 模块名 ∈ `env_transitive_modules` → `missing_third_party`；名与 `feature_module_name_hints`/Issue 点名重叠 → `missing_feature_module`；`JSONDecodeError` 且栈在脚本 parse stdout → `harness_error`（先于 feature_fail） |
| **Q5** 弱断言 | httpx-streaming；narwhals | BC-05；SCC-06；DSL-04；L10 | **O8 非 stub 不强制契约** → streaming 类题仍走 legacy，L10 要么整卷拒要么放过存在性。score DSL-04 仅扣分选稿，**不阻止落盘弱卷** | **ADD** L10w（legacy）；**KEEP** BC-05/SCC-06 契约路径；**DEFER** 非 stub 强制契约到 3.4.1 | **L10w**：legacy 路径若 ≥1 个 AC 段主断言仅为 `hasattr`/`in dir`/`getattr(..., True)` → **warning + score 重罚**（不整卷 blocking，除非 **全部** Must 段皆 existence → 仍 L10 blocking）。避免「一刀切拒完」与「全放行」两极 |
| **Q6** 窄/过宽 | multipart 窄；`_internal` 过宽 | BC-06；BC-W2 | BC-06 只查 call_graph；脚本仍可 `from x._internal import`。NARROW 保持 warning 正确 | **ADD** SCC-09；**KEEP** BC-06/W2 | **SCC-09**：AC 段 import/属性访问匹配 `\._[A-Za-z]` 或 `._internal` 且符号未出现在 Issue 正文 → blocking → 标 `render_error` 或回写删私有（优先重渲染禁模板） |
| **Q7** 决策落盘 | bandit/sqlfmt 等 | ART（WP） | 非「审核条目」而是 persist；机械上缺 **pick 后校验** | **ADD** ART-M1 | **ART-M1**：`final_action=no_script` ⇒ accepted 路径无 `test_feature.py`（删或隔离）；机器断言进 run report |

---

## 2. 修订后机械规则总表（3.4.0）

### 2.1 BehaviorContract（填表后 / 修表后）

| rule_id | when | path | severity | 机器判定要点 | 失败处置 | 防 Q |
|---------|------|------|----------|--------------|----------|------|
| BC-01…05,11,12 | BC | contract | blocking | 同 FINAL §3.5.6 | S_REPAIR / no_script | Q1/Q5 |
| BC-06 | BC | contract | blocking | call_graph 私有路径 | 修表 | Q6 |
| **BC-07** | BC | contract | **blocking（S1 web/cli）** | 缺 `entrypoint` | 修表补入口 | Q3 |
| BC-08 | BC | contract | blocking | recipe_id / forbidden on graph | 修表 / 换 recipe | Q3 |
| BC-09 | BC | contract | blocking | 关键词方向冲突 | 修表 | Q2 |
| **BC-09b** | BC | contract | blocking | quote 含 required+none 且 expect.value 为非 null 容器 | 修表（改 field_path+null 或 degraded raises） | Q2 cattrs |
| BC-10 | BC | contract | warning@S1 / blocking@S2 | async 无 harness 标记 | 补标记；渲染强制 async 模板 | Q2 |
| BC-W1/W2 | BC | contract | warning | 过宽异常 / 过窄覆盖 | 不挡渲染 | Q6 |

### 2.2 渲染后 SCC-M + DSL

| rule_id | when | path | severity | 机器判定要点 | 失败处置 | 防 Q |
|---------|------|------|----------|--------------|----------|------|
| SCC-01…07 | post-render | contract | 同 FINAL | 同 FINAL | render_error / S_REPAIR | Q1/Q5/表脚本漂 |
| **SCC-08** | post-render | contract | blocking | recipe card required/forbidden 命中源码 | 优先重渲染；表错→S_REPAIR | Q3 |
| **SCC-09** | post-render | both | blocking | 私有 `_` / `_internal` 导入且 Issue 未点名 | 重渲染禁私有；不计「改脚本毕业」 | Q6 |
| DSL-01 | post-render | both | blocking | `run_coroutine_threadsafe` 无 running loop | 契约→async 模板重渲染 | Q2 |
| DSL-02 | pre-render | contract | =BC-09/09b | 同 BC | 同 BC | Q2 |
| DSL-03 | post-render | both | blocking | web 无 entrypoint 字符串 + `*Handler` 类名 | 删段/重渲染 | Q2/Q3 |
| DSL-04 | score | both | score_only | 无 concrete expect | 不得 strong；扣分 | Q5 |
| DSL-05 | post-render | contract | warning | shadow 可选 | 3.4.0 可不实现 | — |

### 2.3 薄 lint（L*）职责切分 — **关键修订**

| rule_id | path | severity | 语义 | 失败处置 |
|---------|------|----------|------|----------|
| L10 | **legacy_only** | blocking | 存在性主断言（现行 `_has_existence_only_ac`） | 可触发契约路径（若 enable）；否则自由 regen / no_script |
| **L10w** | **legacy_only** | warning（部分 existence）/ blocking（全 Must existence） | 见上表 Q5 | 不误杀「一强多弱」的 PARTIAL 题 |
| L12 / L14 | **legacy_only** | blocking | stub / empty-fail（现行） | stub→契约；非 stub 耗尽→no_script |
| **L10c / L12c / L14c** | **contract_only** | blocking 但 **不计自由 gen 轮** | 同形检查作双保险 | → `render_error` 或 S_REPAIR；**禁止**解释为「再自由写三轮 pytest」 |
| L1–L9,L11,L13 | both | 维持现状为主 | 见 `script_linter.py` | 契约路径上 L2/L3 若与 BC 重复，**warning 优先**，避免双 blocking 耗尽 budget |

**原则**：契约路径 lint **变薄且改处置**，不是删检查；把「拒识」改成「构造失败信号」。

### 2.4 Gate / ART 机械

| rule_id | when | severity | 判定 | 处置 | 防 Q |
|---------|------|----------|------|------|------|
| GAT-M1 | sandbox | classify | 见上 | 写入 `gate_class`；影响 calib/score | Q4 |
| ART-M1 | pick/persist | blocking 一致性 | no_script ⇒ 无 accepted 脚本文件 | 删/隔离；report 双口径 | Q7 |

---

## 3. 禁止清单（防再次「拒识堆叠」）

| 禁止 | 原因（运行经验） |
|------|------------------|
| 新增 L15「与 Issue 语义同构」机械规则 | 无正向构造手段时只增负样本；3.3 已证明 |
| 契约路径上 L10/L12 blocking 后继续 **自由 regen pytest** | igel：有脚本→拒→空手 |
| 契约路径 ScriptReviewer 改脚本毕业 | 架空 BC/SCC；O11/O12 |
| 用更严 L10 **整卷拒** 非 stub 弱断言题且无 S1 注入 | httpx-streaming 类题会 INVALID↑ |
| 把 `calibration_passed` 回写成选稿主门 | 奖励能挂不测对 |
| 默认打开表 LLM / SCC-L 当「补机械缺口」 | MVP 边界；先把 SCC-08/09、BC-09b 做实 |
| 依赖 solution.patch 做机械双态 | 硬约束 |

---

## 4. 单测用例清单（≥8）

| # | Fixture 意图 | 应命中 | 对照（不应误杀） |
|---|--------------|--------|------------------|
| T1 | 契约行 call_graph 仅 hasattr | BC-05 | 含 Retort+load 的好行 |
| T2 | quote「required fields → value None」+ expect.value=`{"a":1}` | **BC-09b** | field_path + value=null 好行 |
| T3 | recipe_id=adaptix，渲染脚本含 `name_mapping(...)(Model)` | **SCC-08** | `Retort(recipe=[name_mapping(` 好脚本 |
| T4 | 脚本 `run_coroutine_threadsafe` 无 loop | DSL-01 | `asyncio.run` 模板 |
| T5 | web 层无 path，有 `FooHandler` | DSL-03 | TestClient + `/api/...` |
| T6 | 脚本 `from pkg._internal import X`，Issue 未提 | **SCC-09** | Issue 明文点名该符号 |
| T7 | ImportError: pandas | GAT-M1 → missing_third_party | ImportError: sqlfmt.ddl + Issue 点名 ddl → feature |
| T8 | contract 渲染稿触发 L12 形 stub | **L12c→S_REPAIR**，非 legacy 自由轮+1 | legacy 真 stub 仍 L12→可进契约 |
| T9 | legacy 一题：1 强 assert + 1 hasattr AC | **L10w warning**，非整卷 L10 blocking | 全 AC 仅 hasattr → L10 blocking |
| T10 | final_action=no_script 后仍存在 accepted test_feature.py | **ART-M1** fail | calib_pass 保留文件 |

---

## 5. 对 FINAL 的补丁提纲

1. §3.5.6：BC-07 升 S1 blocking；新增 **BC-09b**；注明与 DSL-02 合并实现可接受。  
2. §3.5.10：新增 **SCC-08（recipe 源码合规）、SCC-09（私有导入）**。  
3. 新增 §14（或扩 §13）：本文件总表 + lint 切分 L10c/L12c/L14c + L10w + 禁止清单。  
4. WP-DSL / WP-GAT：交叉引用 GAT-M1、ART-M1。  
5. V4/V6 单测表并入 T1–T10。  
6. 修订号：`3.4.0-FINAL.2`。  
7. INDEX 增加 P1-11。

---

## 6. CONFLICT 检查

| 项 | 结果 |
|----|------|
| O6 entrypoint | **无冲突** — BC-07 TIGHTEN 与 O6 一致 |
| O8 仅 stub 契约 | **无冲突** — L10w 给非 stub 弱断言降级处置，不强制契约 |
| O11/O12 | **无冲突** — 新规则仍回写表/重渲染 |
| §2.4 不加表审 | **无冲突** — BC-09b 机器可判；更难句 DEFER |
| 「lint 变薄」 | **有意修订** — 变薄的是 **legacy 处置耦合**，检查项保留为 c 系列 |

**修订**：`mech-runtime-1`（2026-07-22）
