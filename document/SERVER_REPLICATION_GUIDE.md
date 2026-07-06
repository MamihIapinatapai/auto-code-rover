# AutoCodeRover 服务器复现完整指南

> **用途**：供 Agent 在组内 Linux 服务器上从零完成 AutoCodeRover 方法论复现。  
> **目标**：① Pipeline 跑通（Context Retrieval → Patch Generation）；② Pilot 测试跑通（10 实例 SWE-bench Lite）；③（可选）SWE-bench Docker 自动评测与消融实验。  
> **LLM 后端**：DeepSeek API（via LiteLLM）  
> **运行环境**：Docker 镜像 `yuntongzhang/auto-code-rover:experiment`  
> **汇总来源**：`AutoCodeRover_Replication_Plan.md`、`Replication_Report.md`、`LIGHTWEIGHT_PILOT.md`、`DOCKER_PILOT_GUIDE.md`、`ABLATION_GUIDE.md` 及本地复现经验

组里服务器的 Docker 使用要求：

+ 建立持久运行的 docker 容器时，**尽量指定容器名称，以用户名（或缩写）开头**，如 `zhangsan-container-1`、`pengxm-acr-replicate` 等。对于无法区分归属的容器，将不定期进行清除。
+ docker 容器中的重要数据请创建卷或挂载到个人目录中，以免服务器升级维护时被意外清理。

**本机（pengxm）实践（与 [`scripts/run_pilot_docker.sh`](../scripts/run_pilot_docker.sh) 一致）**：

| 项 | 值 |
|----|-----|
| 持久容器名 | `pengxm-acr-replicate`（可用 `export ACR_CONTAINER_NAME=...` 覆盖） |
| 代码与实验结果 | bind 挂载 `/datadisk/pengxm/auto-code-rover` → 容器内 `/workspace/acr` |
| 镜像存储 | `/etc/docker/daemon.json` 中 `data-root: /datadisk/docker/data` |
| Hub 加速 | `registry-mirrors`（如 DaoCloud、轩辕等）；逻辑镜像仍为 `docker.io/yuntongzhang/auto-code-rover:experiment` |
| 常用日志 | `docker_pull.log`、`pilot_docker_run.log`、`pilot_eval.log`、`wait_l2.log` |

---

## 目录

0. [本服务器复现进度（pengxm）](#0-本服务器复现进度pengxm)
0.1. [Pilot 推理 + 评测完整流程](#01-pilot-推理--评测完整流程)
1. [复现目标与验收标准](#1-复现目标与验收标准)
2. [硬件与软件前置条件](#2-硬件与软件前置条件)
3. [代码仓库说明（必读）](#3-代码仓库说明必读)
4. [阶段 A：轻量 Pipeline 验证（可选，推荐先做）](#4-阶段-a轻量-pipeline-验证可选推荐先做)
5. [阶段 B：Docker 环境与 Pilot 实验（主流程）](#5-阶段-bdocker-环境与-pilot-实验主流程)
6. [阶段 C：SWE-bench Docker 自动评测（补全指标）](#6-阶段-cswe-bench-docker-自动评测补全指标)
   - [6.8 Pilot 推理 + 评测端到端（本机推荐顺序）](#68-pilot-推理--评测端到端本机推荐顺序)
   - [6.7 SWE-bench Lite 300 任务 ID 与评测镜像预拉取（防漏拉）](#67-swe-bench-lite-300-任务-id-与评测镜像预拉取防漏拉)
7. [阶段 D：消融实验 E0–E4（可选）](#7-阶段-d消融实验-e0e4可选)
8. [系统架构速览](#8-系统架构速览)
9. [已知 Bug 与解决方案（完整清单）](#9-已知-bug-与解决方案完整清单)
10. [调试检查清单](#10-调试检查清单)
11. [结果目录与成功标志](#11-结果目录与成功标志)
12. [费用与资源估算](#12-费用与资源估算)
13. [Agent 执行 Checklist（逐步打勾）](#13-agent-执行-checklist逐步打勾)

---

## 0. 本服务器复现进度（pengxm）

> **更新日期**：2026-06-01  
> **工作目录**：`/datadisk/pengxm/auto-code-rover`  
> **续跑入口**：见 [§0.1 Pilot 推理 + 评测完整流程](#01-pilot-推理--评测完整流程) 与 [§13](#13-agent-执行-checklist逐步打勾)。

| 阶段 | 状态 | 证据 / 备注 |
|------|------|-------------|
| 准备（密钥、§3.2 修复、子模块） | ✅ 完成 | `conf/.env`（勿提交 git）；`SWE-bench-docker/` 子模块在仓库内 |
| L1 Pipeline | ✅ 完成 | `demo_pilot/output/pilot-divide_2026-05-30_16-11-08/` |
| `docker pull experiment` | ✅ 完成 | `docker_pull.log` 含 `Status: Downloaded newer image`；`docker images` 约 **57.6GB** |
| **Lite 300 评测镜像（83）** | ✅ 完成 | 2026-06-01 验收 `missing.txt` 0 行；详见 [§6.7.3](#673-预拉取清单与操作推荐) 与 [`SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md`](SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md) §0 |
| L2 Pilot（Agent 推理） | ⚠️ 部分完成，**待验收** | `pilot_docker_run.log`（2026-05-30）；曾生成 `predictions_for_swebench.json`；**10/10 applicable 待核对** |
| L3 Eval（Pilot 10 题） | ⏳ **下一步** | 83 镜像已就绪；[`run_pilot_eval_incremental.sh`](../scripts/run_pilot_eval_incremental.sh) **默认保留**预拉镜像（见 [§6.4](#64-评测流程说明)） |
| 阶段 D 消融 | ❌ 未开始 | — |
| `Replication_Report.md` | ❌ 未填 | 见 [§11.2](#112-填写复现报告) 待填字段 |

---

## 0.1 Pilot 推理 + 评测完整流程

> **目标**：验证 **L2 Agent 推理 → L3 Docker 评测** 全链路。Pilot 仅 **10 题**，所需 **9** 个唯一 `autocoderover/swe-bench-*` 镜像均已包含在已预拉的 **83** 个镜像中，**评测时直接调用本地镜像，无需边评边删、边评边拉**。

### 前置（一次性）

```bash
cd /datadisk/pengxm/auto-code-rover
source scripts/source_env.sh   # 加载 conf/.env 中的 DEEPSEEK_API_KEY

# 确认实验容器与 83 镜像
docker ps --filter name=pengxm-acr-replicate
docker images --format '{{.Repository}}:{{.Tag}}' | grep -c '^autocoderover/swe-bench'   # 应为 83
wc -l swe_lite_pull/missing.txt   # 应为 0（见 SWE_BENCH_LITE_300_IMAGE_PULL_PLAN §0）
```

### 步骤 1：核对或重跑 L2 推理（Agent）

```bash
docker exec pengxm-acr-replicate ls /workspace/acr/experiment/deepseek-lite-pilot 2>/dev/null

python3 -c "import json; d=json.load(open('experiment/deepseek-lite-pilot/predictions_for_swebench.json')); print(len(d) if isinstance(d,dict) else len(d))"
ls experiment/deepseek-lite-pilot/applicable_patch 2>/dev/null | wc -l
```

- **通过**（10 条 predictions、10 个 applicable_patch、`no_patch/` 为空）→ 步骤 3。  
- **不通过** → 步骤 2 重跑 Agent（`SKIP_EVAL=1`，仅推理）：

```bash
bash scripts/run_pilot_docker.sh 2>&1 | tee -a pilot_docker_run.log
```

[`run_pilot_docker.sh`](../scripts/run_pilot_docker.sh) 已在 `docker exec` 中传入 **`SKIP_EVAL=1`**，不会进入 L3。验收标准见 [§5.7](#57-l2-验收)。

### 步骤 2：同步 L2 产物到 `pilot_output/`（可选）

```bash
mkdir -p pilot_output
docker cp pengxm-acr-replicate:/workspace/acr/experiment/deepseek-lite-pilot/. ./pilot_output/
```

### 步骤 3：L3 逐题评测（Pilot 10 题）

```bash
# 首次
bash scripts/run_pilot_eval_incremental.sh 2>&1 | tee pilot_eval.log

# 断点续跑（保留 eval_progress.json）
bash scripts/run_pilot_eval_incremental.sh --resume 2>&1 | tee -a pilot_eval.log
```

**镜像策略（2026-06-01 起默认）**：

| 行为 | 默认 | 旧行为（磁盘极紧张时） |
|------|------|------------------------|
| 每题后删除 `sweb.eval` 容器 | ✅ | ✅ |
| 每题后删除 `autocoderover/*` 预拉镜像 | ❌ **保留** | `--prune-preloaded-images` 或 `PRUNE_AUTOCODEROVER_IMAGES=1` |

> **禁止**：在未执行 `setup_swe_bench_docker.sh` 时直接 `python scripts/run.py conf/deepseek-lite.conf`（会误进 eval 且可能缺 `/opt/SWE-bench-docker`，见 [§9.7](#97-l2l3-衔接与-skip_eval)）。

### 步骤 4：L3 验收

```bash
ls experiment/deepseek-lite-pilot/report/report.json
ls experiment/deepseek-lite-pilot/eval_logs/ | wc -l   # 目标：10
python -c "
import json
r = json.load(open('experiment/deepseek-lite-pilot/report/report.json'))
print('resolved:', len(r.get('resolved', [])))
print('total:', r.get('total_num_tasks'))
"
```

详见 [§6.5](#65-l3-验收)。

### 步骤 5：填写复现报告

将 Resolved Rate 等写入 `document/Replication_Report.md`（[§11.2](#112-填写复现报告)）。

### 步骤 6：（可选）Lite 300 全量

按 **12 个 repo 分终端**跑 L2（`num_processes=2`）→ L3 → 飞书 **Baseline** 上传。83 评测镜像已在宿主机，无需改 prune 逻辑。

**一键启动（tmux 12 窗口）：**

```bash
cd /datadisk/pengxm/auto-code-rover
source scripts/source_env.sh
bash scripts/start_lite300_tmux.sh
tmux attach -t lite300-baseline
```

**单库手动跑：**

```bash
REPO=django bash scripts/run_lite300_repo.sh          # 全量 L2→L3→飞书
REPO=django bash scripts/run_lite300_repo.sh --resume # 仅 L3 断点续跑
```

脚本与配置见 [§6.7.6](#676-lite-300-分库-pipeline)；飞书上传见 [`FEISHU_BITABLE_SERVER_PIPELINE.md`](FEISHU_BITABLE_SERVER_PIPELINE.md) §6。

---

## 0.2 从早期进度续跑（简表）

| §0.1 步骤 | 内容 |
|-----------|------|
| 前置 | 容器运行 + **83** 镜像验收 |
| 步骤 1–2 | L2 推理验收 / `run_pilot_docker.sh` |
| 步骤 3 | L3 `run_pilot_eval_incremental.sh`（默认**不删**预拉镜像） |
| 步骤 4–5 | L3 验收 + `Replication_Report.md` |

历史 L2/L3 衔接问题见 [§9.7](#97-l2l3-衔接与-skip_eval)（`run_pilot_docker.sh` 已默认 `SKIP_EVAL=1`）。

---

## 1. 复现目标与验收标准

### 1.1 方法论复现（非数值对齐）

本复现采用 **DeepSeek-Chat** 替代论文中的 GPT-4，目标是 **跑通完整管线**，而非与论文 19%/30.67% Resolved Rate 数值对齐。

### 1.2 三级验收

| 级别 | 内容 | 验收标准 |
|------|------|----------|
| **L1 Pipeline** | 两阶段 Agent 跑通 | 产生 `search_round_*.json`、`extracted_patch_*.diff`、`selected_patch.json`、`cost.json` |
| **L2 Pilot** | 10 实例 SWE-bench Lite | 10/10 生成 applicable patch；`predictions_for_swebench.json` 含 10 条记录 |
| **L3 Eval** | SWE-bench Docker 评测 | 生成 `report/report.json`、`stats.json`；可统计 Resolved Rate |

**本服务器（pengxm，2026-06-01）**：**L1 ✅、Lite 83 镜像 ✅、L2 ⚠️（待 10/10 验收）、L3 Pilot ⏳（下一步）**。详见 [§0](#0-本服务器复现进度pengxm) 与 [§0.1](#01-pilot-推理--评测完整流程)。

---

## 2. 硬件与软件前置条件

### 2.1 硬件

| 资源 | 最低 | 推荐 |
|------|------|------|
| CPU | 8 核 | 16 核+ |
| 内存 | 32 GB | 64 GB |
| 磁盘 | 100 GB 可用 | 150 GB+ |
| GPU | **不需要** | — |
| 网络 | 稳定访问 DeepSeek API + Docker Hub | 国内建议配置镜像加速 |

### 2.2 软件

- Linux 服务器（Ubuntu 20.04/22.04 推荐；**不要在 Windows 原生环境跑全量 SWE-bench**）
- Docker Engine（含 docker CLI，daemon 正常运行）
- Git
- DeepSeek API Key（已充值）

### 2.3 环境变量（全程必须）

**推荐**（读取 gitignore 的 `conf/.env`）：

```bash
cd /datadisk/pengxm/auto-code-rover
cp conf/.env.example conf/.env   # 首次：填入 DEEPSEEK_API_KEY
chmod 600 conf/.env
source scripts/source_env.sh     # 加载 DEEPSEEK_API_KEY、ACR_TOKEN_LIMIT 等
```

或手动 export：

```bash
export DEEPSEEK_API_KEY=sk-你的真实密钥    # 勿写入代码或 git
export ACR_TOKEN_LIMIT=4096                 # 默认 1024 会截断 patch 输出
export PYTHONIOENCODING=utf-8
```

> **安全**：密钥仅通过 `conf/.env` 或环境变量传递，参考 `conf/.env.example`，**切勿提交真实密钥**。

---

## 3. 代码仓库说明（必读）

### 3.1 克隆与分支

```bash
git clone <仓库地址> auto-code-rover
cd auto-code-rover
git submodule update --init --recursive   # 含 SWE-bench-docker 子模块
```

### 3.2 本地已修复的关键改动（迁移时必须保留）

以下改动已在本地复现中验证，**服务器上应使用含这些改动的代码**：

| 文件 | 改动 | 原因 |
|------|------|------|
| `app/agents/agent_search.py` | 补全 generator 第三次 yield（analyze and select 阶段） | 原代码截断导致 Context Retrieval 不完整 |
| `app/config.py` | `backup_model` 改为 `litellm-generic-deepseek/deepseek-chat` | 原默认 GPT-4o，重试时会调用 OpenAI |
| `app/config.py` | 新增 `enable_text_only_search` | E1 消融实验需要 |
| `app/main.py` | 新增 `--enable-text-only-search`；`--model` 不再限制 choices | 支持 DeepSeek 与消融 |
| `app/model/common.py` | `max_tokens=int(os.getenv(...))` | 修复类型问题 |
| `app/task.py` | `PlainTask.execute_reproducer()` | local-issue 模式 reproducer 执行 |
| `scripts/run_pilot_docker.sh` | `--entrypoint ""`、conda `/root/miniconda3`、容器名 `pengxm-acr-replicate`、bind mount | Docker 与组规 |
| `scripts/check_prerequisites.py` | 实验镜像内跳过 docker daemon 检查 | 容器内无 docker CLI |
| `scripts/run.py` | 支持 `SKIP_EVAL=1` 仅跑 Agent | L2 与 L3 分离 |
| `scripts/run_pilot_eval_incremental.sh` | 逐题 L3 评测；默认**保留**预拉 `autocoderover/*` 镜像 | 见 [§6](#6-阶段-cswe-bench-docker-自动评测补全指标) |
| `scripts/setup_swe_bench_docker.sh` | 安装 `/opt/SWE-bench-docker` | L3 前置 |
| `scripts/source_env.sh` | 加载 `conf/.env` | 安全读密钥 |
| `requirements-pilot-minimal.txt`、`demo_pilot/` | L1 轻量依赖与样例 | 见 §4 |

**验证修复是否生效**：

```bash
python scripts/check_prerequisites.py
# 应全部 PASS，尤其 "agent_search.py third yield"
```

### 3.3 关键配置文件

| 文件 | 用途 |
|------|------|
| `conf/deepseek-lite.conf` | Pilot 主实验配置（10 题，`selected_tasks_file` → `pilot_tasks.txt`） |
| `conf/pilot_tasks.txt` | **Pilot 子集**：10 个跨仓库 SWE-bench Lite 实例 |
| `conf/swe_lite_tasks.txt` | **Lite 全量**：官方 **300** 题 instance ID（见 [§6.7](#67-swe-bench-lite-300-任务-id-与评测镜像预拉取防漏拉)） |
| `conf/vanilla-lite.conf` | 论文复现式全量 Lite 配置（`selected_tasks_file` → `swe_lite_tasks.txt`） |
| `conf/ablation/e0-baseline.conf` ~ `e4-round-limit-3.conf` | 消融实验 |
| `conf/.env.example` | 环境变量模板 |

---

## 4. 阶段 A：轻量 Pipeline 验证（可选，推荐先做）

**用途**：在拉取 95GB 实验镜像之前，用 <500MB 依赖验证 Agent 两阶段管线是否正常。  
**耗时**：~17 秒/任务，费用 ~$0.01。

### 4.1 安装依赖

```bash
cd auto-code-rover
python3 -m venv .venv && .venv/bin/pip install -r requirements-pilot-minimal.txt
source scripts/source_env.sh
# 样例仓库需 git init（L1 首次）：
cd demo_pilot/sample_project && git init && git add -A && git commit -m "initial"
```

### 4.2 运行 local-issue 样例

```bash
python ACR.py local-issue \
  --model litellm-generic-deepseek/deepseek-chat \
  --model-temperature 0.2 \
  --conv-round-limit 5 \
  --task-id pilot-divide \
  --local-repo demo_pilot/sample_project \
  --issue-file demo_pilot/issues/divide_by_zero.md \
  --output-dir demo_pilot/output \
  --num-processes 1 \
  --no-print
```

### 4.3 L1 验收

检查 `demo_pilot/output/pilot-divide_*/` 下是否存在：

```
search/search_round_*.json
search/tool_call_layers.json
extracted_patch_*.diff
selected_patch.json
cost.json
```

预期补丁：在除法函数中添加 `ValueError("Cannot divide by zero")`。

---

## 5. 阶段 B：Docker 环境与 Pilot 实验（主流程）

### 5.1 拉取实验镜像

```bash
docker pull yuntongzhang/auto-code-rover:experiment 2>&1 | tee docker_pull.log
bash scripts/monitor_docker_pull.sh   # 查看进度摘要
```

- 逻辑来源：**Docker Hub** `docker.io/yuntongzhang/auto-code-rover:experiment`；本机经 `/etc/docker/daemon.json` 的 `registry-mirrors` 加速。
- `docker images` 可能显示约 **57–95 GB**（层共享与显示方式不同，以 `docker image inspect` 能启动为准）。
- 存储位置：**`/datadisk/docker/data`**（`data-root`），非个人项目目录。
- **勿并行**多个 `docker pull` 同一镜像；拉取失败见 [§9.1](#91-docker-镜像拉取)。

### 5.2 一键运行 Pilot（推荐，仅 L2 Agent）

```bash
cd /datadisk/pengxm/auto-code-rover
source scripts/source_env.sh
bash scripts/run_pilot_docker.sh 2>&1 | tee pilot_docker_run.log
```

脚本自动完成：
1. 读取 `conf/.env`（若存在）
2. 检查/拉取镜像
3. 创建或启动容器 **`pengxm-acr-replicate`**（`-v $(pwd):/workspace/acr`、`-v /var/run/docker.sock`）
4. 容器内运行 `check_prerequisites.py`
5. 运行 `python scripts/run.py conf/deepseek-lite.conf`（宿主机应设 `SKIP_EVAL=1`；见 [§9.7](#97-l2l3-衔接与-skip_eval)）
6. `docker cp` 结果到主机 **`pilot_output/`**

### 5.3 手动分步运行（调试时使用）

```bash
# 主机：启动长期运行容器（容器名须以用户名开头）
export ACR_CONTAINER_NAME=pengxm-acr-replicate   # 可选，默认已是此名
docker run -d --name pengxm-acr-replicate --entrypoint "" \
  -v "$(pwd):/workspace/acr" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DEEPSEEK_API_KEY \
  -e ACR_TOKEN_LIMIT=4096 \
  yuntongzhang/auto-code-rover:experiment \
  sleep infinity

docker exec -it pengxm-acr-replicate bash
```

```bash
# 容器内
source /root/miniconda3/etc/profile.d/conda.sh
conda activate auto-code-rover
cd /workspace/acr

ls /opt/SWE-bench/setup_result/setup_map.json
ls /opt/SWE-bench/setup_result/tasks_map.json

python scripts/check_prerequisites.py
export SKIP_EVAL=1    # 仅 L2 Agent，跳过 L3 eval
python scripts/run.py conf/deepseek-lite.conf
```

> **重要**：优先在挂载目录 `/workspace/acr` 运行，而非镜像内置的 `/opt/auto-code-rover/`（版本可能不一致）。

### 5.4 Pilot 任务列表（10 实例）

> **勿与 Lite 300 混淆**：Pilot 仅覆盖 10 题（`conf/pilot_tasks.txt`）。全量 **300** 题 ID 见 [`conf/swe_lite_tasks.txt`](../conf/swe_lite_tasks.txt) 与 [§6.7](#67-swe-bench-lite-300-任务-id-与评测镜像预拉取防漏拉)。按 Pilot 10 题逐题拉镜像**无法**覆盖后续 Lite 300 L3 评测所需镜像。

```
django__django-11001
django__django-11049
django__django-12700
sympy__sympy-13471
sympy__sympy-24152
pytest-dev__pytest-5227
pytest-dev__pytest-7373
astropy__astropy-6938
matplotlib__matplotlib-23314
scikit-learn__scikit-learn-10297
```

### 5.5 单实例调试

```bash
python ACR.py swe-bench \
  --model litellm-generic-deepseek/deepseek-chat \
  --model-temperature 0.2 \
  --conv-round-limit 10 \
  --task-id django__django-11001 \
  --setup-map /opt/SWE-bench/setup_result/setup_map.json \
  --tasks-map /opt/SWE-bench/setup_result/tasks_map.json \
  --output-dir /tmp/acr-pilot \
  --num-processes 1
```

### 5.6 复制结果到主机

因 bind mount，结果通常在 **`experiment/deepseek-lite-pilot/`**（与 `pilot_output/` 二选一同步即可）：

```bash
mkdir -p pilot_output
docker cp pengxm-acr-replicate:/workspace/acr/experiment/deepseek-lite-pilot/. ./pilot_output/
# 或：cp -a experiment/deepseek-lite-pilot/. pilot_output/
```

> 旧文档中的 `/opt/auto-code-rover/experiment/...` 为镜像内置路径；**请以挂载目录 `/workspace/acr` 为准**。

### 5.7 L2 验收

- `pilot_output/applicable_patch/`（或 `experiment/deepseek-lite-pilot/applicable_patch/`）下 **10** 个任务目录，每个含 `extracted_patch_*.diff`
- `no_patch/` 为空
- `predictions_for_swebench.json` 含 **10** 条 SWE-bench 格式记录
- 每个 applicable 目录含 **`cost.json`**，且 `info.log` 含 `Task {instance_id} completed successfully`

**自动化验收**（[`run_pilot_docker.sh`](../scripts/run_pilot_docker.sh) L2 结束后自动执行）：

```bash
python scripts/verify_l2_output.py \
  --expr-dir experiment/deepseek-lite-pilot \
  --expected 10 \
  --tasks-file conf/pilot_tasks.txt
```

Lite 300：`--expected 300 --tasks-file conf/swe_lite_tasks.txt`，并设置对应 `--expr-dir`。

---

## 6. 阶段 C：SWE-bench Docker 自动评测（补全指标）

> **推荐**：使用 [`scripts/run_pilot_eval_incremental.sh`](../scripts/run_pilot_eval_incremental.sh) 逐题评测；每题后仅清理 **`sweb.eval` 评测容器**，**保留**宿主机上已预拉的 **83** 个 `autocoderover/*` 镜像，并同步 `pilot_output/`。流程见 [§6.4](#64-评测流程说明) 与 [§0.1](#01-pilot-推理--评测完整流程)。
>
> **注意**：L3 与 L2 分离。勿在 L2 之后直接运行未设 `SKIP_EVAL=1` 的 `python scripts/run.py conf/deepseek-lite.conf`（会触发 eval 且可能因 `/opt/SWE-bench-docker` 未安装而失败，见 [§9.7](#97-l2l3-衔接与-skip_eval)）。

### 6.1 一键逐题评测（推荐）

```bash
# Linux / Git Bash（Windows PowerShell 见 DOCKER_PILOT_GUIDE.md）
bash scripts/run_pilot_eval_incremental.sh 2>&1 | tee pilot_eval.log
bash scripts/run_pilot_eval_incremental.sh --resume 2>&1 | tee -a pilot_eval.log

# 磁盘极紧张、无预拉镜像时的旧行为（每题删除 autocoderover/*）：
# bash scripts/run_pilot_eval_incremental.sh --prune-preloaded-images
```

脚本自动完成：安装 SWE-bench-docker、挂载 docker.sock、逐题 eval、清理 `sweb.eval` 容器（**默认不删** testbed 镜像）、生成 report、`docker cp`。

### 6.2 手动安装 SWE-bench-docker（可选）

若需手动安装，在容器 `pengxm-acr-replicate` 内：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate auto-code-rover
cd /workspace/acr
bash scripts/setup_swe_bench_docker.sh
```

### 6.3 仅重跑评测（批量，不推荐磁盘紧张时）

若已安装 SWE-bench-docker 且磁盘充足：

```bash
cd /workspace/acr
python scripts/run.py conf/deepseek-lite.conf --eval-only
```

> 注意：`run.py --eval-only` 会 `create_fresh_dir(eval_logs)` 清空日志，无法断点续跑。磁盘紧张请用 6.1。

### 6.4 评测流程说明

```
scripts/run_pilot_eval_incremental.sh   # 宿主机入口
  ├── setup_swe_bench_docker.sh
  ├── run_eval_incremental.py           # 逐题（默认 --prune-preloaded-images 未启用）
  │     ├── run_evaluation.py (×1 instance)
  │     └── prune_eval_images.sh        # 仅 sweb.eval；保留 autocoderover/*（默认）
  ├── generate_report.py                # 全部完成后
  └── docker cp → pilot_output/
```

| 环境变量 / 参数 | 默认 | 说明 |
|-----------------|------|------|
| （无） | 保留 `autocoderover/*` | 83 镜像已预拉时推荐 |
| `--prune-preloaded-images` | — | 每题后删除 `autocoderover/*`（旧版省盘行为） |
| `PRUNE_AUTOCODEROVER_IMAGES=1` | `0` | 与上项等效，供直接调用 `prune_eval_images.sh` 时使用 |

### 6.8 Pilot 推理 + 评测端到端（本机推荐顺序）

与 [§0.1](#01-pilot-推理--评测完整流程) 相同，浓缩为命令链：

```bash
cd /datadisk/pengxm/auto-code-rover
source scripts/source_env.sh

# L2：Agent 推理（10 题，SKIP_EVAL=1）
bash scripts/run_pilot_docker.sh 2>&1 | tee -a pilot_docker_run.log

# L3：Docker 评测（直接复用本地 83 镜像，无需边评边拉/删）
bash scripts/run_pilot_eval_incremental.sh 2>&1 | tee pilot_eval.log

# 验收
ls pilot_output/report/report.json
wc -l pilot_output/eval_logs/*.eval.log 2>/dev/null || ls pilot_output/eval_logs/ | wc -l
```

**耗时粗估**：L2 ~1h（DeepSeek API）；L3 Pilot 10 题 ~30min–2h（镜像已本地，无 pull 等待）。

### 6.5 L3 验收

```bash
ls experiment/deepseek-lite-pilot/report/report.json
ls experiment/deepseek-lite-pilot/stats.json
ls experiment/deepseek-lite-pilot/eval_logs/
```

查看 Resolved 统计：

```bash
python -c "
import json
r = json.load(open('experiment/deepseek-lite-pilot/report/report.json'))
print('resolved:', len(r.get('resolved', [])))
print('total:', r.get('total_num_tasks'))
"
```

### 6.6 评测指标含义

| 状态 | 含义 |
|------|------|
| **Resolved (Yes)** | FAIL_TO_PASS 测试全部通过 |
| **Partially** | 部分测试通过 |
| **No** | 未修复 |

### 6.7 SWE-bench Lite 300 任务 ID 与评测镜像预拉取（防漏拉）

> **目的**：L3 评测在宿主机通过 `docker.sock` 拉/跑 `autocoderover/swe-bench-*` 镜像。若只按 Pilot 10 题或评测到哪拉到哪，极易在 Lite 300 全量评测时**漏拉镜像**、中途失败。本节给出仓库内**权威任务清单**与**83 个唯一镜像**的对应关系。

#### 6.7.1 任务 ID：以 `conf/swe_lite_tasks.txt` 为准

| 文件 | 行数 | 用途 |
|------|------|------|
| [`conf/swe_lite_tasks.txt`](../conf/swe_lite_tasks.txt) | **300** | **官方 SWE-bench Lite 全量 instance ID**；全量 Agent / L3 评测的任务范围 |
| [`conf/pilot_tasks.txt`](../conf/pilot_tasks.txt) | **10** | Pilot 复现子集（[`conf/deepseek-lite.conf`](../conf/deepseek-lite.conf)） |
| [`conf/vanilla-lite.conf`](../conf/vanilla-lite.conf) | — | 论文式全量 Lite 实验，`selected_tasks_file: conf/swe_lite_tasks.txt` |

**快速核对**（宿主机）：

```bash
wc -l conf/swe_lite_tasks.txt conf/pilot_tasks.txt
# 期望：300 与 10
head -3 conf/swe_lite_tasks.txt
```

**勿误用以下来源作为 Lite 300 任务列表**：

| 来源 | 说明 |
|------|------|
| `SWE-bench-docker/evaluations/SWE-bench_Lite_golden/report.json` 的 `generated` | 约 **323** 条，含 sqlfluff、pydicom 等，**不等于** Princeton Lite 300 |
| `processed_data_lite/test/tasks.txt` | 代码中有引用，**仓库未附带** |
| 仅跑过的 Pilot / 消融 `tasks.txt` | 仅为子集，不能推导全量所需镜像 |

#### 6.7.2 镜像数量：300 题 ≠ 300 个镜像

Lite 300 题按 **repo + testbed 版本** 共享 Docker 镜像；scikit-learn 等部分仓库为 **instance 级** 镜像。与 [`conf/swe_lite_tasks.txt`](../conf/swe_lite_tasks.txt) 及实验镜像内 `/opt/SWE-bench/data/swe-bench.json` 对齐后，L3 所需**唯一镜像共 83 个**（namespace：`autocoderover`）。

| 类型 | 数量 | 命名示例 |
|------|------|----------|
| testbed 共享 | 60 | `autocoderover/swe-bench-django_django-testbed:3.2` |
| instance 级 | 23 | `autocoderover/swe-bench-scikit-learn_scikit-learn-instance:scikit-learn__scikit-learn-10297` |

**Pilot 10 题**仅为 Lite 300 的子集，所需约 **9** 个唯一镜像，**全部包含**在上述 83 个中（详见 [SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md §11](SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md)）。

#### 6.7.3 预拉取清单与操作（推荐）

> **本机状态（pengxm，2026-06-01）**：✅ **83/83 已验收**（`swe_lite_pull/missing.txt` 0 行）。详情见 [`SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md` §0](SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md)。

完整步骤见 **[`document/SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md`](SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md)**。仓库内已生成：

| 路径 | 说明 |
|------|------|
| [`swe_lite_pull/autocoderover_lite_83_images.txt`](../swe_lite_pull/autocoderover_lite_83_images.txt) | 83 行，一行一个 `repo:tag` |
| [`swe_lite_pull/run_parallel_pull.sh`](../swe_lite_pull/run_parallel_pull.sh) | 宿主机首轮并行 `docker pull` |
| [`swe_lite_pull/retry_missing.sh`](../swe_lite_pull/retry_missing.sh) | 缺失镜像续拉（无人值守重试） |

**验收命令**（宿主机）：

```bash
cd /datadisk/pengxm/auto-code-rover
grep -v '^#' swe_lite_pull/autocoderover_lite_83_images.txt | while read img; do
  docker image inspect "$img" >/dev/null 2>&1 || echo "$img"
done | tee swe_lite_pull/missing.txt
wc -l swe_lite_pull/missing.txt   # 目标：0
docker images --format '{{.Repository}}:{{.Tag}}' | grep -c '^autocoderover/swe-bench'   # 目标：83
```

镜像落在宿主机 **`/datadisk/docker/data`**（`data-root`），L3 通过 `pengxm-acr-replicate` 挂载的 `docker.sock` 直接使用，**无需**导入实验容器。评测脚本**默认不再删除**这些镜像（见 [§6.4](#64-评测流程说明)）。

#### 6.7.4 常见漏拉原因

| 现象 | 原因 | 预防 |
|------|------|------|
| L3 某题长时间卡在 `Pulling` / 报镜像不存在 | 该题 testbed 镜像未在宿主机 | 按 §6.7.3 预拉 **83** 个镜像后再跑全量 eval |
| 预拉完成后评测仍重复拉同一镜像 | 旧版每题 `prune_eval_images.sh` 删除 `autocoderover/*` | **已修复**：默认保留预拉镜像；勿加 `--prune-preloaded-images` |
| 以为 Pilot 10 已够 | Pilot 仅 9/83 镜像 | 以 `swe_lite_tasks.txt` + `autocoderover_lite_83_images.txt` 为准 |
| 磁盘不足中途失败 | 83 镜像层共享后约 **80–180 GB**（另加 experiment ~57 GB） | `df -h /datadisk`；见 [§12](#12-费用与资源估算) |

#### 6.7.5 与 Pilot L3 的关系

- **Pilot L3**（10 题）：`bash scripts/run_pilot_eval_incremental.sh`；83 镜像已在宿主机，**秒级/分钟级**启动 testbed，无 pull 等待。
- **Lite 300 全量 L3**：不再改 `conf/swe_lite_tasks.txt` 单文件跑 300 题，改为 **12 库分 task 文件 + 分 experiment 目录**（见 §6.7.6）。

#### 6.7.6 Lite 300 分库 pipeline

| 路径 | 说明 |
|------|------|
| [`conf/swe_lite_tasks.txt`](../conf/swe_lite_tasks.txt) | 300 题总表 |
| [`conf/lite300_tasks/<REPO>.txt`](../conf/lite300_tasks/) | 分库 task 列表（`python scripts/split_lite300_tasks.py` 生成） |
| [`conf/deepseek-lite-300.repo.conf.template`](../conf/deepseek-lite-300.repo.conf.template) | 分库 conf 模板 |
| [`conf/generated/deepseek-lite-300-<REPO>.conf`](../conf/generated/) | 运行时生成的 per-repo conf |
| [`scripts/lite300_common.sh`](../scripts/lite300_common.sh) | 12 repo 列表与路径 helper |
| [`scripts/run_lite300_repo.sh`](../scripts/run_lite300_repo.sh) | 单库 L2→repair→verify→L3→Feishu（`--l2-only` 仅 L2） |
| [`scripts/run_lite300_phase1_stagger.sh`](../scripts/run_lite300_phase1_stagger.sh) | Phase1：≤2 库并行 L2（推荐） |
| [`scripts/rerun_lite300_missing.sh`](../scripts/rerun_lite300_missing.sh) | Phase2：补跑缺失题并 merge predictions |
| [`scripts/lite300_status.py`](../scripts/lite300_status.py) | 去重进度表 EXP/PRED/NO/UNPAR/L3 |
| [`document/LITE300_BASELINE_REPRODUCTION_PLAN.md`](LITE300_BASELINE_REPRODUCTION_PLAN.md) | Baseline300 复现计划与 Bug 汇总 |
| [`scripts/start_lite300_tmux.sh`](../scripts/start_lite300_tmux.sh) | tmux 12 窗口（**勿**用于 Baseline 全量，易 12 路齐开） |
| [`scripts/lite300_upload.sh`](../scripts/lite300_upload.sh) | 飞书 Baseline 上传封装 |

**容器内 experiment 目录**：`experiment/deepseek-lite-300/repos/<REPO>/`（conf 中 `id=<REPO>`，`experiment_dir=.../repos`）。

**宿主机 sync / 飞书**：`lite300_output/repos/<REPO>/`；日志 `lite300_logs/${REPO}_pipeline.log`。

**L2 验收**（单库）：

```bash
python scripts/verify_l2_output.py \
  --expr-dir experiment/deepseek-lite-300/repos/django \
  --expected 114 --tasks-file conf/lite300_tasks/django.txt
```

Baseline300 目标见 [`LITE300_BASELINE_REPRODUCTION_PLAN.md`](LITE300_BASELINE_REPRODUCTION_PLAN.md)：须 verify PASS（`no_patch` 为空）后再 L3；补洞用 `REPO=<repo> bash scripts/rerun_lite300_missing.sh`。

**环境**：`conf/.env` 仅需 `DEEPSEEK_API_KEY`（L2 与 patch selection 均用 DeepSeek）。

**断点续跑**：L3 用 `REPO=<repo> bash scripts/run_lite300_repo.sh --resume`（依赖 `eval_progress.json` + `eval_state.json`）。

---

## 7. 阶段 D：消融实验 E0–E4（可选）

### 7.1 实验设计

| ID | 配置文件 | 变量 |
|----|----------|------|
| E0 | `conf/ablation/e0-baseline.conf` | AST + DeepSeek 基线 |
| E1 | `conf/ablation/e1-no-ast.conf` | `enable_text_only_search=true`（仅 search_code） |
| E2 | `conf/ablation/e2-sbfl.conf` | `enable_sbfl=true` |
| E3 | `conf/ablation/e3-validation.conf` | `enable_validation=true` |
| E4 | `conf/ablation/e4-round-limit-3.conf` | `conv_round_limit=3` |

### 7.2 批量运行

**前提**：容器 `pengxm-acr-replicate` 已运行，Pilot 已成功。

```bash
export DEEPSEEK_API_KEY=sk-xxx
bash scripts/run_ablation.sh
```

> conda 路径已统一为 `/root/miniconda3/etc/profile.d/conda.sh`（与 `run_pilot_docker.sh` 一致）。若仍报错，可手动运行单个实验：

```bash
docker exec -e DEEPSEEK_API_KEY pengxm-acr-replicate bash -lc "
  source /root/miniconda3/etc/profile.d/conda.sh
  conda activate auto-code-rover
  cd /workspace/acr
  python scripts/run.py conf/ablation/e0-baseline.conf
"
```

### 7.3 费用预估

5 组 × 10 实例 ≈ **$5–15 USD**（DeepSeek）。

---

## 8. 系统架构速览

```
inference._run_one_task
  ├── [Optional] SBFL 故障定位
  ├── Phase 1: SearchManager.search_iterative
  │     ├── agent_search.generator  → LLM 选择 API / 定位 bug
  │     ├── agent_proxy               → 解析 JSON (API_calls, bug_locations)
  │     └── SearchBackend             → AST 搜索 API（8 个）
  ├── Phase 2: ReviewManager + PatchAgent
  │     ├── [Optional] Docker Validation
  │     └── select_patch
  └── predictions_for_swebench.json → SWE-bench Docker Eval → report.json
```

### Context Retrieval 循环

```
Round N:
  1. LLM 选择搜索 API 或分析已有结果
  2. agent_proxy 解析 JSON
  3. 若 bug_locations 非空且无 API_calls → 进入 Patch Generation
  4. 否则执行 API 调用 → 下一轮
  5. 达到 conv_round_limit → 强制进入 Patch Generation
```

### Agent 暴露的 8 个 AST 搜索 API

| API | 功能 |
|-----|------|
| `search_class(class_name)` | 全局类搜索 |
| `search_class_in_file(class_name, file_name)` | 文件内类搜索 |
| `search_method(method_name)` | 全局方法搜索 |
| `search_method_in_class(method_name, class_name)` | 类内方法搜索 |
| `search_method_in_file(method_name, file_path)` | 文件内方法搜索 |
| `search_code(code_str)` | 全局代码片段搜索 |
| `search_code_in_file(code_str, file_path)` | 文件内代码片段搜索 |
| `get_code_around_line(file_path, line_number, window_size)` | 行号上下文 |

---

## 9. 已知 Bug 与解决方案（完整清单）

### 9.1 Docker 镜像拉取

| 现象 | 原因 | 解决 |
|------|------|------|
| `short read: unexpected EOF` | 网络中断 | 重新 `docker pull`（已下载层会缓存） |
| `registry-1.docker.io:443` 超时 | 国内网络 | 配置 Docker `registry-mirrors` 后重试 |
| 磁盘占满 | 镜像 ~95GB | 预留 ≥120GB；`docker system df` 监控 |

```bash
docker pull yuntongzhang/auto-code-rover:experiment 2>&1 | tee docker_pull.log
```

### 9.2 容器启动与脚本兼容（Linux 服务器通常无此问题）

| 现象 | 原因 | 解决 |
|------|------|------|
| `cannot execute binary file` | 镜像 ENTRYPOINT 冲突 | `docker run --entrypoint ""` |
| `conda.sh: No such file` | 路径错误 | 使用 `/root/miniconda3/etc/profile.d/conda.sh` |
| `/workspace/acr` 不存在 | 挂载路径错误 | 确认 `-v $(pwd):/workspace/acr` |

### 9.3 Agent / LLM 相关

| 现象 | 原因 | 解决 |
|------|------|------|
| `Invalid model name` | 模型名错误 | 使用 `litellm-generic-deepseek/deepseek-chat` |
| Patch 被截断 | token limit 过低 | `export ACR_TOKEN_LIMIT=4096` |
| `Could not extract API calls` | proxy JSON 解析失败 | 查 `search/agent_proxy_*.json`；降 temperature 至 0.0–0.2 |
| `Too many rounds` | 检索未收敛 | 检查 bug_locations 格式；查 `tool_call_layers.json` |
| Generator 无第三次 yield | agent_search.py 截断 | 确认已应用本地修复（见 §3.2） |
| `Please set the OPENAI_KEY` | Review 阶段可选 LLM | **非阻塞**，不影响补丁生成 |
| 429 Rate Limit | 并发过高 | `conf/deepseek-lite.conf` 中 `num_processes` 降至 1–2 |
| backup_model 调用 GPT-4 | 默认配置 | 确认 `app/config.py` 中 backup_model 已改 DeepSeek |

### 9.4 SWE-bench 评测相关

| 现象 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError: /opt/SWE-bench-docker/` | 未安装评测工具 | `bash scripts/run_pilot_eval_incremental.sh` 或 [§6.2](#62-手动安装-swe-bench-docker可选) |
| `setup_map.json` 不存在 | 非 experiment 镜像 | 必须使用 `yuntongzhang/auto-code-rover:experiment` |
| Patch apply 失败 | diff 格式问题 | 不等于 unresolved；查 `eval_logs/*.eval.log` |
| Docker OOM / 超时 | 资源不足 | 增大内存；`test_exec_timeout=300s` |
| 多进程冲突 | 同 testbed 共享代码库 | **禁止**手动多开 `run.py`；用 conf 内 `num_processes` |

### 9.5 消融脚本路径

| 现象 | 原因 | 解决 |
|------|------|------|
| `run_ablation.sh` conda 激活失败 | 旧版脚本用 `/opt/conda` | 已修复为 `/root/miniconda3`；或使用 §7.2 替代命令 |

### 9.6 工程注意事项

- 同一 SWE-bench testbed 版本的任务共享代码库 → 只用 conf 控制并行度
- Python-only AST 索引；测试文件被 `is_test_file()` 排除
- `@cache` 装饰的索引在多进程间不共享（正常行为）
- **切勿**将 API Key 写入文档或提交 git

### 9.7 L2/L3 衔接与 SKIP_EVAL

| 现象 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError: /opt/SWE-bench-docker` | 容器内未安装评测工具，但 `run.py` 在 Agent 后继续跑 eval | L2 用 `SKIP_EVAL=1`；L3 用 `bash scripts/run_pilot_eval_incremental.sh` |
| 宿主机 `export SKIP_EVAL=1` 无效 | `docker exec` 未传入 `-e SKIP_EVAL=1` | 修复 `run_pilot_docker.sh` 的 `run_in_container`，或容器内 `export SKIP_EVAL=1` |
| `pilot_output/` 为空 | `run.py` 在 eval 阶段异常退出，未执行 `docker cp` | 先完成 L2 验收复制；或从 bind mount 的 `experiment/` 拷贝 |
| `Please set the OPENAI_KEY` | Review 阶段可选 OpenAI | **非阻塞**（见 [§9.3](#93-agent--llm-相关)） |

**推荐修复**（`scripts/run_pilot_docker.sh` 中 `run_in_container`）：

```bash
docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT -e ACR_SKIP_DOCKER_CHECK=1 -e SKIP_EVAL=1 \
  "$CONTAINER_NAME" bash -lc "..."
```

---

## 10. 调试检查清单

### 10.1 单元测试

```bash
pytest test/app/agents/test_agent_search.py -v    # 应 4/4 通过
pytest test/app/search/ -v
pytest test/app/agents/test_agent_proxy.py -v
```

### 10.2 前置检查

```bash
python scripts/check_prerequisites.py
```

### 10.3 端到端 artifact 检查

```
[ ] search/tool_call_layers.json 非空
[ ] applicable_patch/*/extracted_patch_*.diff 存在
[ ] predictions_for_swebench.json 格式正确（10 条）
[ ] report/report.json 有 Resolved 统计（L3）
[ ] 各任务 cost.json 可读取
```

### 10.4 日志排查路径

| 问题类型 | 查看文件 |
|----------|----------|
| 检索轮次 | `search/search_round_*.json` |
| API 调用 | `search/tool_call_layers.json` |
| Proxy JSON | `search/agent_proxy_*.json` |
| Patch 生成 | `conv_patch_*.json`、`patch_raw_*.md` |
| 运行日志 | `info.log` |
| 评测 | `eval_logs/*.eval.log` |

---

## 11. 结果目录与成功标志

### 11.1 Pilot 输出结构

```
experiment/deepseek-lite-pilot/    # 容器内路径；主机复制为 pilot_output/
├── predictions_for_swebench.json  # SWE-bench 格式补丁汇总
├── pilot_tasks.txt
├── applicable_patch/
│   └── <instance_id>_<timestamp>/
│       ├── output_0/
│       │   ├── search/              # Context Retrieval 轨迹
│       │   ├── extracted_patch_*.diff
│       │   ├── conv_patch_*.json
│       │   ├── reproducer_0.py
│       │   └── ...
│       ├── info.log
│       ├── meta.json
│       └── cost.json
├── no_patch/                      # 无补丁任务（Pilot 应为空）
├── eval_logs/                     # L3 完成后有内容
├── report/report.json             # L3 完成后生成
└── stats.json                     # L3 完成后生成
```

### 11.2 填写复现报告

完成 L3 后，创建或更新 `document/Replication_Report.md`，建议包含：

| 字段 | 来源 |
|------|------|
| Resolved Rate、Partially、No | `pilot_output/report/report.json` |
| Patch Apply Rate | `applicable_patch/` vs `no_patch/` |
| 平均 Cost/Issue、Latency/Issue | `stats.json`、各任务 `cost.json` |
| 模型与配置 | `conf/deepseek-lite.conf`、`conf/.env` 中模型名（勿写密钥） |
| 消融对比（若运行 E0–E4） | 各 `conf/ablation/*.conf` 对应实验目录 |

---

## 12. 费用与资源估算

| 规模 | 实例数 | 预估费用 (USD) | 预估耗时 |
|------|--------|----------------|----------|
| 轻量 L1 | 1 | ~$0.01 | ~20 秒 |
| Pilot L2 | 10 | $1–3 | ~1–2 小时 |
| 消融 E0–E4 | 50 | $5–15 | ~5–10 小时 |
| SWE-bench Lite 全量 | 300 | $30–80 | 数天 |

DeepSeek-Chat 参考定价：输入 ~$0.27/1M tokens，输出 ~$1.10/1M tokens。

---

## 13. Agent 执行 Checklist（逐步打勾）

> **续跑本机进度**：从 [§0.1](#01-从当前进度继续推荐顺序) 开始；**勿跳过 L2 验收直接跑 L3**。

### 准备阶段

- [x] 确认服务器：Linux、Docker 可用、磁盘 ≥120GB（2026-05-30）
- [x] `conf/.env` 或 export `DEEPSEEK_API_KEY`、`ACR_TOKEN_LIMIT=4096`
- [x] 仓库位于 `/datadisk/pengxm/auto-code-rover`，`git submodule update --init --recursive`
- [x] 确认 §3.2 所列代码修复与复现脚本已存在
- [x] `python scripts/check_prerequisites.py`（容器内已全部 PASS）

### 阶段 A（可选，~5 分钟）

- [x] `pip install -r requirements-pilot-minimal.txt`（可用 `.venv`）
- [x] 运行 local-issue `pilot-divide`（`demo_pilot/output/pilot-divide_2026-05-30_16-11-08/`）
- [x] 确认 L1 artifact 齐全

### 阶段 B（主流程，~1–2 小时）

- [x] `docker pull yuntongzhang/auto-code-rover:experiment`（2026-05-30，`docker_pull.log`）
- [x] `bash scripts/run_pilot_docker.sh` 已执行一轮（见 `pilot_docker_run.log`）
- [ ] 确认 **10/10** applicable patch（[§0.1 步骤 1–3](#01-从当前进度继续推荐顺序)）
- [ ] 结果同步到 `pilot_output/`（`docker cp` 或复制 `experiment/`）

### 阶段 C（补评测，~30min–2h Pilot）

- [x] Lite 300 **83** 镜像预拉并验收（2026-06-01，`missing.txt` 0 行；见 [§6.7.3](#673-预拉取清单与操作推荐)）
- [ ] L2 **10/10** applicable patch + `verify_l2_output.py` PASS（[§5.7](#57-l2-验收)）
- [ ] `bash scripts/run_pilot_eval_incremental.sh`（或 `--resume` / `--report-only`）
- [ ] `pilot_output/eval_state.json` 存在（测试耗时非 0）
- [ ] `pilot_output/report/report.json` 与 `stats.json` 存在
- [ ] `eval_logs/` 有 **10** 条逐题日志
- [ ] 填写 `document/Replication_Report.md`（[§11.2](#112-填写复现报告)）

### 阶段 D（可选消融）

- [ ] `bash scripts/run_ablation.sh` 依次运行 E0–E4
- [ ] 汇总消融结果到 `Replication_Report.md`

---

## 附录：常用命令速查

```bash
cd /datadisk/pengxm/auto-code-rover
source scripts/source_env.sh

# 监测镜像拉取
tail -f docker_pull.log
bash scripts/monitor_docker_pull.sh

# 轻量 L1（.venv 示例）
PYTHONPATH=. .venv/bin/python ACR.py local-issue \
  --model litellm-generic-deepseek/deepseek-chat \
  --task-id pilot-divide --local-repo demo_pilot/sample_project \
  --issue-file demo_pilot/issues/divide_by_zero.md \
  --output-dir demo_pilot/output --num-processes 1 --no-print

# L2 Pilot（Agent only；脚本内应 SKIP_EVAL=1，见 §9.7）
bash scripts/run_pilot_docker.sh 2>&1 | tee pilot_docker_run.log

# Lite 300 镜像验收（已完成 2026-06-01；新环境见 SWE_BENCH_LITE_300_IMAGE_PULL_PLAN.md）
wc -l swe_lite_pull/missing.txt conf/swe_lite_tasks.txt

# L2 Pilot Agent（推理 only）
bash scripts/run_pilot_docker.sh 2>&1 | tee pilot_docker_run.log

# L3 逐题评测（默认保留 autocoderover/* 预拉镜像）
bash scripts/run_pilot_eval_incremental.sh 2>&1 | tee pilot_eval.log
bash scripts/run_pilot_eval_incremental.sh --resume 2>&1 | tee -a pilot_eval.log

# L3 批量评测（仅当 /opt/SWE-bench-docker 已安装且磁盘充足）
docker exec -e SKIP_EVAL=0 pengxm-acr-replicate bash -lc "
  source /root/miniconda3/etc/profile.d/conda.sh && conda activate auto-code-rover &&
  cd /workspace/acr && python scripts/run.py conf/deepseek-lite.conf --eval-only
"

# 消融
bash scripts/run_ablation.sh

# 进入容器
docker exec -it pengxm-acr-replicate bash

# 复制结果（推荐路径）
docker cp pengxm-acr-replicate:/workspace/acr/experiment/deepseek-lite-pilot/. ./pilot_output/
```

---

## 参考文献

```bibtex
@inproceedings{zhang2024autocoderover,
    author = {Zhang, Yuntong and Ruan, Haifeng and Fan, Zhiyu and Roychoudhury, Abhik},
    title = {AutoCodeRover: Autonomous Program Improvement},
    year = {2024},
    booktitle = {ISSTA 2024},
    pages = {1592--1604},
    doi = {10.1145/3650212.3680384}
}
```
