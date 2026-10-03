"""HOUYI (后羿) —— 环 7：尾纤维靶点分析（表面受体）。

根据菌名，自动分析可结合的病原菌「表面受体」靶点，打分并罗列优先级。
这是尾纤维重定向（杀胞外菌）的第一步，与环1（胞内/包膜靶点）并列，服务于不同的感染生态位。

设计要点：
  - 尾纤维的「靶点」= 病原菌表面受体（WTA/LTA/荚膜多糖/表面蛋白等），非胞内酶。
  - 打分维度：暴露度(exposure) / 必需性(essentiality) / 特异性(specificity)
    / 模板可用性(template_availability) / 菌种覆盖(species_coverage)。
  - 输出按综合分降序排列，作为环8（binder/天然结构域筛选）的输入优先级。

与环1 的区别：
  - 环1 打「胞内生存必需酶 + 菌壁/菌膜（含壁前体转运蛋白）」（杀胞内菌，载荷）。
  - 环7 打「表面受体」（杀胞外菌，尾纤维重定向）。
"""
import os
from .utils import load_json, save_json, log, emit_event


def _composite_score(info, weights):
    """按加权求和计算尾纤维靶点综合分（0-1）。"""
    score = 0.0
    for key, w in weights.items():
        v = info.get(key, 0.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        score += w * v
    return round(score, 4)


def run(cfg, fiber_targets=None, state=None, dry_run=False):
    """环 7：尾纤维靶点分析。

    Args:
        cfg: 配置
        fiber_targets: 指定靶点（None=从知识库读全部，按菌名过滤）
        state: 状态对象
        dry_run: 预览

    Returns:
        list: 按优先级排序的尾纤维靶点列表（含综合分）。
    """
    log().info("===== 环 7：尾纤维靶点分析（表面受体）=====")

    kb = load_json(cfg.fiber_kb_path, default={})
    kb_targets = kb.get("targets", {}) if isinstance(kb, dict) else {}
    weights = kb.get("scoring_weights", {})

    organism = cfg._organism or ""

    # 收集候选靶点：可指定，或按菌名过滤知识库
    if fiber_targets:
        candidates = {t: kb_targets.get(t, {}) for t in fiber_targets}
    else:
        # 按 organism 匹配（大小写/子串）；若无 organism 信息则全部
        candidates = {}
        for t, info in kb_targets.items():
            org = (info.get("organism", "") or "").lower()
            if not organism or not org or organism.lower() in org or org in organism.lower():
                candidates[t] = info
        if not candidates:
            candidates = dict(kb_targets)

    if not candidates:
        log().warning("  无尾纤维靶点（知识库为空），跳过")
        save_json(cfg.ring7_out, [])
        if state is not None:
            state.set_artifact(7, "fiber_targets", [])
            state.mark_ring(7, "SKIPPED", "无尾纤维靶点")
        return []

    results = []
    for t, info in candidates.items():
        score = _composite_score(info, weights)
        rec = {
            "fiber_target": t,
            "protein": info.get("protein", ""),
            "receptor_type": info.get("receptor_type", "surface_protein"),
            "organism": info.get("organism", ""),
            "reference_fiber": info.get("reference_fiber"),
            "reference_uniprot": info.get("reference_uniprot"),
            "reference_pdb": info.get("reference_pdb"),
            "reference_sequence": info.get("reference_sequence"),
            "pdb_chain": info.get("pdb_chain", "A"),
            "binding_site": info.get("binding_site", ""),
            "composite_score": score,
            "priority_rank": 0,  # 下面统一填
        }
        results.append(rec)

    # 按综合分降序排序 + 填优先级
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, r in enumerate(results):
        r["priority_rank"] = i + 1

    save_json(cfg.ring7_out, results)

    log().info(f"  尾纤维靶点优先级（按综合分降序）：")
    for r in results:
        log().info(f"    #{r['priority_rank']} {r['fiber_target']} "
                   f"({r['protein']}) score={r['composite_score']}")

    if state is not None:
        state.set_artifact(7, "fiber_targets", results)
        state.mark_ring(7, "DONE", f"{len(results)} 尾纤维靶点完成打分")

    return results
