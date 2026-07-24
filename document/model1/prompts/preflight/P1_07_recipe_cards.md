# P1-7 Prompt：Recipe Cards 最小集

## 可复制 Prompt

```text
# Role
你是库集成模式工程师。请设计 3.4.0 探针期 **4 张 Recipe Card** 的正式 JSON schema 与内容。

# 依据
WP-RCP；V1 adaptix；禁止 Retort(name_mapping=) 与 name_mapping(...)(Model).load；mashumaro field_options；httpx；aiohttp TestClient。
硬约束：不读官方测试正文；可从 README/examples 思路写 hint，但卡内容写死模式串。

# 任务
1. Card schema：id, required_patterns[], forbidden_patterns[], hint, layer, call_graph_template
2. 四卡完整实例：adaptix.name_mapping / mashumaro.field_options / httpx.client_basic / aiohttp.testclient
3. 命中规则：何时注入 Prompt、何时 BC-08/recipe_compliance blocking
4. 文件路径约定 recipe_cards/*.json

# 质量
卡写「族模式」不是单题补丁；forbidden 必须可字符串/正则检查。
```

## 审查

| 检查项 | 结果 |
|--------|------|
| 对齐 WP-RCP / V1 | PASS |
| 不读官方测 | PASS |
| 可机器检查 | PASS |

**审查结论**：PASS。
