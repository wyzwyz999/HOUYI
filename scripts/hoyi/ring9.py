"""HOUYI (后羿) —— 环 9：重编程 pvc13 生成新尾纤维。

把环8 选定的 binder/天然结构域，替换进 pvc13 的中间受体识别域，
生成重编程尾纤维：pvc13_N + linker + binder + linker + pvc13_C。

科学背景（GP45 改造案例）：
  - pvc13 是 PVC 的尾纤维蛋白，其 N 端、C 端负责在 PVC 组装中的锚定/结构功能（保留）。
  - 中间的受体识别域决定「打谁」，默认识别宿主细胞；替换它为病原菌受体结合域，
    即可把注射器靶向重定向到病原菌本身。
  - 参考案例：E01 anti-EGFR DARPin 曾用「N 端保留段 + linker + binder + linker + C 端保留段」
    的三段式实现宿主细胞 EGFR 重靶向，证明该范式通用可行。

结构：重编程尾纤维 = pvc13_N(402aa) + linker(GGSGGGGSGG) + binder + linker(GGSGGGGSGG) + pvc13_C(32aa)
"""
import os

from .config import PVC13_N, PVC13_C, PVC13_LINKER
from .utils import load_json, save_json, log, is_dry_run


def build_reprogrammed_fiber(binder_sequence: str) -> str:
    """把 binder 序列拼成重编程尾纤维：pvc13_N + linker + binder + linker + pvc13_C。

    Args:
        binder_sequence: 尾纤维受体结合域氨基酸序列（单字母）。

    Returns:
        str: 重编程尾纤维完整氨基酸序列。
    """
    seq = (binder_sequence or "").strip().upper()
    if not seq:
        return PVC13_N + PVC13_LINKER + PVC13_C  # 无 binder 兜底
    return PVC13_N + PVC13_LINKER + seq + PVC13_LINKER + PVC13_C


def run(cfg, fiber_binders=None, state=None):
    """环 9：重编程 pvc13 生成新尾纤维。

    Args:
        cfg: 配置
        fiber_binders: 环8 输出的 binder/结构域候选（None=从环8 产物读）
        state: 状态对象

    Returns:
        list: 重编程尾纤维列表（含完整序列）。
    """
    log().info("===== 环 9：重编程 pvc13 生成新尾纤维 =====")

    if fiber_binders is None:
        fiber_binders = load_json(cfg.ring8_out, default=[]) or []

    if not fiber_binders:
        log().warning("  无尾纤维 binder（环8 无输出），跳过")
        save_json(cfg.ring9_out, [])
        if state is not None:
            state.set_artifact(9, "reprogrammed_fibers", [])
            state.mark_ring(9, "SKIPPED", "无尾纤维 binder")
        return []

    fibers = []
    skipped = []

    for fb in fiber_binders:
        binder_seq = (fb.get("binder_sequence") or "").strip()
        route = fb.get("route")
        route_status = fb.get("route_status")

        # Ring8 双轨后，仅 READY + 有真实序列的候选进入 Ring9。
        # 旧版无 route_status 的记录保持兼容：只要有 binder_sequence 即可进入。
        is_ready = (
            route_status == "READY"
            if route_status is not None
            else bool(binder_seq)
        )

        if not is_ready or not binder_seq:
            if route_status not in (None, "READY"):
                reason_code = str(route_status)
            else:
                reason_code = "MISSING_BINDER_SEQUENCE"

            skipped.append({
                "fiber_target": fb.get("fiber_target"),
                "organism": fb.get("organism", cfg._organism or ""),
                "binder_id": fb.get("binder_id"),
                "route": route,
                "route_status": route_status,
                "source": fb.get("source"),

                # 兼容旧字段
                "reason": (
                    "route_not_ready"
                    if route_status not in (None, "READY")
                    else "missing_binder_sequence"
                ),

                # 新的机器可读细粒度原因
                "reason_code": reason_code,
            })
            continue

        full_seq = build_reprogrammed_fiber(binder_seq)

        fiber = {
            "fiber_target": fb.get("fiber_target"),
            "organism": fb.get("organism", cfg._organism or ""),
            "binder_id": fb.get("binder_id"),
            "source": fb.get("source"),
            "route": route,
            "route_status": route_status,
            "reference_fiber": fb.get("reference_fiber"),
            "reference_uniprot": fb.get("reference_uniprot"),
            "reference_pdb": fb.get("reference_pdb"),
            "binder_sequence": binder_seq,
            "pvc13_N": PVC13_N,
            "pvc13_C": PVC13_C,
            "linker": PVC13_LINKER,
            "reprogrammed_sequence": full_seq,
            "reprogrammed_length": len(full_seq),
            "note": (
                "已按 pvc13_N-linker-binder-linker-pvc13_C "
                "三段式重编程"
            ),
        }
        fibers.append(fiber)

    # 落盘
    save_json(cfg.ring9_out, fibers)

    skipped_path = os.path.join(cfg.results_dir, "ring9_skipped.json")
    save_json(skipped_path, skipped)

    if not is_dry_run():
        with open(cfg.ring9_fasta, "w", encoding="utf-8") as f:
            for fb in fibers:
                if fb["reprogrammed_sequence"]:
                    f.write(f">{fb['fiber_target']}|{fb['binder_id']} "
                            f"len={fb['reprogrammed_length']} reprogrammed_fiber\n"
                            f"{fb['reprogrammed_sequence']}\n")

    n_full = len(fibers)
    log().info(
        f"  输出 {n_full} 条重编程尾纤维；"
        f"跳过 {len(skipped)} 条非 READY / 无序列 route"
    )
    log().info(f"  FASTA: {cfg.ring9_fasta}")
    log().info(f"  JSON:  {cfg.ring9_out}")

    if state is not None:
        state.set_artifact(9, "reprogrammed_fibers", fibers)
        state.mark_ring(9, "DONE", f"{n_full}/{len(fibers)} 尾纤维重编程完成")

    return fibers
