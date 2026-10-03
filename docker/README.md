# HOUYI 容器化迁移（路线 A）

把 HOUYI 十环管线从「Windows + WSL2 开发机」迁移到「Docker 容器」，脱离单一机器运行。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  Docker 容器（nvidia/cuda:12.1 + Ubuntu 22.04）          │
│                                                         │
│  /opt/conda/envs/protein_design  ← torch 2.5.1+cu121    │
│    ├─ chai-lab 0.6.1           ← 环2 结构预测            │
│    ├─ transformers 4.28        ← 环4 ESM-2 评分          │
│    └─ hydra-core               ← RFdiffusion 依赖        │
│  /opt/RFdiffusion  ← 环3 binder 骨架设计（含权重 3.2GB）  │
│  /opt/ProteinMPNN  ← 环3 binder 序列设计                 │
│  /app/scripts      ← HOUYI 管线代码（backend 抽象）       │
│  /app/data         ← 知识库/抗原（卷挂载）                │
│  /app/results      ← 十环产物（卷挂载）                   │
└─────────────────────────────────────────────────────────┘
```

## 关键改造：执行后端抽象（backend.py）

原代码到处硬编码 `wsl -e`、`replace("H:", "/mnt/h")`、`/home/zhaoxx/...`。
新架构引入 `hoyi/backend.py` 的 `ExecutionBackend`，统一三种运行模式：

| 模式 | 命令执行 | 路径转换 | 触发 |
|------|---------|---------|------|
| `wsl` | `wsl -e bash -lc` | `H:\a` → `/mnt/h/a` | 默认（开发机） |
| `container` | `bash -lc` | 透传 | `HOUYI_RUN_MODE=container` |
| `native` | `bash -lc` | 透传 | 本机 Linux |

所有重计算模块（structure_predictor / rf_designer / mpnn_esm_scorer）已改用它，
**换部署环境只需改环境变量，代码零改动**。

## 构建

```bash
cd H:\eazyclaw\saved\MASA3
docker compose -f docker/docker-compose.yml build
```

首次构建会下载：
- RFdiffusion 权重（~3.2GB）
- Chai-1 + torch + transformers 等 pip 包（~5GB）
- Miniconda 基础环境

## 运行

```bash
# 完整跑金葡菌（已有知识库）
docker compose -f docker/docker-compose.yml run --rm hoyi \
  python pipeline.py --organism "Staphylococcus aureus"

# 任意新细菌（自动检索兜底）
docker compose -f docker/docker-compose.yml run --rm hoyi \
  python pipeline.py --organism "Pseudomonas aeruginosa"

# 预览（不落地）
docker compose -f docker/docker-compose.yml run --rm hoyi \
  python pipeline.py --organism "Pseudomonas aeruginosa" --dry-run
```

## 环境变量清单

| 变量 | 默认（开发机） | 容器值 | 作用 |
|------|--------------|--------|------|
| `HOUYI_RUN_MODE` | `wsl` | `container` | 执行后端 |
| `HOUYI_BASE_WIN` | `H:\eazyclaw\saved\MASA3` | `/app` | 根路径 |
| `HOUYI_BASE_WSL` | `/mnt/h/eazyclaw/saved/MASA3` | `/app` | 执行端根路径 |
| `HOUYI_RFDIFFUSION_ROOT` | `/home/zhaoxx/RFdiffusion` | `/opt/RFdiffusion` | RFdiffusion 根 |
| `HOUYI_MPNN_ROOT` | `/home/zhaoxx/ProteinMPNN` | `/opt/ProteinMPNN` | ProteinMPNN 根 |
| `HOUYI_CONDA_BASE` | `~/miniforge3/.../conda.sh` | `/opt/conda/.../conda.sh` | conda |
| `HOUYI_CHAI1_RETRIES` | `2` | `2` | Chai-1 重试次数 |

## 已知边界

1. **GPU 显存**：Chai-1 单链预测在 16GiB 显存上，≤500aa 能跑通，>600aa 会 CUDA OOM。
   长序列靶点需结构域分割或更大显存 GPU（如 A100 40G）。
2. **首次权重下载**：RFdiffusion 权重从 ipd.uw.edu 下载，若网络不通需预置权重卷挂载。
3. **HF 模型**：ESM-2 650M 从 HF 下载（已设 `HF_ENDPOINT=hf-mirror.com` 加速国内下载）。

## 验证清单

- [ ] `docker compose build` 成功（无报错）
- [ ] `docker run --gpus all hoyi nvidia-smi` 能识别 GPU
- [ ] 环1-2 dry-run 通过（靶点分析 + 结构预测）
- [ ] 环3 RFdiffusion 真实生成 binder 骨架
- [ ] 环4 MPNN+ESM 评分跑通
