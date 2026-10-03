"""环4-6 收尾：对已有 RFdiffusion 骨架的靶点做 MPNN+ESM 评分 -> 输出 Top binder -> 拼装载。

- 重建 ring3_designed.json（全量 9 个有骨架靶点）
- 环4 评分（mpnn_esm）
- 环5 输出 Top3 binder
- 环6 拼装 Pdp1_NTD-linker-binder 载荷

用法：python run_ab_finalize.py
"""
import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import Config, run_pipeline

# 有骨架的靶点（含部分骨架的，仍进入评分出 Top3）
# BasE 无骨架，跳过（RFdiffusion 未生成）
TARGETS_WITH_SCAFFOLDS = [
    'AB_OmpA', 'AB_BauA', 'AB_CarO', 'AB_Omp33',
    'AB_CsuAB', 'AB_CsuE', 'AB_Ata', 'AB_AdeB',
    'AB_LpxC', 'AB_PmrC',
]
SKIPPED = ['AB_BasE']  # 无骨架

cfg = Config()
cfg.set_organism("Acinetobacter baumannii")

# 1. 重建 ring3_designed.json（全量汇总）
designs_root = os.path.join(cfg.data_dir, "designs", "ab")
ring3 = {}
for t in TARGETS_WITH_SCAFFOLDS:
    out_dir = os.path.join(designs_root, t, "rfdiffusion")
    n = 0
    if os.path.isdir(out_dir):
        n = len([f for f in os.listdir(out_dir) if f.endswith('.pdb') and 'traj' not in f and '_B' not in f and 'cont' not in f])
    ring3[t] = {"n_binders": n, "source": "rfdiffusion", "out_dir": out_dir}
    print(f"[ring3] {t}: {n} 骨架", flush=True)
for t in SKIPPED:
    ring3[t] = {"n_binders": 0, "source": "no_structure",
                "note": "500aa 大靶点 RFdiffusion 未生成骨架，计算资源限制跳过"}
    print(f"[ring3] {t}: 跳过（无骨架）", flush=True)

import json as _json
with open(cfg.ring3_out, "w", encoding="utf-8") as f:
    _json.dump(ring3, f, ensure_ascii=False, indent=2)
print(f"[ring3] 已重建 {cfg.ring3_out}", flush=True)

# 2. 跑环4-6
data = run_pipeline(
    cfg, organism="Acinetobacter baumannii",
    targets=TARGETS_WITH_SCAFFOLDS,
    start=4, stop=6, dry_run=False,
    scorer="mpnn_esm", top_n=3,
)
print("\n=== 环4-6 完成 ===", flush=True)
for k, v in data.get("rings", {}).items():
    print(f"环{k}: {v.get('status')} - {v.get('info')}", flush=True)
