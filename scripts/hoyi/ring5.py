"""HOUYI (后羿) —— 环 5：输出 binder。

从评分结果汇总每靶点 Top N，输出 FASTA + JSON（含合成订单格式）。
"""
from .utils import save_json, log, is_dry_run


def run(cfg, scored=None, top_n=3, state=None):
    log().info(f"===== 环 5：输出 binder 序列（Top{top_n}）=====")

    if scored is None:
        from .utils import load_json

        # 优先使用通过 AF2 验证的候选；若不存在或为空，则回退到原 Ring4 评分结果
        scored = load_json(cfg.ring4_af2_validated_out)
        if scored:
            log().info(
                f"  使用 AF2 validated 候选: {cfg.ring4_af2_validated_out} "
                f"({len(scored)} 条)"
            )
        else:
            scored = load_json(cfg.ring4_out)
            if scored:
                log().info(
                    f"  未发现 AF2 validated 候选，回退 Ring4: "
                    f"{cfg.ring4_out} ({len(scored)} 条)"
                )

        if not scored:
            scored = []

    if not scored:
        # 无 binder 结果：输出空产物，不崩溃
        log().warning("  无 binder 可输出（该细菌暂无 binder 库）")
        save_json(cfg.ring5_json, [])
        if not is_dry_run():
            with open(cfg.ring5_fasta, "w", encoding="utf-8") as f:
                f.write("# 无 binder 输出\n")
        if state is not None:
            state.set_artifact(5, "top", [])
            state.mark_ring(5, "DONE", "0 条 Top binder（无 binder 库）")
        return []

    # 按靶点分组（scored 已全局排序，分组后各组内仍保持序）
    by_target = {}
    for b in scored:
        by_target.setdefault(b["target"], []).append(b)

    # 按每组最优 binder 的综合评分降序排列靶点。
    # AF2 validated / 新评分结果优先使用 qc_composite，
    # 其次 composite，最后兼容旧版 score。
    def binder_rank_score(b):
        for key in ("qc_composite", "composite", "score"):
            value = b.get(key)
            if value is not None:
                return value
        return float("-inf")

    def group_best_score(items):
        return max((binder_rank_score(b) for b in items), default=float("-inf"))
    ordered_targets = sorted(by_target.keys(), key=lambda t: group_best_score(by_target[t]), reverse=True)

    top = []
    for t in ordered_targets:
        for b in by_target[t][:top_n]:
            top.append(b)

    # FASTA 输出（去重 binder_id 里的 len= 冗余）
    if not is_dry_run():
        with open(cfg.ring5_fasta, "w", encoding="utf-8") as f:
            for b in top:
                bid = b["binder_id"].split(" len=")[0]
                f.write(f">{b['target']}|{bid} len={b['length']}\n{b['sequence']}\n")

    save_json(cfg.ring5_json, top)

    log().info(f"  输出 {len(top)} 条 Top binder（{len(by_target)} 靶点 × Top{top_n}）")
    log().info(f"  FASTA: {cfg.ring5_fasta}")
    log().info(f"  JSON:  {cfg.ring5_json}")

    if state is not None:
        state.set_artifact(5, "top", top)
        state.mark_ring(5, "DONE", f"{len(top)} Top binders 输出")

    return top
