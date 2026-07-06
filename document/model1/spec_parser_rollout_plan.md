# 规范解析模块 rollout 计划（ver1 基座）

> 实施状态：已搭建模块骨架与配置；五探针迭代验证按 Gate 执行。  
> 关联：[spec_parser_dev_plan.md](spec_parser_dev_plan.md)

## 配置对照

| 项 | ver1 基座 | spec_parser_ver1 实验 |
|----|----------|----------------------|
| `enable_semantic_injection_ver1` | true | true |
| `enable_sympy_pipeline_v2` | **false** (`ACR_SYMPY_PIPELINE_V2=0`) | false |
| `enable_spec_parser` | false | true |
| Profile | `ver1` | `spec_parser_ver1` |
| Conf | `conf/deepseek-lite-300-ver1.sympy.conf` | `conf/deepseek-lite-300-spec_parser_ver1.sympy.conf` |

## 五探针题单

`conf/lite300_tasks/sympy_five_probes.txt`（顺序：12481 → 11400 → 12454 → 11897 → 12171）

## Gate 定义

| Gate | 通过标准 |
|------|---------|
| **R0** | v2 关闭；ver1 注入存在；11897 可进 L3 |
| **L1A** | 五题 JSON 合法 + 检查表 ≥80% |
| **L1B** | 11400 missing Relational；12454 co_fix hessenberg |
| **L1C** | 五题校准通过；11400 AC-REL 先失败 |
| **L1D** | `search_context.txt` 五题齐全 |
| **L2** | Search 首轮指向 GT 文件/handler |
| **L3** | 可选端到端 |

## 运行命令

```bash
# Gate R0 smoke
export ACR_SYMPY_PIPELINE_V2=0
./scripts/start_spec_parser_ver1_probe.sh sympy__sympy-12481

# Spec-only 单题
python scripts/run_spec_parser_probe.py \
  --instance-id sympy__sympy-11400 \
  --stop-after full

# 评测报告
python scripts/eval_spec_parser.py \
  --probe-dir experiment/spec_parser_probe
```

## 工件目录

```
experiment/spec_parser_probe/{instance_id}/
  shared_working_memory.json
  repo_enrichment.json
  execution_evidence.json
  spec_fusion.json
  search_context.txt
  reproduce_issue.py
  probe_review.md   # 人工填写
```

## probe_review 模板

```markdown
# Probe Review: {instance_id} round {n}

## L1-A Issue 抽取
- [ ] repair_goals 权威且非 Issue 草稿复述
- [ ] symptom_goals 与 repair_goals 分离
- [ ] fix_scope / negative_constraints 合理

## L1-B 静态 enrichment
- [ ] missing_handlers / co_fix 与 GT 一致

## L1-C 脚本与动态
- [ ] AC 分节覆盖 must
- [ ] buggy 代码校准通过
- [ ] primary_failure_ac_id 正确

## L1-D Search 上下文
- [ ] search_context.txt 含 repair_goals, co_fix, negative

## 备注

```

## 消融组（五探针）

| 组 | 配置 |
|----|------|
| A0 | ver1，无 spec_parser |
| A1 | spec_parser 仅 LLM（`--stop-after extract`） |
| A2 | + repo_enrichment（`--stop-after enrich`） |
| A3 | + 宽脚本模板（`--no-llm-script`） |
| A4 | 完整 spec_parser + Search 注入 |
