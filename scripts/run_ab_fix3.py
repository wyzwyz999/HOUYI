"""补跑 LpxC/PmrC/BasE 三个靶点的环3（RFdiffusion binder 设计）。
ring2 已修正为 chai1_predicted。每靶点间重启 WSL。
用法：python run_ab_fix3.py [num_designs]
"""
import sys, os, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import run_pipeline, Config

num_designs = int(sys.argv[1]) if len(sys.argv) > 1 else 16

targets_order = ['AB_LpxC', 'AB_PmrC', 'AB_BasE']

for tid in targets_order:
    print(f"\n{'='*60}\n=== 靶点 {tid} ===\n{'='*60}", flush=True)
    subprocess.run(["wsl", "--shutdown"], capture_output=True)
    time.sleep(12)

    cfg = Config()
    try:
        data = run_pipeline(
            cfg, organism="Acinetobacter baumannii",
            targets=[tid], start=3, stop=3,
            dry_run=False, num_designs=num_designs,
        )
        ring3 = data.get("rings", {}).get("3", {})
        print(f"[{tid}] 环3: {ring3.get('status')} - {ring3.get('info')}", flush=True)
    except Exception as e:
        print(f"[{tid}] 异常: {e}", flush=True)

subprocess.run(["wsl", "--shutdown"], capture_output=True)
print("\n=== 补跑 3 靶点完成 ===", flush=True)
