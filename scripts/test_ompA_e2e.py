"""单靶点端到端验证：OmpA(4G88) 全链路 RFdiffusion -> MPNN -> ESM -> 拼装载。"""
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
)
for k, v in data.get("rings", {}).items():
    print(f"环{k}: {v.get('status')} - {v.get('info')}")
