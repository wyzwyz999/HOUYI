"""HOUYI (后羿) —— 环 10：纳米注射器总装（PVC 完整重设计）。

把「重编程尾纤维（环9）」与「杀菌载荷（环6）」组装成完整的重设计纳米注射器规格。
载荷（子弹）+ 尾纤维重定向（瞄准器）= PVC 完整重设计 = 纳米注射器。

完整结构：pvc1-12 + pvc13_N-binder-C + pvc14-16 + designed Payload
  - pvc1-12：PVC 主体（管-鞘组件），保持天然不变
  - pvc13_N-binder-C：重编程尾纤维（环9，受体识别域已替换）
  - pvc14-16：PVC 尾部/末端组件，保持天然不变
  - designed Payload：杀菌载荷（环6，经 Pdp1_NTD 装载进尾管）

产出：nanosyringes.json + nanosyringes.fasta，端到端最终交付物。
"""
from .utils import load_json, save_json, log, is_dry_run


def run(cfg, payloads=None, reprogrammed_fibers=None, state=None):
    """环 10：纳米注射器总装。

    Args:
        cfg: 配置
        payloads: 载荷列表（None=从环6 产物读）
        reprogrammed_fibers: 重编程尾纤维列表（None=从环9 产物读）
        state: 状态对象

    Returns:
        list: 组装好的纳米注射器规格列表。
    """
    log().info("===== 环 10：纳米注射器总装（PVC 完整重设计）=====")

    if payloads is None:
        payloads = load_json(cfg.ring6_json, default=[]) or []
    if reprogrammed_fibers is None:
        reprogrammed_fibers = load_json(cfg.ring9_out, default=[]) or []

    if not payloads:
        log().warning("  无载荷（环6 无输出），仅记录尾纤维模块")

    # 尾纤维按 organism 索引（供载荷匹配同菌种的注射器）
    fibers_by_org = {}
    for f in reprogrammed_fibers:
        org = f.get("organism", cfg._organism or "")
        fibers_by_org.setdefault(org, []).append(f)
    # 环9 产物无 organism 字段时，全部归入全局
    if not fibers_by_org and reprogrammed_fibers:
        fibers_by_org[cfg._organism or ""] = reprogrammed_fibers

    nanosyringes = []

    if payloads:
        for p in payloads:
            org = p.get("organism", cfg._organism or "")
            matched_fibers = (
                fibers_by_org.get(org)
                or fibers_by_org.get("")
                or reprogrammed_fibers
            )

            # 只使用具有完整重编程序列的fiber参与正式组合。
            valid_fibers = [
                f for f in matched_fibers
                if f.get("reprogrammed_sequence")
            ]

            if valid_fibers:
                for f in valid_fibers:
                    payload_tag = (
                        p.get("binder_id")
                        or p.get("target")
                        or "payload"
                    )
                    fiber_tag = (
                        f.get("binder_id")
                        or f.get("fiber_target")
                        or "fiber"
                    )

                    syringe_id = f"NS-{payload_tag}__{fiber_tag}"

                    syringe = {
                        "syringe_id": syringe_id,
                        "design_id": syringe_id,
                        "run_id": (
                            p.get("run_id")
                            or f.get("run_id")
                            or None
                        ),
                        "organism": org,
                        "components": {
                            "pvc1_12": {
                                "status": "native",
                                "note": "PVC 主体管-鞘组件（保持天然）",
                            },
                            "pvc13_reprogrammed": {
                                "status": "reprogrammed",
                                "fiber_sequence": f.get("reprogrammed_sequence"),
                                "fiber_target": f.get("fiber_target"),
                                "fiber_binder_id": f.get("binder_id"),
                                "route": f.get("route"),
                                "source": f.get("source"),
                                "reference_fiber": f.get("reference_fiber"),
                                "reference_uniprot": f.get("reference_uniprot"),
                                "reference_pdb": f.get("reference_pdb"),
                                "evidence_summary": f.get("evidence_summary"),
                            },
                            "pvc14_16": {
                                "status": "native",
                                "note": "PVC 尾部/末端组件（保持天然）",
                            },
                            "payload": {
                                "target": p.get("target"),
                                "binder_id": p.get("binder_id"),
                                "candidate_tier": p.get("candidate_tier"),
                                "payload_sequence": p.get("payload_sequence", ""),
                                "payload_length": p.get("payload_length"),
                                "evidence_summary": p.get("evidence_summary"),
                                "source_record_id": p.get("source_record_id"),
                                "mechanism": "杀菌载荷（经 Pdp1_NTD 装载，子弹）",
                            },
                        },
                        "assembly_note": (
                            "pvc1-12 + pvc13_N-binder-C + pvc14-16 + designed Payload。"
                            "保持管-鞘主体组装不变，仅替换 pvc13 受体识别域实现靶向重定向，"
                            "同时经 Pdp1_NTD 装载杀菌载荷。载荷 + 尾纤维重定向 = PVC 完整重设计。"
                        ),
                        "complete": True,
                    }
                    nanosyringes.append(syringe)

            else:
                # 不静默丢弃payload：保留一条incomplete记录便于批处理审计。
                syringe_id = (
                    f"NS-{p.get('binder_id') or p.get('target', 'unknown')}__NO_FIBER"
                )

                syringe = {
                    "syringe_id": syringe_id,
                    "design_id": syringe_id,
                    "run_id": p.get("run_id"),
                    "organism": org,
                    "reason_code": "NO_READY_FIBER",
                    "components": {
                        "pvc1_12": {"status": "native"},
                        "pvc13_reprogrammed": {
                            "status": "missing",
                            "fiber_sequence": None,
                            "fiber_target": None,
                            "fiber_binder_id": None,
                            "route": None,
                            "source": None,
                        },
                        "pvc14_16": {"status": "native"},
                        "payload": {
                            "target": p.get("target"),
                            "binder_id": p.get("binder_id"),
                            "candidate_tier": p.get("candidate_tier"),
                            "payload_sequence": p.get("payload_sequence", ""),
                            "payload_length": p.get("payload_length"),
                            "mechanism": "杀菌载荷（经 Pdp1_NTD 装载，子弹）",
                        },
                    },
                    "assembly_note": "已有payload，但该菌当前无可执行READY尾纤维。",
                    "complete": False,
                }
                nanosyringes.append(syringe)
    else:
        # 无载荷时，输出尾纤维模块规格（空载荷注射器）
        for f in reprogrammed_fibers:
            syringe = {
                "syringe_id": f"NS-fiber-{f.get('fiber_target', 'unknown')}",
                "organism": f.get("organism", ""),
                "components": {
                    "pvc1_12": {"status": "native"},
                    "pvc13_reprogrammed": {
                        "status": "reprogrammed",
                        "fiber_sequence": f.get("reprogrammed_sequence"),
                        "fiber_target": f.get("fiber_target"),
                        "fiber_binder_id": f.get("binder_id"),
                        "route": f.get("route"),
                        "source": f.get("source"),
                        "reference_fiber": f.get("reference_fiber"),
                        "reference_uniprot": f.get("reference_uniprot"),
                    },
                    "pvc14_16": {"status": "native"},
                    "payload": None,
                },
                "assembly_note": "暂无载荷，仅输出靶向模块规格。",
                "complete": False,
            }
            nanosyringes.append(syringe)

    save_json(cfg.ring10_json, nanosyringes)

    if not is_dry_run():
        with open(cfg.ring10_fasta, "w", encoding="utf-8") as f:
            for ns in nanosyringes:
                pl = (ns.get("components", {}).get("payload") or {})
                seq = pl.get("payload_sequence", "")
                f.write(f">{ns['syringe_id']}|{ns['organism']}|payload_len={len(seq)}\n")
                f.write((seq or "# 无载荷序列") + "\n")

    log().info(f"  输出 {len(nanosyringes)} 条纳米注射器规格")
    log().info(f"  JSON:  {cfg.ring10_json}")
    log().info(f"  FASTA: {cfg.ring10_fasta}")

    if state is not None:
        state.set_artifact(10, "nanosyringes", nanosyringes)
        n_complete = sum(1 for ns in nanosyringes if ns["complete"])
        state.mark_ring(10, "DONE", f"{n_complete}/{len(nanosyringes)} 注射器组装完成")

    return nanosyringes
