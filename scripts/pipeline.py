#!/usr/bin/env python3
"""HOUYI (后羿) 端到端抗菌载荷设计平台 —— CLI 入口。

用法：
  python pipeline.py --organism "Staphylococcus aureus"            # 走全程
  python pipeline.py --start 3 --stop 6                            # 只跑部分环
  python pipeline.py --targets B3_ClfA D2_Hla_blocker              # 指定靶点
  python pipeline.py --skip 1                                      # 跳过某环
  python pipeline.py --dry-run                                     # 预览不落地
  python pipeline.py --scorer length                               # 评分器（length/mic）
  python pipeline.py --mic mic_results.json                        # 接入 MIC 湿实验数据

环编号（1-based，十环）：
  环1 靶点分析 → 环2 结构预测 → 环3 Binder 设计 → 环4 评分排序
  → 环5 输出 binder → 环6 拼装载（Pdp1_NTD-linker-binder）
  → 环7 尾纤维靶点分析 → 环8 尾纤维 binder/天然结构域筛选
  → 环9 重编程 pvc13 → 环10 纳米注射器总装

模块化重构版，工程健壮性增强：真断点续跑 / 异常处理 / dry-run / 可插拔评分器。
"""
import sys
import os
import argparse

# 保证能 import hoyi 包（脚本可能在 scripts/ 或 workspace 下运行）
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from hoyi.config import Config
from hoyi.utils import load_json
from hoyi import run_pipeline


def main():
    ap = argparse.ArgumentParser(description="HOUYI (后羿) 端到端抗菌 binder 设计平台")
    ap.add_argument("--organism", default="Staphylococcus aureus")
    ap.add_argument("--targets", nargs="*", help="指定靶点（默认全部）")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--stop", type=int, default=10)
    ap.add_argument("--skip", nargs="*", type=int, default=[], help="跳过的环编号")
    ap.add_argument("--dry-run", action="store_true", help="预览不落地")
    ap.add_argument("--scorer", default="length", help="环4评分器: length/mic")
    ap.add_argument("--mic", help="MIC 湿实验数据 JSON 路径（供 mic 评分器）")
    ap.add_argument("--top-n", type=int, default=3, help="每靶点输出 Top N")
    ap.add_argument("--num-designs", type=int, default=32,
                    help="每靶点 RFdiffusion 骨架数")
    ap.add_argument("--verbose", action="store_true", help="详细日志")
    args = ap.parse_args()

    # 载入 MIC 数据（若指定）
    mic_map = None
    if args.mic:
        mic_map = load_json(args.mic)
        if not mic_map:
            print(f"[error] 无法读取 MIC 数据: {args.mic}")
            sys.exit(1)

    cfg = Config()
    try:
        run_pipeline(
            cfg,
            args.organism,
            targets=args.targets,
            start=args.start,
            stop=args.stop,
            skip=args.skip,
            dry_run=args.dry_run,
            scorer=args.scorer,
            mic_map=mic_map,
            top_n=args.top_n,
            num_designs=args.num_designs,
        )
    except Exception as e:
        print(f"\n[FATAL] 管线执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
