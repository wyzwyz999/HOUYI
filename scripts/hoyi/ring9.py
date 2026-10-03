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
    for fb in fiber_binders:
        binder_seq = fb.get("binder_sequence")
        # 无 binder 序列（天然结构域未填 / 从头设计待接入）→ 不拼接，标记待补充
        if not binder_seq:
            full_seq = None
            if fb.get("source") == "natural_domain":
                note = f"天然结构域 {fb.get('binder_id')} 序列待补充后重编程"
            else:
                note = "从头设计 binder 序列待接入（RFdiffusion）后重编程"
        else:
            full_seq = build_reprogrammed_fiber(binder_seq)
            note = "已按 pvc13_N-linker-binder-linker-pvc13_C 三段式重编程"

        fiber = {
            "fiber_target": fb.get("fiber_target"),
            "binder_id": fb.get("binder_id"),
            "source": fb.get("source"),
            "binder_sequence": binder_seq,
            "pvc13_N": PVC13_N,
            "pvc13_C": PVC13_C,
            "linker": PVC13_LINKER,
            "reprogrammed_sequence": full_seq,
            "reprogrammed_length": len(full_seq) if full_seq else None,
            "note": note,
        }
        fibers.append(fiber)

    # 落盘
    save_json(cfg.ring9_out, fibers)

    if not is_dry_run():
        with open(cfg.ring9_fasta, "w", encoding="utf-8") as f:
            for fb in fibers:
                if fb["reprogrammed_sequence"]:
                    f.write(f">{fb['fiber_target']}|{fb['binder_id']} "
                            f"len={fb['reprogrammed_length']} reprogrammed_fiber\n"
                            f"{fb['reprogrammed_sequence']}\n")

    n_full = sum(1 for fb in fibers if fb["reprogrammed_sequence"])
    log().info(f"  输出 {len(fibers)} 条重编程尾纤维（{n_full} 条已拼接完整序列）")
    log().info(f"  FASTA: {cfg.ring9_fasta}")
    log().info(f"  JSON:  {cfg.ring9_out}")

    if state is not None:
        state.set_artifact(9, "reprogrammed_fibers", fibers)
        state.mark_ring(9, "DONE", f"{n_full}/{len(fibers)} 尾纤维重编程完成")

    return fibers
