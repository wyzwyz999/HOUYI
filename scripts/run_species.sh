#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source scripts/houyi_env.sh

# 让脚本在非交互 shell（cron / 批量 / ssh 直接调用）下也能找到 python，
# 否则 `python: command not found` 会在 GPU 检查那一步就退出。
PYTHON_BIN="${HOUYI_PYTHON:-/root/miniconda3/bin/python}"
export PATH="/root/miniconda3/bin:$PATH"

if [ $# -lt 1 ]; then
    echo '用法: bash scripts/run_species.sh "Pseudomonas aeruginosa" [额外参数，原样透传给 pipeline.py，如 --allow-unreviewed / --targets sodA]'
    exit 1
fi

ORGANISM="$1"
shift

# ---------------------------------------------------------------------------
# UniProt 可用性预检（2026-10-30）
# 环1 和环7 都依赖 rest.uniprot.org；EBI 偶尔返回 503 或直接超时。
# 与其白跑（环1 失败 → 整条 FAILED），不如开跑前 15 秒确认一下。
# 需要跳过检查：HOUYI_SKIP_NETCHECK=1
# ---------------------------------------------------------------------------
if [ "${HOUYI_SKIP_NETCHECK:-0}" != "1" ]; then
    # 必须用“真实查询形态”：EBI 出故障时，通用查询可能 200，
    # 但 organism_name 检索会 500（2026-10-30 实际发生过）。
    _code=$(curl -sS -m 20 -G -o /dev/null -w '%{http_code}' \
        --data-urlencode "query=organism_name:\"$ORGANISM\" AND reviewed:true" \
        --data 'size=1&format=list' \
        'https://rest.uniprot.org/uniprotkb/search' 2>/dev/null || echo 000)
    if [ "$_code" != "200" ]; then
        echo "=========================================="
        echo "ERROR: UniProt 按物种检索不可用（HTTP ${_code:-000}）"
        echo "  测试查询: organism_name=\"$ORGANISM\" AND reviewed:true"
        echo "  环1/环7 都用这条路径，现在开跑必然失败。"
        echo "  处理：等 5-30 分钟重试，或换一台实例；"
        echo "        确认要跳过检查：HOUYI_SKIP_NETCHECK=1 bash scripts/run_species.sh ..."
        echo "=========================================="
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# 质量策略（2026-10-24）：reviewed 优先，失败才降级
#
# --allow-unreviewed 的语义是"先查 reviewed（Swiss-Prot 人工审阅），只有查不到
# 可用靶点时才回落 TrEMBL"，因此默认开启不会降低正常物种的结果质量：
#   - reviewed 能出靶点 -> 全程不碰 TrEMBL，provenance=reviewed
#   - reviewed 0 条 / 有记录但全被筛掉 -> 自动回落 TrEMBL，provenance=TrEMBL
#
# 需要严格模式（任何情况都不降级）时：
#   HOUYI_STRICT_REVIEWED=1 bash scripts/run_species.sh "菌名"
# ---------------------------------------------------------------------------
AUTO_REVIEW_FALLBACK=()
if [ "${HOUYI_STRICT_REVIEWED:-0}" != "1" ]; then
    AUTO_REVIEW_FALLBACK=(--allow-unreviewed)
fi

echo "=========================================="
echo "HOUYI 一键泛化设计"
echo "Organism: $ORGANISM"
if [ "${HOUYI_STRICT_REVIEWED:-0}" = "1" ]; then
    echo "质量策略: 严格 reviewed（不降级）"
else
    echo "质量策略: reviewed 优先，检索不到靶点时自动回落 TrEMBL"
fi
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

"$PYTHON_BIN" scripts/pipeline.py \
    --organism "$ORGANISM" \
    --start 1 \
    --stop 10 \
    --af2 \
    --af2-top-k 3 \
    --af2-models 5 \
    --af2-seeds 3 \
    --af2-recycles 6 \
    --verbose \
    "${AUTO_REVIEW_FALLBACK[@]}" \
    "$@"

echo
echo "=========================================="
echo "HOUYI completed: $ORGANISM"
echo "Results:"
echo "results/by_organism/"
echo "=========================================="
