"""稳健分批运行：每靶点间重启 WSL 释放内存，避免长时间 RFdiffusion 压垮 WSL。

用法：python run_ab_batched.py [num_designs]
默认 num_designs=16，逐靶点跑 ring3（RFdiffusion），每靶点后 wsl --shutdown。
"""
import sys, os, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import run_pipeline, Config

num_designs = int(sys.argv[1]) if len(sys.argv) > 1 else 16

# 靶点顺序：小靶点优先（快且稳），大靶点（500aa）放后面
targets_order = [
    'AB_CsuAB',   # 180aa
    'AB_CarO',    # 247aa
    'AB_LpxC',    # 300aa
    'AB_Omp33',   # 299aa
    'AB_CsuE',    # 339aa
    'AB_PmrC',    # 500aa
    'AB_BasE',    # 500aa
    'AB_AdeB',    # 500aa
    'AB_Ata',     # 500aa
    'AB_BauA',    # 500aa (已有12骨架)
    'AB_OmpA',    # 122aa (已有16骨架)
]

for tid in targets_order:
    print(f"\n{'='*60}\n=== 靶点 {tid} ===\n{'='*60}", flush=True)
    # 重启 WSL 释放内存（每个靶点前）
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

# 最后重启 WSL
subprocess.run(["wsl", "--shutdown"], capture_output=True)
print("\n=== 全部靶点 RFdiffusion 完成 ===", flush=True)
