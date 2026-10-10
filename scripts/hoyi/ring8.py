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
from .natural_rbp_search import search_natural_rbps


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


def run(cfg, fiber_targets=None, state=None, num_designs=32, mpnn_samples=3, dry_run=False):
    """环 8：尾纤维 binder / 天然结构域筛选。

    Args:
        cfg: 配置
        fiber_targets: 尾纤维靶点列表（None=从环7 产物读）
        state: 状态对象
        num_designs: 每受体从头设计骨架数（仅 surface_protein 类生效）
        mpnn_samples: 每骨架、每采样温度的 ProteinMPNN 序列数
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
    rbd_dir = os.path.join(
        cfg.data_dir,
        "designs",
        cfg.organism_slug,
        "tail_fiber_rbd",
    )

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

        base = {
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
        }

        route_results = []

        # =====================================================
        # Route A: 天然蛋白 / 天然尾纤维 / RBP
        # =====================================================
        natural = dict(base)
        natural["route"] = "natural"
        natural["source"] = "natural_domain"
        natural["binder_sequence"] = None
        natural["binder_id"] = None
        natural["out_dir"] = None
        natural["n_scaffolds"] = 0

        if ft.get("reference_fiber"):
            natural["binder_id"] = ft["reference_fiber"]
            ref_seq = ft.get("reference_sequence")

            if ref_seq:
                natural["binder_sequence"] = ref_seq
                natural["route_status"] = "READY"
                natural["note"] = (
                    f"天然尾纤维/RBP候选 {ft['reference_fiber']} "
                    f"（{len(ref_seq)}aa），可进入Ring9"
                )
            else:
                natural["route_status"] = "PENDING_SEQUENCE"
                natural["note"] = (
                    f"已知天然候选 {ft['reference_fiber']}，"
                    "但reference_sequence待补充"
                )
        else:
            natural["source"] = "natural_search"

            try:
                candidates = search_natural_rbps(
                    host_organism=ft.get("organism") or cfg._organism or "",
                    size=30,
                    top_n=5,
                    fetch_sequences=False,
                )
            except Exception as e:
                candidates = []
                natural["search_error"] = str(e)

            natural["natural_candidates"] = candidates

            if candidates:
                ready_candidates = [
                    c for c in candidates
                    if (c.get("evidence_summary") or {}).get(
                        "ready_for_ring9", False
                    )
                ]

                if ready_candidates:
                    best = ready_candidates[0]

                    natural["selected_candidate"] = {
                        "accession": best.get("accession"),
                        "protein_name": best.get("protein_name"),
                        "source_organism": best.get("source_organism"),
                        "evidence_summary": best.get("evidence_summary"),
                    }

                    if best.get("sequence"):
                        natural["binder_id"] = (
                            best.get("accession")
                            or best.get("protein_name")
                        )
                        natural["binder_sequence"] = best.get("sequence")
                        natural["route_status"] = "READY"
                        natural["note"] = (
                            "自动天然RBP候选已通过统一证据门控，"
                            "且序列可用，可进入Ring9"
                        )
                    else:
                        natural["route_status"] = (
                            "EVIDENCE_READY_PENDING_SEQUENCE"
                        )
                        natural["note"] = (
                            "自动天然RBP候选已通过统一证据门控，"
                            "但序列尚未获取，暂不进入Ring9"
                        )
                else:
                    natural["route_status"] = "SEARCHED_CANDIDATE"
                    natural["note"] = (
                        f"自动检索到 {len(candidates)} 条天然tail fiber/RBP候选；"
                        "当前无候选满足统一Ring9证据门控"
                    )
            else:
                natural["route_status"] = "NO_HIT"
                natural["note"] = (
                    "自动天然tail fiber/RBP检索未发现候选"
                )

        route_results.append(natural)

        # =====================================================
        # Route B: de novo binder / RBD
        # =====================================================
        de_novo = dict(base)
        de_novo["route"] = "de_novo"
        de_novo["source"] = None
        de_novo["binder_sequence"] = None
        de_novo["binder_id"] = None
        de_novo["out_dir"] = None
        de_novo["n_scaffolds"] = 0

        if strategy["rfdiffusion_ok"] and ft.get("reference_pdb"):
            de_novo["source"] = "rfdiffusion"
            de_novo["binder_id"] = f"{ft['fiber_target']}_RBD"
            de_novo["route_status"] = "DESIGNING" if not dry_run else "DRY_RUN"

            _design_rbd(
                designer,
                cfg,
                ft,
                de_novo,
                rbd_dir,
                num_designs,
                mpnn_samples,
                dry_run,
            )

            if de_novo.get("binder_sequence"):
                de_novo["route_status"] = "READY"
            elif de_novo.get("source") == "rfdiffusion_error":
                de_novo["route_status"] = "ERROR"

        elif strategy["rfdiffusion_ok"] and not ft.get("reference_pdb"):
            de_novo["source"] = "de_novo_pending"
            de_novo["route_status"] = "PENDING_STRUCTURE"
            de_novo["note"] = (
                "surface_protein受体但无结构，"
                "需先结构预测后进入de novo设计"
            )

        else:
            de_novo["source"] = "de_novo_not_applicable"
            de_novo["route_status"] = "NOT_APPLICABLE"
            de_novo["note"] = (
                "当前de novo RFdiffusion路线不直接适用于该受体类型"
            )

        route_results.append(de_novo)

        results.extend(route_results)

        emit_event({
            "ring": 8, "ring_name": "尾纤维 binder 筛选", "status": "progress",
            "message": (
                f"{ft['fiber_target']}: "
                f"{', '.join(r.get('route') + '=' + str(r.get('route_status')) for r in route_results)}"
            ),
            "current": idx + 1, "total": total,
            "percent": int((idx + 1) * 100 / max(total, 1)), "target": ft.get("fiber_target"),
        })

    save_json(cfg.ring8_out, results)

    if state is not None:
        state.set_artifact(8, "fiber_binders", results)
        n_nat = sum(
            1 for r in results
            if r.get("route") == "natural" and r.get("route_status") == "READY"
        )
        n_denovo = sum(
            1 for r in results
            if r.get("route") == "de_novo" and r.get("route_status") == "READY"
        )
        n_pending = sum(
            1 for r in results
            if str(r.get("route_status", "")).startswith("PENDING")
        )

        state.mark_ring(
            8,
            "DONE",
            f"{n_nat} 天然候选READY / "
            f"{n_denovo} de novo READY / "
            f"{n_pending} pending"
        )

    return results


def _design_rbd(designer, cfg, ft, rec, rbd_dir, num_designs, mpnn_samples, dry_run):
    """对 surface_protein 受体做真实 RFdiffusion 从头设计 RBD。

    复用 RFdiffusionDesigner，RBD 专用长度 60-130aa（区别于胞内酶 40-90aa）。
    """
    pdb_id = ft.get("reference_pdb")
    chain = ft.get("pdb_chain", "A")

    # 结构来源兼容：
    # 1) reference_pdb 若已经是本地 PDB 路径，直接使用；
    # 2) 否则按传统 PDB ID 在 data/pdbs 中查找 / 从 RCSB 下载。
    from .structure_predictor import StructurePredictor

    if (
        pdb_id
        and os.path.isfile(pdb_id)
        and os.path.getsize(pdb_id) > 1000
    ):
        pdb_path = os.path.abspath(pdb_id)
        log().info(
            f"  {ft['fiber_target']}: 使用本地受体结构 {pdb_path}"
        )
        rec["structure_source"] = "local_pdb"
    else:
        pdb_dir = os.path.join(
            cfg.data_dir,
            "pdbs",
            cfg.organism_slug,
        )
        os.makedirs(pdb_dir, exist_ok=True)

        pdb_path = os.path.join(pdb_dir, f"{pdb_id}.pdb")

        if not (
            os.path.exists(pdb_path)
            and os.path.getsize(pdb_path) > 1000
        ):
            if dry_run:
                rec["note"] = (
                    f"[dry-run] 将下载 {pdb_id} 并 RFdiffusion 设计 RBD"
                )
                return

            predictor = StructurePredictor(cfg)
            pdb_path = predictor.download_pdb(pdb_id, pdb_dir)

            if not pdb_path:
                rec["source"] = "rfdiffusion_no_structure"
                rec["route_status"] = "ERROR"
                rec["note"] = (
                    f"受体 {pdb_id} 既不是有效本地PDB，"
                    "也无法从RCSB下载，无法设计 RBD"
                )
                return

        rec["structure_source"] = "rcsb_pdb"

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
        rec["n_scaffolds_total"] = res.get("n_scaffolds", 0)

        if dry_run:
            rec["n_scaffolds"] = min(
                int(num_designs),
                int(rec["n_scaffolds_total"] or 0),
            )
            rec["note"] = (
                f"[dry-run] 将 RFdiffusion 设计/复用 RBD "
                f"({RBD_MIN}-{RBD_MAX}aa, budget={num_designs} 骨架)"
            )
            return

        # 只让本次预算允许的 backbone 进入 ProteinMPNN/ESM。
        # 历史缓存保留，不删除。
        import glob
        import re

        target_id = ft["fiber_target"]

        backbone_paths = sorted(
            [
                p
                for p in glob.glob(os.path.join(out_dir, "*.pdb"))
                if re.match(
                    rf"^{re.escape(target_id)}__\d+\.pdb$",
                    os.path.basename(p),
                )
            ],
            key=lambda p: int(
                re.search(
                    r"__(\d+)\.pdb$",
                    os.path.basename(p),
                ).group(1)
            ),
        )

        allowed_paths = backbone_paths[:max(0, int(num_designs))]
        allowed_names = [os.path.basename(p) for p in allowed_paths]

        rec["n_scaffolds"] = len(allowed_names)
        rec["n_scaffolds_used"] = len(allowed_names)
        rec["allowed_backbones"] = allowed_names

        log().info(
            f"  {target_id}: Ring8 本次使用 "
            f"{len(allowed_names)}/{len(backbone_paths)} 个骨架 "
            f"(budget={num_designs})"
        )

        # 骨架 → 序列化（ProteinMPNN + ESM）
        if rec["n_scaffolds"] > 0:
            from .mpnn_esm_scorer import MpnnEsmScorer
            scorer = MpnnEsmScorer(cfg)
            seqs = scorer.run(
                out_dir,
                target_id,
                num_seq_per_target=mpnn_samples,
                allowed_pdb_names=allowed_names,
                dry_run=dry_run,
            )
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
