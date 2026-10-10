#!/usr/bin/env bash
set -euo pipefail

cd /root/autodl-tmp/HOUYI_git
source scripts/houyi_env.sh

if [ $# -lt 1 ]; then
    echo '用法: bash scripts/run_species.sh "Pseudomonas aeruginosa"'
    exit 1
fi

ORGANISM="$1"

echo "=========================================="
echo "HOUYI 一键泛化设计"
echo "Organism: $ORGANISM"
echo "=========================================="

echo
echo "[1/5] 检查 RFdiffusion..."
test -f "$HOUYI_RFDIFFUSION" || {
    echo "ERROR: RFdiffusion script not found"
    exit 1
}

test -f "$HOUYI_RF_CKPT" || {
    echo "ERROR: RFdiffusion checkpoint not found"
    exit 1
}

echo "RFdiffusion OK"

echo
echo "[2/5] 检查 ProteinMPNN..."
test -f "$HOUYI_MPNN" || {
    echo "ERROR: ProteinMPNN not found"
    exit 1
}

echo "ProteinMPNN OK"

echo
echo "[3/5] 检查 ColabFold / AF2..."
test -x "$HOUYI_COLABFOLD_BIN" || {
    echo "ERROR: colabfold_batch not found"
    exit 1
}

test -d "$HOUYI_COLABFOLD_DATA" || {
    echo "ERROR: ColabFold parameter directory not found"
    exit 1
}

echo "ColabFold OK"

echo
echo "[4/5] 检查 GPU..."
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("CUDA:", torch.version.cuda)
print("GPU available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    raise SystemExit("ERROR: CUDA GPU unavailable")
PY

echo
echo
echo "===== Ring4 / ESM2 preflight ====="

PYTHON_BIN="${HOUYI_PYTHON:-/root/miniconda3/bin/python}"

test -x "$PYTHON_BIN" || {
    echo "PRECHECK FAILED: Python不存在: $PYTHON_BIN"
    exit 1
}

test -f "$HOUYI_MPNN" || {
    echo "PRECHECK FAILED: ProteinMPNN脚本不存在: $HOUYI_MPNN"
    exit 1
}

"$PYTHON_BIN" - <<'PYCHECK'
import sys
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForMaskedLM

print("Python:", sys.executable)
print("torch:", torch.__version__)
print("transformers:", transformers.__version__)
print("Ring4 imports: OK")

if not torch.cuda.is_available():
    raise SystemExit("PRECHECK FAILED: Ring4 CUDA unavailable")

print("Ring4 GPU:", torch.cuda.get_device_name(0))
PYCHECK

echo "Ring4 / ESM2 OK"
echo

echo "[5/5] 启动完整 HOUYI Ring1 -> Ring10"
echo

python scripts/pipeline.py \
    --organism "$ORGANISM" \
    --start 1 \
    --stop 10 \
    --af2 \
    --af2-top-k 3 \
    --af2-models 5 \
    --af2-seeds 3 \
    --af2-recycles 6 \
    --verbose

echo
echo "=========================================="
echo "HOUYI completed: $ORGANISM"
echo "Results:"
echo "results/by_organism/"
echo "=========================================="
