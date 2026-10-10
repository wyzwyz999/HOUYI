#!/usr/bin/env bash

# ===============================
# HOUYI stable runtime environment
# ===============================

export HOUYI_RUN_MODE=native
export HOUYI_BASE_WIN=/root/autodl-tmp/HOUYI_git
export HOUYI_BASE_WSL=/root/autodl-tmp/HOUYI_git

# ---------- RFdiffusion ----------
export HOUYI_ENV_RF=rfdiffusion311
export HOUYI_RFDIFFUSION="/root/autodl-tmp/HOUYI/output model HOUYI/tools/RFdiffusion/scripts/run_inference.py"
export HOUYI_RFDIFFUSION_ROOT="/root/autodl-tmp/HOUYI/output model HOUYI/tools/RFdiffusion"
export HOUYI_RF_CKPT="/root/autodl-tmp/HOUYI/output model HOUYI/tools/RFdiffusion/models/Complex_base_ckpt.pt"

# PyTorch 2.6+ checkpoint compatibility
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

# ---------- ProteinMPNN ----------
export HOUYI_MPNN="/root/autodl-tmp/HOUYI/output model HOUYI/tools/ProteinMPNN/protein_mpnn_run.py"
export HOUYI_MPNN_ROOT="/root/autodl-tmp/HOUYI/output model HOUYI/tools/ProteinMPNN"

# ---------- ColabFold / AF2 ----------
export HOUYI_COLABFOLD_BIN=/root/autodl-tmp/colabfold_env/bin/colabfold_batch
export HOUYI_COLABFOLD_DATA=/root/autodl-tmp/colabfold_data
