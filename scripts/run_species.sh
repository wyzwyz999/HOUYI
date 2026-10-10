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
