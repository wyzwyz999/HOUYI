#!/bin/bash
# ============================================================
# HOUYI (后羿) —— Mtb binder 从头设计 —— RFdiffusion 批量（残基号已修正）
# 用 protein_design 环境，contig 用实际残基号（探测自 PDB）
# ============================================================
set -e
source /home/zhaoxx/miniforge3/etc/profile.d/conda.sh
conda activate protein_design

BASE=/mnt/h/eazyclaw/saved/MASA3/data/designs/mtb
PDB_DIR=/mnt/h/eazyclaw/saved/MASA3/data/pdbs/mtb
RFDIFF_DIR=/home/zhaoxx/RFdiffusion
NUM_DESIGNS=32
BINDER_MIN=40
BINDER_MAX=90

# TARGET:PDB:CHAIN:START:END  (残基号已从 PDB 实际探测)
# ESAT6 = 3FAV链B(10-81), CFP10 = 3FAV链A(11-84)
TARGETS=(
  "MTB_KasA:4C70:A:2:416"
  "MTB_InhA:1BVR:A:2:269"
  "MTB_Ag85A:1SFR:A:0:287"
  "MTB_Ag85B:1F0P:A:2:285"
  "MTB_Ag85C:1DQY:A:0:282"
  "MTB_ESAT6:3FAV:B:10:81"
  "MTB_CFP10:3FAV:A:11:84"
)

rm -f /home/zhaoxx/RFdiffusion/schedules/T_50_omega_1000_min_sigma_0_02_min_b_1_5_max_b_2_5_schedule_linear.pkl

for entry in "${TARGETS[@]}"; do
  IFS=':' read -r target_id pdb_id chain start_res end_res <<< "$entry"
  OUTDIR=$BASE/$target_id/rfdiffusion
  mkdir -p "$OUTDIR"
  PDB=$PDB_DIR/${pdb_id}.pdb
  LENGTH=$((end_res - start_res + 1))

  EXISTING=$(ls "$OUTDIR"/*.pdb 2>/dev/null | grep -v traj | wc -l)
  NEED=$((NUM_DESIGNS - EXISTING))
  if [ "$NEED" -le 0 ]; then
    echo "[$target_id] 已有 $EXISTING 骨架，跳过"
    continue
  fi

  echo ""
  echo "===== [$target_id] PDB=$pdb_id chain=$chain res=$start_res-$end_res (${LENGTH}aa) need=$NEED ====="
  cd "$RFDIFF_DIR"
  python scripts/run_inference.py \
    inference.output_prefix=$OUTDIR/${target_id} \
    inference.input_pdb=$PDB \
    "contigmap.contigs=[${chain}${start_res}-${end_res}/0 ${BINDER_MIN}-${BINDER_MAX}]" \
    inference.num_designs=$NEED \
    denoiser.noise_scale_ca=0.5 \
    denoiser.noise_scale_frame=0.5 \
    diffuser.T=50 \
    2>&1 | tail -5

  N_NEW=$(ls "$OUTDIR"/*.pdb 2>/dev/null | grep -v traj | wc -l)
  echo "  [$target_id] 生成 $N_NEW 骨架"
done

echo ""
echo "======== 全部 RFdiffusion 骨架生成完成 ========"
