"""补跑 AB_BauA 环4（MPNN+ESM 评分），修复 _B 过滤 bug 后。
用法：python run_ab_bauA_ring4.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi import Config
from hoyi.mpnn_esm_scorer import MpnnEsmScorer

cfg = Config()
cfg.set_organism("Acinetobacter baumannii")

design_dir = os.path.join(cfg.data_dir, "designs", "ab", "AB_BauA", "rfdiffusion")
scorer = MpnnEsmScorer(cfg)
recs = scorer.run(design_dir, "AB_BauA", dry_run=False)
print(f"[AB_BauA] 评分完成，共 {len(recs)} 条", flush=True)
