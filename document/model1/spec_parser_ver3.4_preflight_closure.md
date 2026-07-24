# Spec Parser ver3.4.0 — 实现前设计收口（Preflight Closure）

> **状态**：Executed（由 preflight prompts P0-1…P1-10 逐条审查 PASS 后执行产出）  
> **已并入最终设计**：[spec_parser_ver3.4_design_FINAL.md](./spec_parser_ver3.4_design_FINAL.md)（实现唯一真相源；冲突以 FINAL §13.1 为准）  
> **Prompt 索引**：[prompts/preflight/INDEX.md](./prompts/preflight/INDEX.md)  
> **历史计划稿**：[spec_parser_ver3.4_design.md](./spec_parser_ver3.4_design.md)  
> **日期**：2026-07-22  
> **效力**：本文件为十点执行原始产出（溯源）；**实现变更请改 FINAL 并升修订号**，再择机回写本文件。

---

## §0 执行总览

| ID | Prompt 审查 | 执行 |
|----|-------------|------|
| P0-1 … P1-10 | 均 PASS（见各 prompt 文件内审查表） | 下文 §1–§10 |

---

## §1（P0-1）3.4.0 MVP 最小闭环边界 — FROZEN

### 1.1 三栏边界

| 必做（无开关也要有；开关默认 True） | 默认关（有开关，默认 False） | 本版不做 |
|--------------------------------------|------------------------------|----------|
| MVP BehaviorContract + `validate_contract` | 表 LLM 语义复审 `enable_contract_llm_review` | 全量题默认 Contract-First |
| 首填 `contract_fill` + 修表 `contract_repair` | SCC-L `enable_script_contract_llm` | UsageRecipe 自动挖掘 |
| S1 Renderer（lib/cli/web/async 最小集） | UsageRecipe mine | 完整 S2/S3 字段集强制 |
| SCC-M `enable_script_contract_align=True` | 异模复审 | 依赖 solution 的 patched-pass |
| ART 落盘事务一致 | — | 全库调用图 |
| GAT 三分类 | — | PERFECT 清零作为门禁 |
| Recipe Cards×4（静态） | — | — |
| Dual-State Lite 机器规则（最小集） | shadow oracle | — |
| draft_score_v34 + pick | — | — |
| **契约路径**：L10/L12/L14 stub 触发（及显式开关） | 非 stub 强制契约（O8=仅 stub） | — |

### 1.2 成功标准（沿用 §2.3，实现 KPI）

STRONG≥3；INVALID≤4；accepted 无脚本≤2；artifact_consistency=15/15；adaptix 配方层命中；cattrs/aiomonitor 已知假失败模式清除；Gate 可分类。

### 1.3 禁止范围膨胀

实现 PR 不得夹带：默认打开表审/SCC-L、全量改非 stub 路径、UsageRecipe、以 calib_pass 为主 KPI。

### 1.4 Phase 映射

- A：ART+GAT  
- B：Fill+BC+Render+SCC-M+Repair+stub 契约路径  
- C：Recipe+DSL +（可选）表审/SCC-L ablation  
- D：score+15 题回归  

---

## §2（P0-2）Agent 编排状态机 — FROZEN

### 2.1 契约路径状态

| State | 产物 | D_* | 成功下一跳 | 失败 |
|-------|------|-----|------------|------|
| `S_FILL` | draft contract | D_contract_step1/2/3 | S_BC | 解析失败→重填≤1→no_script |
| `S_BC` | bc_validate | D_contract_bc_validate | S_TABLE_REVIEW or S_RENDER | blocking→S_REPAIR 或回 S_FILL expect |
| `S_TABLE_REVIEW` | llm_review（可 skip） | D_contract_llm_review | pass/warn→S_RENDER；reject→S_REPAIR | — |
| `S_REPAIR` | items_patch 应用后 contract | D_contract_patch_apply | S_BC | budget=0→no_script |
| `S_RENDER` | test_feature.py | D_contract_render | S_LINT_THIN | render 异常→no_script |
| `S_LINT_THIN` | lint report | D_lint | pass→S_SCC_M；stub 类不应出现 | blocking→视为 render/contract bug→S_REPAIR 或 no_script |
| `S_SCC_M` | scc_report | D_scc_machine | pass→S_SCC_L_OPT or S_SANDBOX；blocking render_error→重渲染；contract_error→S_REPAIR | budget=0→no_script |
| `S_SCC_L_OPT` | 可选 | D_scc_llm | →Feedback→S_REPAIR or S_SANDBOX | — |
| `S_SANDBOX` | execution | D_gate_classify | S_PICK | — |
| `S_PICK` | accepted / no_script | D_pick_draft | ART commit | — |
| `S_NO_SCRIPT` | 清理残留 | D_persist | 结束 | — |

非契约：`S_LEGACY_*`（见 §5），与契约互斥 persist。

### 2.2 修槽预算

```text
budget = spec_parser_contract_max_expect_retries  # default 2

consume_repair_budget(reason):
  # reason ∈ table_review_reject | repair_apply | scc_contract_error | bc_after_repair
  budget -= 1
  if budget < 0: goto S_NO_SCRIPT
```

表审 reject、修表轮、SCC contract_error **共用**同一 budget；SCC-M 纯 `render_error` 重渲染 **不耗** budget（限 1 次），再失败耗 budget 或 no_script。

### 2.3 禁止

状态机内不得出现「LLM 自由改 pytest 后直接 calib」边。

---

## §3（P0-3）TableGenFeedback + apply API — FROZEN

### 3.1 TableGenFeedback Schema（canonical）

```json
{
  "feedback_id": "string",
  "source": "table_review|script_review|merged",
  "blocking": true,
  "summary_for_filler": "string<=200",
  "items": [
    {
      "must_id": "string",
      "error_type": "false_fail|off_must|weak_degraded|quote_drift|recipe_misaligned|multi_item_inconsistency|script_contract_mismatch|invented_expect|insufficient_evidence|render_error",
      "severity": "blocking|warning",
      "what_is_wrong": "string<=200",
      "evidence_digest": [{"source":"issue|contract|script|recipe","span":"<=80"}],
      "allowed_edits": ["expect","fail_mode","expect_confidence"],
      "forbidden_edits": ["call_graph","recipe_id","layer","entrypoint"],
      "suggested_patch": {
        "path": "string",
        "next_value_hint": null,
        "oracle_kind_hint": "keep|equality|field_path|raises|...",
        "rationale": "<=150"
      },
      "do_not": ["string"]
    }
  ],
  "filler_instructions": ["string"]
}
```

模块建议：`app/spec_parser/table_gen_feedback.py`

### 3.2 merge 规则

1. 同 `must_id`+同 `error_type` 去重，保留证据更长者。  
2. severity：blocking > warning。  
3. error_type 优先级：false_fail/invented_expect > quote_drift > off_must/recipe_misaligned/script_contract_mismatch > weak_degraded > multi_item > insufficient_evidence；`render_error` 单独保留且 **不进入修表 items 可改集合**（仅提示 unchanged）。  
4. `source=merged`。

### 3.3 API 草案

```python
def merge_feedback(table_review: dict|None, script_patch: dict|None) -> dict: ...

def apply_items_patch(contract: dict, repair_json: dict) -> dict:
    """Whitelist fields; rollback if validate_contract fails."""

def apply_contract_patch(contract: dict, scc_patch: dict) -> dict:
    """Map SCC findings to repair intents or noop_rerender flags."""
```

**白名单**：expect 信封、fail_mode、expect_confidence；quote 仅 quote_drift。  
**黑名单**：call_graph、recipe_id、layer、entrypoint（除非 Feedback 显式 allowed）。  
**validate_contract 失败 → 回滚**，计一次 budget。

---

## §4（P0-4）Renderer 模板表 — FROZEN

### 4.1 命名锚点（SCC 依赖）

- 函数名：`test_ac_{sanitize(must_id)}`  
- 段注释：`# --- AC-{must_id} ---`  
- 文件：`test_feature.py`

### 4.2 layer × oracle_kind 矩阵（MVP）

| layer \ kind | equality / field_path / contains | raises | http_status | stdout_regex |
|--------------|----------------------------------|--------|-------------|--------------|
| **lib** | call_graph 展开→result→assert / 字段取值 | `with pytest.raises` | N/A→降级 lib | N/A |
| **async** | `asyncio.run(_body())` 包装 await 调用 | 同上在 _body | N/A | N/A |
| **web** | TestClient + path=entrypoint | raises 少见 | `assert resp.status==` | N/A |
| **cli** | CliRunner/subprocess | 非零码可映射 fail_mode | N/A | stdout regex |

**recipe**：若 `recipe_id` 命中，arrange 段必须插入 card `call_graph_template` 文本模式（字符串级可被 SCC/recipe 检查）。

### 4.3 lib + equality 骨架

```python
# --- AC-{must_id} ---
def test_ac_{must_id}():
    # arrange — recipe/call_graph locked
    ...
    result = <primary_call>(**<inputs>)
    assert result == <expect.value>
```

### 4.4 async + equality 骨架

```python
def test_ac_{must_id}():
    async def _body():
        result = await <primary_call>(**<inputs>)
        assert result == <expect.value>
    asyncio.run(_body())
```

### 4.5 SCC 锚点映射

| SCC | 依赖 |
|-----|------|
| SCC-01 | `test_ac_*` 或 AC 注释 |
| SCC-02 | AC 段内出现 call_graph 符号 |
| SCC-03 | AC 段字面量匹配 expect.value |
| SCC-04 | `pytest.raises` / raises 形态 |
| SCC-05 | status 断言 + entrypoint 字符串 |
| SCC-06 | 禁止 hasattr 主断言 |
| SCC-07 | 字面量 ⊆ expect∪inputs∪quote |

---

## §5（P0-5）旧路径交接 — FROZEN

### 5.1 路径选择

| 条件 | 路径 |
|------|------|
| `enable_behavior_contract` 且（stub L10/L12/L14 触发 **或** `force_contract_path`） | **contract_path** |
| 其他 | **legacy_path**（3.3.1 gen→lint→script_review→calib） |

O8 CONFIRMED：非 stub 默认不强制契约。

### 5.2 契约路径上的 ScriptReviewer

- **默认 skip**（不调用改脚本 LLM）。  
- 可选 `contract_path_legacy_review=warn_only`：只写 decision 备注，**不得**改文件。  
- **禁止**契约路径「审视改 pytest 后落盘」。

### 5.3 Persist 互斥

`ArtifactStore.commit` 同一 task 只能有一份 accepted；切换路径前清理另一路径残留。

### 5.4 回滚

`enable_behavior_contract=False` → 全 legacy（3.3.1 行为）。

---

## §6（P1-6）O1–O12 决策 — FROZEN

| ID | Decision | Config / 备注 |
|----|----------|----------------|
| O1 | **CONFIRMED** degraded S1 写入主路径，标 `tier=S1`/`degraded` | 下游可读 meta |
| O2 | **CONFIRMED** `missing_feature_module` → `feature_signal_ok` 单计，不算普通 calib_pass | GAT |
| O3 | **CONFIRMED** 探针卡 recipe blocking；通用 warning | Recipe |
| O4 | **CONFIRMED** examples 非 test_*.py 允许；pytest 金标目录禁止 | UsageRecipe 预留 |
| O5 | **CONFIRMED** UsageRecipe 默认关 | `enable_usage_recipe_mine=False` |
| O6 | **CONFIRMED** web/cli S1 强制 entrypoint | `s1_require_entrypoint_for_cli_web=True` |
| O7 | **CONFIRMED** quote 空白归一化子串 | BC-02 |
| O8 | **CONFIRMED** 仅 stub+可选 force | 见 §5 |
| O9 | **CONFIRMED** 表 LLM 审默认关；ablation high_risk_only | |
| O10 | **CONFIRMED** reject_false_fail 耗尽 → no_script | |
| O11 | **CONFIRMED** SCC-M on / SCC-L off | |
| O12 | **CONFIRMED** 表优先重渲染 | |

无 CHANGED 项。

---

## §7（P1-7）Recipe Cards 最小集 — FROZEN

### 7.1 Card schema

```json
{
  "id": "adaptix.name_mapping",
  "layer": "lib",
  "required_patterns": ["Retort(recipe=[", "name_mapping("],
  "forbidden_patterns": ["Retort(name_mapping=", "name_mapping(...)("],
  "hint": "Use Retort(recipe=[name_mapping(...)]).load / get_loader",
  "call_graph_template": ["Retort", "name_mapping", "load"],
  "blocking": true
}
```

路径：`app/spec_parser/recipe_cards/*.json`

### 7.2 四卡

| id | required（要旨） | forbidden（要旨） |
|----|------------------|-------------------|
| `adaptix.name_mapping` | `Retort(recipe=[` + `name_mapping(` | `Retort(name_mapping=`；Provider 直调 `name_mapping(...)(` |
| `mashumaro.field_options` | `field(metadata=` + `field_options` | 错误顶层 kwargs 绑 Model |
| `httpx.client_basic` | `httpx.` 客户端调用模式 | 纯 hasattr aiter |
| `aiohttp.testclient` | `TestClient` + 真实 path | 臆造 `*Handler` 类名当入口 |

### 7.3 命中

Issue/Anchor/recipe_id 命中 → 注入 fill Prompt；渲染后 `recipe_compliance`；探针卡 `blocking=true`（O3）。

---

## §8（P1-8）Dual-State Lite 规则 — FROZEN

| ID | 何时 | 条件 | 处置 |
|----|------|------|------|
| DSL-01 | 渲染后 / lint | AST：`run_coroutine_threadsafe` + 无 running loop 证据 | blocking；契约路径→强制 async 模板重渲染 |
| DSL-02 | 渲染前 BC/表 | Issue 含 required/None 方向 vs expect 冲突（对齐 BC-09） | BC blocking 或表审；不进 sandbox 当金标 |
| DSL-03 | 渲染后 | web 层无 entrypoint 字符串却有自定义 Handler 名 | blocking 删段/重渲染 |
| DSL-04 | score | Must 无 concrete expect | 不得 strong coverage；扣分 |
| DSL-05 | 渲染后 | （可选）契约 `shadow_check` 且有 Issue 字面量纯函数可比 | warning 记 trace；3.4.0 可不实现执行器 |

**顺序**：BC-09/表审（渲染前）→ Renderer → DSL-01/03（渲染后）→ score DSL-04。  
**不做**：默认跑 solution.patch。

---

## §9（P1-9）Gate 三分类 — FROZEN

### 9.1 判定要点

| 类 | 判定 |
|----|------|
| `missing_third_party` | ImportError 模块 ∈ 配置传递依赖集（pandas/yaml/…）且非 Issue 点名新模块 |
| `missing_feature_module` | 缺失名与 Issue/Must 点名新 API/模块高度匹配（如 sqlfmt.ddl） |
| `harness_error` | JSONDecodeError 于脚本解析 stdout；未 running loop；模板自崩 |
| `feature_fail` | 其余 AC 级断言失败 / NOT_IMPLEMENTED 在产品调用后 |

### 9.2 KPI

- `calibration_passed`：仅干净 `feature_fail` 路径意图失败。  
- `feature_signal_ok`：O2。  
- ENV/harness **不计入**脚本质量成功。

### 9.3 bandit

先 `extract_json_blob(stdout)`；失败 → `harness_error`，禁止当功能结论。

### 9.4 配置键

`spec_parser_env_transitive_modules`、`spec_parser_feature_module_name_hints`。

---

## §10（P1-10）draft_score_v34 — FROZEN

### 10.1 公式

```text
score =
  + concrete_expect_ac_count * 12
  + recipe_compliance_bonus * 15      # 0 or 1 * 15
  + scc_m_pass_bonus * 10             # NEW contract path
  + behavioral_ac_count * 6
  + (20 if feature_calib_ok else 0)   # 仅 feature_fail 语义
  + (8 if contract_path_s1 else 0)    # 有合法 behavior_contract 且 tier≥S1
  - existence_only_ac_count * 15
  - empty_fail_ac_count * 25
  - false_fail_risk_hits * 30
  - lint_violations * 10
  - coverage_missing_must * 6
  - wrong_layer * 10
  - harness_error * 20
  - env_fail * 0                      # 不奖励也不当质量分（或单独标记不可选）
```

### 10.2 选稿

1. 候选：lint 无 blocking；非纯 ENV/harness 导致的「假通过」。  
2. 契约路径优先有 `scc_m_pass` 与 concrete expect 的稿。  
3. 同分：更早 round（防越修越差）→ lint 更少。  
4. 无合格候选 → no_script（ART 清残留）。

### 10.3 冻结

探针回归结束前 **不得改权重**；仅允许开关 ablation（关 recipe bonus 等）。

---

## §11 实现启动检查单

- [ ] 已读本收口文 §1–§10  
- [ ] 配置键写入 `config.py` 草案与 §1/§6 一致  
- [ ] Phase 0 V1–V6 单测按本冻结规格写  
- [ ] 不实现本文件标「不做」项  

**修订**：`preflight-closure-1`（2026-07-22）
