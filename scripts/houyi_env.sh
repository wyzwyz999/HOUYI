#!/usr/bin/env bash
# ===============================
# HOUYI stable runtime environment（自定位 + 工具自动探测）
#
# 不再写死任何与账号相关的路径：
#   1) 代码根目录 = 本文件所在目录的上一级
#   2) 工具目录   = 优先 <代码根>/tools，其次旧布局 /root/autodl-tmp/HOUYI/output model HOUYI/tools
#   3) ColabFold  = 优先 <代码根>/colabfold_env，其次 /root/autodl-tmp/colabfold_env
# 因此主账号、子账号可以共用同一份文件。
# ===============================

_HOUYI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HOUYI_RUN_MODE=native
export HOUYI_BASE_WIN="$_HOUYI_ROOT"
export HOUYI_BASE_WSL="$_HOUYI_ROOT"

# ---------- 工具目录自动探测 ----------
_HOUYI_TOOLS=""
for _cand in \
    "$_HOUYI_ROOT/tools" \
    "/root/autodl-tmp/HOUYI/output model HOUYI/tools"
do
    if [ -f "$_cand/RFdiffusion/scripts/run_inference.py" ]; then
        _HOUYI_TOOLS="$_cand"
        break
    fi
done
[ -n "$_HOUYI_TOOLS" ] || _HOUYI_TOOLS="/root/autodl-tmp/HOUYI/output model HOUYI/tools"
export HOUYI_TOOLS_ROOT="$_HOUYI_TOOLS"

# ---------- RFdiffusion ----------
export HOUYI_ENV_RF=rfdiffusion311
export HOUYI_RFDIFFUSION="$_HOUYI_TOOLS/RFdiffusion/scripts/run_inference.py"
export HOUYI_RFDIFFUSION_ROOT="$_HOUYI_TOOLS/RFdiffusion"
export HOUYI_RF_CKPT="$_HOUYI_TOOLS/RFdiffusion/models/Complex_base_ckpt.pt"

# PyTorch 2.6+ checkpoint compatibility
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

# ---------- ProteinMPNN ----------
export HOUYI_MPNN="$_HOUYI_TOOLS/ProteinMPNN/protein_mpnn_run.py"
export HOUYI_MPNN_ROOT="$_HOUYI_TOOLS/ProteinMPNN"

# ---------- ColabFold / AF2 ----------
if [ -x "$_HOUYI_ROOT/colabfold_env/bin/colabfold_batch" ]; then
    export HOUYI_COLABFOLD_BIN="$_HOUYI_ROOT/colabfold_env/bin/colabfold_batch"
else
    export HOUYI_COLABFOLD_BIN=/root/autodl-tmp/colabfold_env/bin/colabfold_batch
fi
if [ -d "$_HOUYI_ROOT/colabfold_data" ]; then
    export HOUYI_COLABFOLD_DATA="$_HOUYI_ROOT/colabfold_data"
else
    export HOUYI_COLABFOLD_DATA=/root/autodl-tmp/colabfold_data
fi

# Ring4: use current base Python instead of obsolete protein_design conda env
export HOUYI_ENV_MPNN=""
export HOUYI_ENV_ESM=""
export HOUYI_PYTHON="/root/miniconda3/bin/python"
