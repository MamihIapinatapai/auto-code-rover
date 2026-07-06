# Spec Parser v2.0 五探针分析报告

> **Parser 版本**：2.1.0（含 M6–M9 动态校准门禁）  
> **对比模式**：P2 deterministic vs P2 ScopePlan LLM  
> **运行范围**：Spec Parser 全流程，**止于 Search 注入前**（未跑 Search / Patch）

## 工件来源

| 模式 | 本地路径 |
|------|----------|
| deterministic | [`spec_parser_probe_v2_det/`](../../../spec_parser_probe_v2_det/) |
| scope_llm | [`spec_parser_probe_v2_scope_llm/`](../../../spec_parser_probe_v2_scope_llm/) |
| 聚合指标 | [`spec_parser_probe_p2_compare_report.json`](../../../spec_parser_probe_p2_compare_report.json) |

## 报告索引

| 文档 | 内容 |
|------|------|
| [five_probe_spec_parser_v2_analysis_summary.md](./five_probe_spec_parser_v2_analysis_summary.md) | 总表、跨题结论、det vs scope_llm 对比 |
| [sympy__sympy-11400_analysis.md](./sympy__sympy-11400_analysis.md) | ccode(sinc) + Relational 委托链 |
| [sympy__sympy-11897_analysis.md](./sympy__sympy-11897_analysis.md) | LaTeX Piecewise 括号 vs 症状锚定 |
| [sympy__sympy-12171_analysis.md](./sympy__sympy-12171_analysis.md) | MCodePrinter Derivative + Float scope |
| [sympy__sympy-12454_analysis.md](./sympy__sympy-12454_analysis.md) | is_upper + hessenberg 兄弟齐修 |
| [sympy__sympy-12481_analysis.md](./sympy__sympy-12481_analysis.md) | Permutation 守卫 + P2 定位偏差 |

## Ground Truth 参考

SWE-bench 人类补丁要点见 [`sympy_c_class_cross_case_knowledge.md`](../../baseline/sympy/sympy_c_class_cross_case_knowledge.md) 与 [`five_probe_baseline_ver1_ver11_failure_analysis.md`](../five_probe_baseline_ver1_ver11_failure_analysis.md)。
