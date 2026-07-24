# P1-10 Prompt：draft_score_v34 与选稿冻结

## 可复制 Prompt

```text
# Role
你是选稿策略设计师。请冻结 draft_score_v34 权重与 D_pick_draft 规则。

# 依据
WP-SCR 草案；契约路径产物（concrete expect、recipe、SCC、false_fail_risk）；禁止 calib*100 垄断；best-of 防越修越差。

# 任务
1. 最终权重公式（可含 contract_path bonus）
2. 选稿规则：谁有资格进入候选池；同分打破；no_script 条件
3. 与 Gate 分类的交互（ENV 题不靠虚高 calib 赢）
4. 冻结声明：探针结束前不得改权重（仅开关 ablation）

# 质量
权重必须可单测；契约 S1 的 concrete expect 权重要高于「仅挂上」。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 WP-SCR / KPI 换锚 | PASS |
| 可单测 | PASS |
| 防 calib 垄断 | PASS |

**审查结论**：PASS。
