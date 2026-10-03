# HOUYI（后羿）—— 面向任意细菌的抗菌 binder 设计平台

> 一个端到端的、可自动推导靶点并从头设计抗菌蛋白 binder 的开源计算管线。
> 目标是兑现"任意细菌"承诺：给定细菌名，自动检索毒力/耐药/表面靶点，设计纳米注射器载荷。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-GHCR-blue)](https://github.com/YOUR_ORG/hoyi/pkgs/container/hoyi)

---

## 快速开始（三种方式任选）

### 方式 1：Docker 一行跑（推荐，无需配环境）

```bash
# 拉镜像（自动构建发布在 GHCR）
docker pull ghcr.io/YOUR_ORG/hoyi:latest

# 跑金葡菌（预置知识库）
docker run --gpus all -v $(pwd)/data:/app/data -v $(pwd)/results:/app/results \
  ghcr.io/YOUR_ORG/hoyi:latest python pipeline.py --organism "Staphylococcus aureus"

# 跑任意新细菌（自动检索兜底，无需预置库）
docker run --gpus all -v $(pwd)/data:/app/data -v $(pwd)/results:/app/results \
  ghcr.io/YOUR_ORG/hoyi:latest python pipeline.py --organism "Pseudomonas aeruginosa"
```

### 方式 2：无 GPU 的 CPU 体验（dry-run / 轻量环）

```bash
# 环1 靶点分析 + 环2 结构预测的 dry-run（不落盘、不依赖 GPU）
docker run --rm ghcr.io/YOUR_ORG/hoyi:latest \
  python pipeline.py --organism "Pseudomonas aeruginosa" --start 1 --stop 2 --dry-run
```

### 方式 3：本地源码运行（开发者）

```bash
git clone https://github.com/YOUR_ORG/hoyi.git
cd hoyi/scripts
python pipeline.py --organism "Staphylococcus aureus" --dry-run
```

---

## 十环管线

| 环 | 名称 | 作用 | 依赖 GPU |
|----|------|------|---------|
| 1 | 靶点分析 | 从知识库/自动检索推导毒力/耐药/表面靶点 | ✗ |
| 2 | 结构预测 | 下载 PDB 或 Chai-1 从头预测 | ✓ |
| 3 | Binder 设计 | RFdiffusion 生成 binder 骨架 | ✓ |
| 4 | 评分排序 | ProteinMPNN 序列设计 + ESM-2 折叠评分 | ✓ |
| 5 | 输出 binder | Top binder 序列输出 | ✗ |
| 6 | 拼装载 | Pdp1_NTD-linker-binder 载荷组装 | ✗ |
| 7 | 尾纤维靶点 | 尾纤维靶点打分排序 | ✗ |
| 8 | 尾纤维 binder | 尾纤维 binder/结构域筛选 | ✓ |
| 9 | 重编程 pvc13 | 重编程注射器尾纤维 | ✗ |
| 10 | 注射器总装 | 纳米注射器规格生成 | ✗ |

---

## 核心特性

- **任意细菌兜底**：无预置库的细菌自动经 UniProt 检索 reviewed 蛋白 → 强信号关键词分类 → 排除转录调控因子 → 产出候选靶点（`auto_target_discovery.py`）
- **执行后端抽象**：`wsl`/`container`/`native` 三种运行模式一键切换（`HOUYI_RUN_MODE`），脱离单一开发机
- **真断点续跑**：每环产物独立落盘，失败可续
- **重试机制**：Chai-1 预测带重试，对抗瞬时 CUDA OOM

---

## 已知边界

- **GPU 显存**：Chai-1 单链预测在 16GiB 显存上，≤500aa 能跑通，>600aa 会 OOM。长序列需结构域分割或更大显存 GPU（A100 40G）。
- **权重下载**：首次运行需联网下载 RFdiffusion 权重（~3.2GB）和 ESM-2 模型（~2.5GB）。

---

## 目录结构

```
├── scripts/          # 管线代码（hoyi/ 包 + pipeline.py 入口）
│   └── hoyi/         # 十环模块 + backend 抽象
├── data/             # 知识库/抗原/PDB（预置金葡菌/结核等）
├── docker/           # Dockerfile + compose + 文档
├── .github/          # CI 自动构建发布镜像
└── LICENSE
```

## 引用

若使用本项目，请引用（待发表）。依赖：RFdiffusion、ProteinMPNN、Chai-1、ESM-2。

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。
