"""汇总环4评分结果 -> 生成 ring4_scored.json -> 跑环5/6 输出载荷。

各靶点评分已在 rfdiffusion/{target}_esm_scores.json 中完成，
此脚本直接汇总（不重跑 MPNN+ESM），然后输出 Top binder + 拼装载。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import Config
from hoyi.utils import save_json, load_json, log
from hoyi import ring5, ring6

cfg = Config()
cfg.set_organism("Acinetobacter baumannii")

TARGETS = ['AB_OmpA', 'AB_BauA', 'AB_CarO', 'AB_Omp33',
           'AB_CsuAB', 'AB_CsuE', 'AB_Ata', 'AB_AdeB',
           'AB_LpxC', 'AB_PmrC']
SKIPPED = ['AB_BasE']

designs_root = os.path.join(cfg.data_dir, "designs", "ab")
all_scored = []
for t in TARGETS:
    j = os.path.join(designs_root, t, "rfdiffusion", f"{t}_esm_scores.json")
    if not os.path.exists(j):
        print(f"[warn] {t}: 无评分文件，跳过", flush=True)
        continue
    recs = json.load(open(j, encoding="utf-8"))
    for r in recs:
        b = {
            "target": r["target"],
            "binder_id": r["binder_id"],
            "sequence": r["sequence"],
            "length": r["length"],
            "score": float(r["composite"]),
            "scorer": "mpnn_esm",
            "esm_composite": r["composite"],
            "pLL": r["pLL"],
            "emb_norm": r["emb_norm"],
        }
        all_scored.append(b)
    print(f"[ring4] {t}: {len(recs)} 条", flush=True)

all_scored.sort(key=lambda x: x["score"], reverse=True)
save_json(cfg.ring4_out, all_scored)
print(f"[ring4] 汇总 {len(all_scored)} 条 -> {cfg.ring4_out}", flush=True)

# 环5
ring5.run(cfg, scored=all_scored, top_n=3, state=None)
# 环6
ring6.run(cfg, top=None, state=None)

# 汇总报告
top = load_json(cfg.ring5_json)
payloads = load_json(cfg.ring6_json)
print("\n=== 最终交付 ===", flush=True)
print(f"Top binders: {len(top)} 条 ({len(set(b['target'] for b in top))} 靶点)", flush=True)
print(f"载荷 payloads: {len(payloads)} 条", flush=True)
print(f"跳过靶点: {SKIPPED}（500aa 大靶点 RFdiffusion 未生成骨架，计算资源限制）", flush=True)
print(f"FASTA: {cfg.ring6_fasta}", flush=True)
print(f"JSON:  {cfg.ring6_json}", flush=True)
