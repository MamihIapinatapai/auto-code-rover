# P1-9 Prompt：Gate 三分类决策表

## 可复制 Prompt

```text
# Role
你是校准门禁工程师。请冻结 Gate 失败四类（含 harness）的判定决策表。

# 依据
WP-GAT；O2 feature_signal_ok；sqlfmt 新模块 vs 第三方；bandit JSON；sqlite/narwhals ENV。

# 任务
1. 分类：missing_third_party / missing_feature_module / harness_error / feature_fail
2. 判定树（stderr/stdout/异常类型/Issue 点名模块）
3. 对 calibration_passed / KPI 的计入规则（对齐 O2）
4. bandit stdout 适配策略
5. 配置化扩展列表键名

# 质量
禁止为抬 calib 放宽 ENV；missing_feature_module 不得当第三方 ENV 抹掉。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 WP-GAT / O2 | PASS |
| 不放宽 ENV 装好 | PASS |
| 可编码 | PASS |

**审查结论**：PASS。
