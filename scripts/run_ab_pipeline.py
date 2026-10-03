"""鲍曼不动杆菌端到端载荷设计 — 启动脚本。

后羿(HOUYI)模型六环管线：输入 Acinetobacter baumannii → 输出载荷序列。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import run_pipeline, Config

cfg = Config()
data = run_pipeline(
    cfg,
    organism="Acinetobacter baumannii",
    start=1,
    stop=6,
    dry_run=False,
    scorer="mpnn_esm",
    top_n=3,
)
print("=== 管线完成 ===")
print("rings:")
for k, v in data.get("rings", {}).items():
    print(f"  环{k}: {v.get('status')} - {v.get('info')}")
