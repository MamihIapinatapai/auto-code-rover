# Spec-Parser 版本复现清单

> 用途：回滚到指定代码版本或实验配置后，尽量一键恢复运行环境并冒烟/跑评测。  
> 详细服务器环境见 [SERVER_REPLICATION_GUIDE.md](SERVER_REPLICATION_GUIDE.md)。

## 环境前置（所有版本通用）

```bash
cd /datadisk/pengxm/auto-code-rover   # 或你的 clone 路径
conda activate auto-code-rover
test -f conf/.env || cp conf/.env.example conf/.env   # 填入 DEEPSEEK_API_KEY
docker ps --format '{{.Names}}' | grep -qx pengxm-acr-replicate   # L2/L3 需要
bash scripts/setup_swe_bench_docker.sh   # L3 Docker 评测需要
```

---

## 代码版本 Tags

### spec-parser-v2-foundation（`1d21e2fa`，M1–M5 基础架构）

```bash
git fetch origin --tags && git checkout spec-parser-v2-foundation
git submodule update --init --recursive
pip install -r requirements-pilot-minimal.txt
PYTHONPATH=. python scripts/eval_spec_parser.py --help
```

### spec-parser-m6（`692adca2`，M6 AC marker 解析）

```bash
git checkout spec-parser-m6
git submodule update --init --recursive
PYTHONPATH=. python -m pytest test/app/spec_parser/test_ac_markers.py -q
```

### spec-parser-m7（M7 script_linter + calibration_gate）

```bash
git checkout spec-parser-m7
git submodule update --init --recursive
patch -p1 -d SWE-bench-docker < patches/swe-bench-docker-host-acr-root.patch
PYTHONPATH=. python -m pytest test/app/spec_parser/ -q
```

> **L3 嵌套 Docker 说明**：补丁中 `swebench_docker/run_docker.py` 的 `HOST_ACR_ROOT` 映射是容器内跑 L3 评测的关键；运行前可 `export HOST_ACR_ROOT=/datadisk/pengxm/auto-code-rover`。

---

## 运行配置 Profiles（叠在 M7 代码上）

以下配置不是独立 Git 分支，而是在 `spec-parser-m7` 代码上切换 conf + 脚本。

### ver1 — SymPy 全量 L2→L3

- **配置**：`conf/deepseek-lite-300-ver1.sympy.conf`
- **入口**：`scripts/run_sympy_ver1_eval.sh`

```bash
git checkout spec-parser-m7
patch -p1 -d SWE-bench-docker < patches/swe-bench-docker-host-acr-root.patch
set -a && source conf/.env && set +a
export SYSTEM_VERSION=ver1 ACR_SEMANTIC_INJECTION_VER1=1 HOST_ACR_ROOT=$PWD
bash scripts/run_sympy_ver1_eval.sh
```

### ver1.1 — SymPy 逐实例流水线（L2 校验 → L3 → Feishu）

- **配置**：`conf/deepseek-lite-300-ver1.1.sympy.conf`
- **入口**：`scripts/start_ver1.1_sympy_instance_pipeline.sh`

```bash
git checkout spec-parser-m7
patch -p1 -d SWE-bench-docker < patches/swe-bench-docker-host-acr-root.patch
set -a && source conf/.env && set +a
export HOST_ACR_ROOT=$PWD
bash scripts/start_ver1.1_sympy_instance_pipeline.sh
```

> 输出目录 `lite300_output_ver1.1/` 已被 `.gitignore` 排除，结果保留在本地磁盘。

### spec_parser_ver1 — 五探针冒烟（Gate R0）

- **配置**：`conf/deepseek-lite-300-spec_parser_ver1.sympy.conf`
- **入口**：`scripts/start_spec_parser_ver1_probe.sh`

```bash
git checkout spec-parser-m7
set -a && source conf/.env && set +a
bash scripts/start_spec_parser_ver1_probe.sh sympy__sympy-12481
```

---

## 版本对照表

| Tag / Profile | 类型 | 说明 |
|---------------|------|------|
| `spec-parser-v2-foundation` | 代码 tag | M1–M5 模块骨架 |
| `spec-parser-m6` | 代码 tag | 统一 AC marker |
| `spec-parser-m7` | 代码 tag | script_linter、calibration_gate 等 |
| ver1 | 运行 profile | ver1 语义注入 + SymPy lite300 |
| ver1.1 | 运行 profile | ver1.1 机械流水线 |
| spec_parser_ver1 | 运行 profile | spec_parser 五探针 Gate R0 |

## 大体积产物说明

评测输出（`lite300_output*`、`lite300_logs/`、`*.log`）不入 Git。回滚代码后历史跑分需从本地备份或网盘恢复，或重新跑评测。
