"""最终输出：去重后生成干净的 Top binder + 载荷。

去重规则：每靶点内，同一骨架编号（binder_id 的 __N 部分）只保留 composite 最高的一条，
避免同骨架多温度采样序列霸占 Top3。每靶点取不同骨架 Top3。

产出：top_binders.fasta/json + payloads.fasta/json（覆盖环5/6 默认产物）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import Config
from hoyi.utils import save_json
from hoyi.ring6 import PDP1_NTD, LINKER, build_payload

cfg = Config()
cfg.set_organism("Acinetobacter baumannii")

scored = json.load(open(cfg.ring4_out, encoding="utf-8"))

# 按靶点分组，组内按骨架去重（保留最高 composite）
by_target = {}
for b in scored:
    by_target.setdefault(b["target"], []).append(b)

top = []
for t, items in by_target.items():
    # 骨架去重：binder_id 形如 AB_CarO__5_B -> 骨架 5
    best_per_scaffold = {}
    for b in items:
        bid = b["binder_id"]
        parts = bid.split("__")
        scaff = parts[1].split("_")[0] if len(parts) > 1 else bid
        if scaff not in best_per_scaffold or b["score"] > best_per_scaffold[scaff]["score"]:
            best_per_scaffold[scaff] = b
    # 按 score 降序取 Top3 不同骨架
    unique = sorted(best_per_scaffold.values(), key=lambda x: x["score"], reverse=True)
    top.extend(unique[:3])

# 全局按 score 降序
top.sort(key=lambda x: x["score"], reverse=True)

# 输出 Top binder FASTA + JSON
save_json(cfg.ring5_json, top)
with open(cfg.ring5_fasta, "w", encoding="utf-8") as f:
    for b in top:
        bid = b["binder_id"].split(" len=")[0]
        f.write(f">{b['target']}|{bid} len={b['length']}\n{b['sequence']}\n")

# 拼装载
payloads = []
for b in top:
    payload_seq = build_payload(b["sequence"])
    p = dict(b)
    p["payload_sequence"] = payload_seq
    p["payload_length"] = len(payload_seq)
    p["pdp1_ntd"] = PDP1_NTD
    p["linker"] = LINKER
    p["binder_sequence"] = b["sequence"]
    payloads.append(p)

save_json(cfg.ring6_json, payloads)
with open(cfg.ring6_fasta, "w", encoding="utf-8") as f:
    for p in payloads:
        bid = p["binder_id"].split(" len=")[0]
        f.write(f">{p['target']}|{bid} len={p['payload_length']} payload\n{p['payload_sequence']}\n")

# 汇总
print(f"Top binders: {len(top)} 条 / {len(by_target)} 靶点", flush=True)
print(f"载荷: {len(payloads)} 条", flush=True)
print(f"跳过: AB_BasE（500aa 大靶点 RFdiffusion 未生成骨架）", flush=True)
for t, items in sorted(by_target.items(), key=lambda x: -max(b['score'] for b in x[1])):
    n_top = len([b for b in top if b['target'] == t])
    best = max(b['score'] for b in items)
    print(f"  {t:12s} {n_top} 条 Top / {len(items)} 条候选 / best composite={best:.0f}", flush=True)
print(f"\nFASTA: {cfg.ring6_fasta}", flush=True)
print(f"JSON:  {cfg.ring6_json}", flush=True)
