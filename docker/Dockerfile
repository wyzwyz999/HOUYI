# HOUYI (后羿) —— 端到端抗菌 binder 设计平台 Docker 镜像
#
# 把整个十环管线（RFdiffusion + ProteinMPNN + Chai-1 + ESM-2）打包进容器，
# 脱离开发机（Windows+WSL2）也能在任何有 NVIDIA GPU 的机器上运行。
#
# 构建：
#   docker build -t hoyi:latest .
# 运行：
#   docker run --gpus all -v <数据目录>:/app/data -v <结果目录>:/app/results hoyi:latest \
#     python pipeline.py --organism "Staphylococcus aureus"
#
# 关键环境变量（运行时可覆盖）：
#   HOUYI_RUN_MODE=container          # 已在 ENV 设好，容器内默认
#   HOUYI_BASE_WIN=/app               # 容器内"根路径"（Linux 视角，无需 Windows 盘符）
#   HOUYI_BASE_WSL=/app
#   HOUYI_RFDIFFUSION_ROOT=/opt/RFdiffusion
#   HOUYI_MPNN_ROOT=/opt/ProteinMPNN
#   HOUYI_CONDA_BASE=/opt/conda/etc/profile.d/conda.sh

# ============ 基础镜像：CUDA 12.1 + Ubuntu 22.04 ============
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# 避免交互式安装提示
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1

# ============ 系统依赖 ============
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ============ Miniconda（提供 conda 环境管理，兼容 backend.conda_base） ============
RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda clean -afy

ENV PATH=/opt/conda/bin:$PATH

# ============ Python 环境（torch 2.5.1 + cu121，对齐开发机） ============
RUN conda create -n protein_design python=3.11 -y \
    && conda run -n protein_design pip install --no-cache-dir \
        torch==2.5.1 \
        torchvision \
        --index-url https://download.pytorch.org/whl/cu121

# ============ Chai-1（结构预测） ============
RUN conda run -n protein_design pip install --no-cache-dir chai-lab==0.6.1

# ============ 生物信息/评分依赖 ============
RUN conda run -n protein_design pip install --no-cache-dir \
    transformers==4.28.0 \
    numpy==1.26.4 \
    pandas \
    biopython \
    gemmi \
    hydra-core

# ============ RFdiffusion（binder 骨架设计） ============
# 官方仓库 + 预训练权重（Complex_base_ckpt）
RUN git clone https://github.com/RosettaCommons/RFdiffusion.git /opt/RFdiffusion \
    && conda run -n protein_design pip install --no-cache-dir -e /opt/RFdiffusion

# RFdiffusion 权重（约 3.2GB，下载到 models/）
RUN mkdir -p /opt/RFdiffusion/models \
    && wget -q http://files.ipd.uw.edu/pub/RFdiffusion/6f5902ac237024bdd0c176cb93063dc4/Complex_base_ckpt.pt \
        -O /opt/RFdiffusion/models/Complex_base_ckpt.pt

# ============ ProteinMPNN（binder 序列设计） ============
RUN git clone https://github.com/dauparas/ProteinMPNN.git /opt/ProteinMPNN

# ============ HOUYI 管线代码 ============
WORKDIR /app
COPY scripts/ /app/scripts/
COPY data/ /app/data/

# ============ 环境变量（容器模式） ============
ENV HOUYI_RUN_MODE=container \
    HOUYI_BASE_WIN=/app \
    HOUYI_BASE_WSL=/app \
    HOUYI_RFDIFFUSION=/opt/RFdiffusion/scripts/run_inference.py \
    HOUYI_RFDIFFUSION_ROOT=/opt/RFdiffusion \
    HOUYI_MPNN=/opt/ProteinMPNN/protein_mpnn_run.py \
    HOUYI_MPNN_ROOT=/opt/ProteinMPNN \
    HOUYI_CONDA_BASE=/opt/conda/etc/profile.d/conda.sh \
    HF_ENDPOINT=https://hf-mirror.com

# ============ 入口 ============
WORKDIR /app/scripts
CMD ["python", "pipeline.py", "--help"]
