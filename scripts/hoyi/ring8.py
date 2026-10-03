"""HOUYI (后羿) —— 环 8：尾纤维 binder / 天然结构域筛选。

针对环7 排序出的表面受体，设计结合它的尾纤维受体结合域（RBD）。

策略按受体类型分流（科学边界：RFdiffusion 只能做蛋白-蛋白设计）：
  1. surface_protein（表面蛋白受体）→ 真实 RFdiffusion 从头设计 RBD
     （复用 RFdiffusionDesigner，用 RBD 专用长度范围 60-130aa）。
  2. surface_carbohydrate / capsule_polysaccharide（糖类受体）→ 不走 RFdiffusion，
     复用天然结构域（如 Gp45 识别 WTA-GlcNAc）或标注「糖结合域挖掘待接入」。

与环3 的区别：
  - 环3 打胞内酶（迷你蛋白拓扑，binder 40-90aa）。
  - 环8 打表面受体（尾纤维 RBD 拓扑，β-三明治 + 纤维茎，长度 60-130aa）。

糖类受体说明：RFdiffusion 是蛋白-蛋白设计器，无法直接设计糖结合域；金葡菌
WTA/LTA/荚膜都是糖靶点，对它们应复用天然噬菌体尾纤维（Gp45 先例）或挖掘
天然糖结合域（CBM/凝集素结构域），而非硬套 RFdiffusion。
"""
import os
from .utils import load_json, save_json, log, emit_event
from .rf_designer import RFdiffusionDesigner


# 受体类型 → 首选设计策略 + fallback 天然模板
RECEPTOR_DESIGN = {
    "surface_carbohydrate": {
        "desc": "表面多糖（WTA/LTA 等糖基修饰）",
        "primary": "天然结构域复用（RFdiffusion 不适用糖靶点）",
        "fallback": "天然噬菌体尾纤维（如 Gp45 识别 WTA-GlcNAc）",
        "rfdiffusion_ok": False,
    },
    "surface_protein": {
        "desc": "表面蛋白受体",
        "primary": "RFdiffusion 对暴露表位从头设计 RBD（同环3 流程）",
        "fallback": "天然抗体/结合蛋白的结构域",
        "rfdiffusion_ok": True,
    },
    "capsule_polysaccharide": {
        "desc": "荚膜多糖",
        "primary": "天然结构域复用（RFdiffusion 不适用多糖靶点）",
        "fallback": "抗荚膜抗体/凝集素的糖结合域",
        "rfdiffusion_ok": False,
    },
}


# RBD 专用长度范围（尾纤维受体结合域比胞内酶 mini-binder 更长）
RBD_MIN = 60
RBD_MAX = 130


def run(cfg, fiber_targets=None, state=None, num_designs=32, dry_run=False):
    """环 8：尾纤维 binder / 天然结构域筛选。

    Args:
        cfg: 配置
        fiber_targets: 尾纤维靶点列表（None=从环7 产物读）
        state: 状态对象
        num_designs: 每受体从头设计骨架数（仅 surface_protein 类生效）
        dry_run: 预览

    Returns:
        list: 每受体的 binder/结构域候选结果。
    """
    log().info("===== 环 8：尾纤维 binder / 天然结构域筛选 =====")

    if fiber_targets is None:
        fiber_targets = load_json(cfg.ring7_out, default=[]) or []

    if not fiber_targets:
        log().warning("  无尾纤维靶点（环7 无输出），跳过")
        save_json(cfg.ring8_out, [])
        if state is not None:
            state.set_artifact(8, "fiber_binders", [])
            state.mark_ring(8, "SKIPPED", "无尾纤维靶点")
        return []

    # 只对 surface_protein 类受体才需要 RFdiffusionDesigner
    designer = RFdiffusionDesigner(cfg)

    # 尾纤维 RBD 结构目录（与胞内酶 binder 分开）
    rbd_dir = os.path.join(cfg.data_dir, "designs", "tail_fiber_rbd")

    results = []
    total = len(fiber_targets)

    for idx, ft in enumerate(fiber_targets):
        receptor_type = ft.get("receptor_type", "surface_protein")
        strategy = RECEPTOR_DESIGN.get(receptor_type, RECEPTOR_DESIGN["surface_protein"])

        emit_event({
            "ring": 8, "ring_name": "尾纤维 binder 筛选", "status": "progress",
            "message": f"{ft['fiber_target']}: 处理中（{strategy['desc']}）",
            "current": idx, "total": total, "percent": int(idx * 100 / max(total, 1)),
            "target": ft.get("fiber_target"),
        })

        rec = {
            "fiber_target": ft.get("fiber_target"),
            "receptor_type": receptor_type,
            "receptor_desc": strategy["desc"],
            "primary_strategy": strategy["primary"],
            "fallback_strategy": strategy["fallback"],
            "reference_fiber": ft.get("reference_fiber"),
            "reference_uniprot": ft.get("reference_uniprot"),
            "reference_pdb": ft.get("reference_pdb"),
            "priority_rank": ft.get("priority_rank"),
            "composite_score": ft.get("composite_score"),
            "organism": ft.get("organism", ""),
            "source": None,  # 最终选定的 binder/结构域来源
            "binder_sequence": None,
            "binder_id": None,
            "out_dir": None,
            "n_scaffolds": 0,
            "note": None,
        }

        # ---- 判定设计路径 ----
        # 1) 有 reference_fiber（天然模板，如 Gp45）→ 复用天然结构域（参考 MASA 先例）
        # 2) surface_protein + 有 reference_pdb → 真实 RFdiffusion 从头设计 RBD
        # 3) 其余 → 待补（糖结合域挖掘 / 天然结构域序列待填）
        if ft.get("reference_fiber"):
            rec["source"] = "natural_domain"
            rec["binder_id"] = ft["reference_fiber"]
            # 若知识库已填入天然结构域序列（如 Gp45），直接作为 binder_sequence，
            # 环9 可直接拼接重编程尾纤维；否则标记序列待补充
            ref_seq = ft.get("reference_sequence")
            if ref_seq:
                rec["binder_sequence"] = ref_seq
                rec["note"] = (f"复用天然尾纤维结构域 {ft['reference_fiber']}"
                               f"（识别 {ft.get('binding_site', '')}，"
                               f"{len(ref_seq)}aa），可直接进入环9 重编程")
            else:
                rec["note"] = (f"复用天然尾纤维结构域 {ft['reference_fiber']}"
                               f"（识别 {ft.get('binding_site', '')}），"
                               f"符合「糖靶点复用天然蛋白」的策略；序列待补充后重编程")
        elif strategy["rfdiffusion_ok"] and ft.get("reference_pdb"):
            # surface_protein 类 + 有结构 → 真实 RFdiffusion 从头设计 RBD
            rec["source"] = "rfdiffusion"
            rec["binder_id"] = f"{ft['fiber_target']}_RBD"
            _design_rbd(designer, cfg, ft, rec, rbd_dir, num_designs, dry_run)
        elif strategy["rfdiffusion_ok"] and not ft.get("reference_pdb"):
            rec["source"] = "de_novo_pending"
            rec["note"] = ("surface_protein 受体但无 reference_pdb 结构，"
                           "需先结构预测（Chai-1 / 复用 PDB）后接入 RFdiffusion 设计")
        else:
            # 糖类受体无天然模板 → 糖结合域挖掘待接入
            rec["source"] = "glycan_domain_pending"
            rec["note"] = ("糖类受体且无天然模板，需挖掘天然糖结合域"
                           "（CBM/凝集素结构域）；RFdiffusion 不适用糖靶点")

        results.append(rec)

        emit_event({
            "ring": 8, "ring_name": "尾纤维 binder 筛选", "status": "progress",
            "message": f"{ft['fiber_target']}: {rec['source']}",
            "current": idx + 1, "total": total,
            "percent": int((idx + 1) * 100 / max(total, 1)), "target": ft.get("fiber_target"),
        })

    save_json(cfg.ring8_out, results)

    if state is not None:
        state.set_artifact(8, "fiber_binders", results)
        n_nat = sum(1 for r in results if r["source"] == "natural_domain")
        n_rfd = sum(1 for r in results if r["source"] == "rfdiffusion")
        state.mark_ring(8, "DONE",
                        f"{n_nat} 天然结构域 / {n_rfd} 从头设计 / "
                        f"{len(results) - n_nat - n_rfd} 待补")

    return results


def _design_rbd(designer, cfg, ft, rec, rbd_dir, num_designs, dry_run):
    """对 surface_protein 受体做真实 RFdiffusion 从头设计 RBD。

    复用 RFdiffusionDesigner，RBD 专用长度 60-130aa（区别于胞内酶 40-90aa）。
    """
    pdb_id = ft.get("reference_pdb")
    chain = ft.get("pdb_chain", "A")

    # 结构文件：优先 data/pdbs 下已下载的 PDB，回退用 StructurePredictor 下载
    from .structure_predictor import StructurePredictor
    pdb_dir = os.path.join(cfg.data_dir, "pdbs", "sa")
    os.makedirs(pdb_dir, exist_ok=True)
    pdb_path = os.path.join(pdb_dir, f"{pdb_id}.pdb")
    if not (os.path.exists(pdb_path) and os.path.getsize(pdb_path) > 1000):
        if dry_run:
            rec["note"] = f"[dry-run] 将下载 {pdb_id} 并 RFdiffusion 设计 RBD"
            return
        predictor = StructurePredictor(cfg)
        pdb_path = predictor.download_pdb(pdb_id, pdb_dir)
        if not pdb_path:
            rec["source"] = "rfdiffusion_no_structure"
            rec["note"] = f"受体 {pdb_id} 结构下载失败，无法设计 RBD"
            return

    out_dir = os.path.join(rbd_dir, ft["fiber_target"], "rfdiffusion")
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)

    rec["out_dir"] = out_dir

    try:
        # 尾纤维 RBD 用更宽长度范围（60-130aa），区别于胞内酶 mini-binder
        res = designer.design(
            ft["fiber_target"], pdb_path, chain=chain,
            num_designs=num_designs, binder_min=RBD_MIN, binder_max=RBD_MAX,
            out_dir=out_dir, dry_run=dry_run)
        rec["n_scaffolds"] = res.get("n_scaffolds", 0)
        if dry_run:
            rec["note"] = (f"[dry-run] 将 RFdiffusion 设计 RBD "
                           f"({RBD_MIN}-{RBD_MAX}aa, {num_designs} 骨架)")
            return

        # 骨架 → 序列化（ProteinMPNN + ESM），复用胞内酶 binder 同一套 MpnnEsmScorer
        if rec["n_scaffolds"] > 0:
            from .mpnn_esm_scorer import MpnnEsmScorer
            scorer = MpnnEsmScorer(cfg)
            seqs = scorer.run(out_dir, ft["fiber_target"], dry_run=dry_run)
            if seqs:
                top1 = seqs[0]
                rec["binder_sequence"] = top1["sequence"]
                rec["binder_id"] = top1["binder_id"]
                rec["esm_composite"] = top1.get("composite")
                rec["pLL"] = top1.get("pLL")
                rec["note"] = (f"RFdiffusion + ProteinMPNN + ESM 闭环完成，"
                               f"top1 RBD 序列 {len(top1['sequence'])}aa "
                               f"(composite={top1.get('composite')})，可进入环9 重编程")
            else:
                rec["note"] = (f"RFdiffusion 完成 {rec['n_scaffolds']} 骨架，"
                               f"但 MPNN+ESM 序列化无结果，binder_sequence 待补")
    except Exception as e:
        log().error(f"  {ft['fiber_target']}: RFdiffusion RBD 设计失败: {e}")
        rec["source"] = "rfdiffusion_error"
        rec["note"] = f"RFdiffusion 设计失败: {e}"
