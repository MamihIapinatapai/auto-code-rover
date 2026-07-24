# DeepSWE 评测指南

> **用途**：在 AutoCodeRover 上拉取 DeepSWE、运行 Python 子集（以及可选全量）、查看 issue 解析 / patch 产物。  
> **评测集**：[datacurve-ai/deep-swe](https://github.com/datacurve-ai/deep-swe)（113 题，Harbor 格式）  
> **当前阶段**：Phase 1 — 本地生成结构化规格 / patch；**尚未**集成 Pier 端到端评测。

---

## 目录

1. [当前测试结果摘要（Python 子集）](#1-当前测试结果摘要python-子集)
2. [路径与角色总览](#2-路径与角色总览)
3. [一次性准备](#3-一次性准备)
4. [模式 A：仅 issue 解析智能体（spec_parser）](#4-模式-a仅-issue-解析智能体spec_parser)
5. [模式 B：完整 Agent 出 patch（baseline）](#5-模式-b完整-agent-出-patchbaseline)
6. [产物查看](#6-产物查看)
7. [仓库 cache 复用与预热](#7-仓库-cache-复用与预热)
8. [失败题重跑](#8-失败题重跑)
9. [监控与常见问题](#9-监控与常见问题)
10. [相关文件索引](#10-相关文件索引)

---

## 1. 当前测试结果摘要（Python 子集）

| 项 | 值 |
|----|----|
| 测试范围 | DeepSWE **全部 34 道 Python** 题（`conf/deepswe_python_tasks.txt`） |
| 测试内容 | **仅 issue 解析智能体**（`spec_parser`，`stop_after=enrich`），**未**跑 search/patch |
| 是否全部启动并结束 | **是** — 34/34 都进入了流水线并有记录 |
| 成功 | **29/34**（已写出 `search_context.txt`） |
| 失败 | **5/34**（均为仓库 clone / git reset，非 LLM 逻辑错误） |
| 起止时间 | `2026-07-08T06:05` → `09:05`（UTC，约 3 小时） |
| 模型 | `litellm-generic-deepseek/deepseek-chat` |
| 汇总报告 | `outputs/deepswe_spec_parser/deepswe-spec-parser-python/spec_parser_run_report.json` |

### 失败 5 题

| Task ID | 原因 |
|---------|------|
| `bandit-incremental-cache-control` | 已有 work/cache 损坏，`git reset --hard` 失败 |
| `koota-entity-snapshot-rollback` | `pmndrs/koota` clone / fetch 失败 |
| `langchain-request-coalescing` | `langchain-ai/langchain` clone 失败（仓库大 + 网络） |
| `textual-kitty-key-phases` | `Textualize/textual` shallow fetch 3 次失败 |
| `textual-richlog-follow-state` | 同上另一 commit，完整 fetch 仍失败 |

### 结论

- **Python 题单已全部跑完一轮**（无遗漏、未中途假死后挂起）。
- **成功率为 29/34**；失败题可修 cache / 网络后按 [§8](#8-失败题重跑) 补跑。
- **完整 Agent + patch**（`conf/deepseek-deepswe.conf`）**尚未**对 34 题做过批量跑；Pier 评测尚未集成。

---

## 2. 路径与角色总览

```text
/datadisk/pengxm/auto-code-rover/
├── third_party/deep-swe/              # DeepSWE 任务定义（113 tasks，Harbor）
├── third_party/deepswe-repos/
│   ├── cache/{owner}__{repo}@{commit12}/   # 按 (repo, commit) 去重的只读 baseline
│   └── work/{instance_id}/                 # 每题可写副本
├── conf/
│   ├── .env                                # DEEPSEEK_API_KEY / HF_TOKEN
│   ├── deepswe_python_tasks.txt            # 34 道 Python
│   ├── deepswe_all_tasks.txt               # 113 道全量
│   ├── deepseek-deepswe-spec-parser.conf   # 模式 A：仅 issue 解析
│   └── deepseek-deepswe.conf               # 模式 B：完整 Agent + patch
├── scripts/
│   ├── setup_deepswe.sh                    # 拉取评测集 + 生成题单
│   ├── run_deepswe_spec_parser.py          # 模式 A 入口
│   ├── run_deepswe.py                      # 模式 B 入口
│   └── run_deepswe_docker.sh               # 模式 B Docker 包装
└── outputs/
    ├── deepswe_spec_parser/.../            # 模式 A 产物
    ├── deepswe_run/.../                    # 模式 B 运行日志目录
    └── deepswe_patches/                    # 模式 B 收集的 patch
```

推荐在 Docker 容器 `pengxm-acr-replicate`（镜像 `yuntongzhang/auto-code-rover:experiment`）内跑，与现有 SWE-bench 流程一致。  
**注意**：`third_party/deep-swe` 与 `third_party/deepswe-repos` 必须是**仓库内真实目录或本机可解析路径**；绝对路径符号链接在容器内可能失效。

---

## 3. 一次性准备

### 3.1 凭证

在 `conf/.env`（勿提交 git）中配置：

```bash
DEEPSEEK_API_KEY=sk-...
HF_TOKEN=hf_...   # 仅从 Hugging Face 拉数据集时需要；GitHub clone 主路径可不依赖
ACR_TOKEN_LIMIT=4096
```

加载：

```bash
set -a && source conf/.env && set +a
# 或
source scripts/source_env.sh
```

### 3.2 拉取 DeepSWE 与生成题单

```bash
cd /datadisk/pengxm/auto-code-rover
bash scripts/setup_deepswe.sh
# 可选：从 HF 拉（需 gated + HF_TOKEN）
# bash scripts/setup_deepswe.sh --from-hf
```

默认将任务放到 `third_party/deep-swe`，并写入：

- `conf/deepswe_all_tasks.txt`（113）
- `conf/deepswe_python_tasks.txt`（34）

校验：

```bash
test -f third_party/deep-swe/tasks/manifest.json
wc -l conf/deepswe_python_tasks.txt   # 期望 34
```

### 3.3 Docker 容器

```bash
docker ps --filter name=pengxm-acr-replicate
# 若不存在，可由 run_deepswe_docker.sh 自动创建，或复用现有 ACR 容器
```

容器内工作目录：`/workspace/acr`（绑定项目根目录）。

---

## 4. 模式 A：仅 issue 解析智能体（spec_parser）

用于验证 / 迭代「规范解析」模块，输出注入 search 的 `search_context.txt`。**不跑** search、不写 patch。

### 配置

`conf/deepseek-deepswe-spec-parser.conf`：

- `selected_tasks_file: conf/deepswe_python_tasks.txt`
- `spec_parser_stop_after: enrich`（P1 结构化 + P2 enrichment；跳过沙箱校准脚本）
- `output_dir: outputs/deepswe_spec_parser`

### 冒烟（1 题）

```bash
cd /datadisk/pengxm/auto-code-rover
set -a && source conf/.env && set +a

docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}" \
  pengxm-acr-replicate bash -lc '
    source /root/miniconda3/etc/profile.d/conda.sh && conda activate auto-code-rover
    cd /workspace/acr
    DEEPSWE_MAX_TASKS=1 PYTHONPATH=. python scripts/run_deepswe_spec_parser.py \
      --conf-file conf/deepseek-deepswe-spec-parser.conf
  '
```

### 全量 Python（34 题）

```bash
docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}" \
  pengxm-acr-replicate bash -lc '
    source /root/miniconda3/etc/profile.d/conda.sh && conda activate auto-code-rover
    cd /workspace/acr
    PYTHONPATH=. python scripts/run_deepswe_spec_parser.py \
      --conf-file conf/deepseek-deepswe-spec-parser.conf
  ' 2>&1 | tee /tmp/deepswe_spec_parser_run.log
```

### 可选参数

| 环境变量 / 参数 | 含义 |
|-----------------|------|
| `DEEPSWE_MAX_TASKS=N` | 只跑题单前 N 题 |
| `--stop-after extract\|enrich\|fusion\|calibration\|full` | 覆盖 conf 中的截断阶段 |

首次全量预计 **2–4 小时**（瓶颈是 GitHub clone）；有 cache 后可大幅缩短。

---

## 5. 模式 B：完整 Agent 出 patch（baseline）

Phase 1 出 patch；默认 **关闭** `spec_parser` / semantic injection（见 `conf/deepseek-deepswe.conf`）。

### 冒烟

```bash
cd /datadisk/pengxm/auto-code-rover
set -a && source conf/.env && set +a
DEEPSWE_MAX_TASKS=1 bash scripts/run_deepswe_docker.sh
```

### 全量 Python

```bash
bash scripts/run_deepswe_docker.sh
# 或指定 conf / 日志
DEEPSWE_CONF=conf/deepseek-deepswe.conf \
DEEPSWE_LOG=outputs/deepswe_docker_run.log \
  bash scripts/run_deepswe_docker.sh
```

等价于容器内：

```bash
python scripts/run_deepswe.py --conf-file conf/deepseek-deepswe.conf
```

若要打开 issue 解析再跑 Agent，在 conf 中设：

```text
enable_spec_parser:true
```

（并视需要加 `--spec-parser-only` 相关 CLI；模式 A 更适合纯规格联调。）

34 题完整 Agent **显著更久**（每题常 15–30+ 分钟），建议先 1 题冒烟再全量。

---

## 6. 产物查看

### 模式 A（issue 解析 → 给 search 用的上下文）

根目录：

```text
outputs/deepswe_spec_parser/deepswe-spec-parser-python/
```

| 文件 | 含义 |
|------|------|
| `<task_id>/search_context.txt` | **注入 search 的文本**（优先看这个） |
| `<task_id>/shared_working_memory.json` | 完整结构化规格 (SWM) |
| `<task_id>/target_resolution.json` | 目标文件候选 |
| `<task_id>/repo_enrichment.json` | 仓库侧 enrichment |
| `<task_id>/spec_fusion.json` | 融合摘要 |
| `<task_id>/error.txt` | 失败 traceback |
| `spec_parser_run_report.json` | 全库 ok/fail 汇总 |

快速统计：

```bash
OUT=outputs/deepswe_spec_parser/deepswe-spec-parser-python
find "$OUT" -name search_context.txt | wc -l
python3 -c "import json; print(json.load(open('$OUT/spec_parser_run_report.json'))['summary'])"
```

### 模式 B（patch）

| 路径 | 含义 |
|------|------|
| `outputs/deepswe_run/<expr_id>/<task_id>_<timestamp>/` | 单次运行目录 |
| `outputs/deepswe_patches/<instance_id>.patch` | 汇总后的 patch |
| `outputs/deepswe_predictions.json`（或 runner 写出的 predictions） | 批量预测汇总 |
| `outputs/deepswe_docker_run.log` | Docker 包装日志 |

---

## 7. 仓库 cache 复用与预热

DeepSWE 任务目录只有 `instruction.md` + `task.toml`，**不含**源码。每次跑题前会：

1. 在 `deepswe-repos/cache/{owner}__{repo}@{commit12}/` 确保有 baseline（已有 `.git` 则跳过 clone）
2. 复制到 `deepswe-repos/work/{instance_id}/`（已有则 `git reset --hard`）

### 建议

- **长期保留 `cache/`**，不要每次清空。
- `work/` 可删可留；删掉只会多一次 `copytree`，比重新 clone 快得多。
- 同一 repo **不同 commit** 会占用不同 cache 目录。
- clone 失败时脚本会删除半成品 cache 再重试（最多 3 次）。

经常复测时，第一次全量跑完即可形成 cache；失败题建议先在主机或容器内手动：

```bash
# 示例：预热某个 repo@commit（在 conf 的 deepswe_repos_dir/cache 下）
git init ...
git remote add origin https://github.com/<org>/<repo>.git
git fetch --depth 1 origin <full_commit_sha>
# 或完整 clone 后 checkout 到指定 commit，目录名遵循 cache_key 约定
```

实现见 `app/deepswe/repo_setup.py`。

---

## 8. 失败题重跑

### 8.1 修损坏的 bandit work/cache

```bash
# 删除有问题的 work（必要时连同对应 cache）
rm -rf third_party/deepswe-repos/work/bandit-incremental-cache-control
# 若 cache 不完整：
# rm -rf third_party/deepswe-repos/cache/PyCQA__bandit@765f00d3f202
```

### 8.2 单题 / 失败列表重跑（模式 A）

新建临时题单，例如 `conf/deepswe_python_retry.txt`：

```text
bandit-incremental-cache-control
koota-entity-snapshot-rollback
langchain-request-coalescing
textual-kitty-key-phases
textual-richlog-follow-state
```

临时改 conf 的 `selected_tasks_file`，或复制一份 conf 后修改，再跑：

```bash
PYTHONPATH=. python scripts/run_deepswe_spec_parser.py \
  --conf-file conf/deepseek-deepswe-spec-parser.conf
```

大仓库（`langchain`、`textual`）建议在网络稳定时重试，或先手动 clone 进 `cache/`。

---

## 9. 监控与常见问题

### 监控

```bash
# 进程是否还在
pgrep -af run_deepswe_spec_parser
pgrep -af 'run_deepswe.py|run_deepswe_docker'

# 成功 / 失败计数（模式 A）
OUT=outputs/deepswe_spec_parser/deepswe-spec-parser-python
echo "OK=$(find "$OUT" -name search_context.txt | wc -l) FAIL=$(find "$OUT" -name error.txt | wc -l)"

# 日志
tail -f /tmp/deepswe_spec_parser_run.log
# 或
tail -f outputs/deepswe_docker_run.log
```

**注意**：用 `search_context.txt` 数量看进度时，失败题不计；结合日志里的 `[k/34]` 更准确。大仓库 clone 期间日志可能长时间无新行，并不代表进程卡死——可在容器内看是否有 `git fetch` / `git index-pack`。

### 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 容器内找不到 `task.toml` | `third_party/deep-swe` 指向宿主机外的绝对路径 symlink | 改成本仓库内真实目录拷贝/挂载 |
| clone exit 128 / curl 超时 | GitHub 网络 | 重试；保留 cache；大仓手动预热 |
| `git reset --hard` 失败 | work 或 shallow cache 损坏 | 删对应 `work/`（及必要时 `cache/`）后重跑 |
| host 跑缺 `natsort`/`rich`/`ollama` | 宿主机依赖不全 | 优先 Docker；或 `scripts/setup_deepswe_host_venv.sh` |
| 只要「全部成功」才算完 | 失败已写 `error.txt`，流程本身已结束 | 看 `spec_parser_run_report.json` 的 `summary` |

---

## 10. 相关文件索引

| 路径 | 说明 |
|------|------|
| `app/deepswe/` | Harbor 解析、repo cache |
| `app/raw_tasks.py` → `RawDeepSweTask` | 任务封装 |
| `app/main.py` → `deepswe` 子命令 | 完整 Agent CLI |
| `app/runner/run_deepswe.py` | patch 收集 |
| `app/spec_parser/` | issue 解析智能体 |
| `scripts/run_deepswe_spec_parser.py` | 本指南模式 A |
| `scripts/run_deepswe.py` / `run_deepswe_docker.sh` | 本指南模式 B |
| `document/model1/spec_parser_dev_plan.md` 等 | spec_parser 设计细节 |
| `document/model1/spec_parser_ver3.2_design.md` | Spec Parser **ver3.2**（审视 LLM 流水线）技术设计 |

---

## 附录：推荐日常工作流

1. **准备一次**：`setup_deepswe.sh` + 确认 `.env` + Docker 容器可用。  
2. **改算法后先冒烟**：`DEEPSWE_MAX_TASKS=1` 跑模式 A 或 B。  
3. **Python 子集回归**：模式 A 看 `search_context.txt`；模式 B 看 `deepswe_patches/`。  
4. **保留** `third_party/deepswe-repos/cache/`。  
5. 失败题清 work/cache 后小列表重跑。  
6. Phase 2（后续）：稳定出 patch 后再接 Pier 端到端评测。
