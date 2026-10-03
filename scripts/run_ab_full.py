"""鲍曼不动杆菌全量载荷设计 — 11 靶点端到端。

num_designs=16（折中：快速出全谱 + 可后续增量补充）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import run_pipeline, Config

cfg = Config()
data = run_pipeline(
    cfg,
    organism="Acinetobacter baumannii",
    start=3, stop=6,
    dry_run=False,
    scorer="mpnn_esm",
    top_n=3,
    num_designs=16,
)
print("=== 管线完成 ===")
for k, v in data.get("rings", {}).items():
    print(f"环{k}: {v.get('status')} - {v.get('info')}")
