"""HOUYI (后羿) —— 环 5：多证据 binder 决策与输出。

候选分层：
- PRIMARY: AF2 正式验证通过
- SECONDARY: AF2 未通过/未验证，但前序 Ring3.5/Ring4 证据较好
- EXPERIMENT_RESCUED: 已有湿实验阳性证据，即使 AF2 不理想仍保留
- REJECTED: 明确几何失败、缺序列或未进入最终选择

Ring6 接口保持兼容：
仍输出 top_binders.json / top_binders.fasta。
"""

import os

from .utils import save_json, load_json, log, is_dry_run


TIER_PRIORITY = {
    "EXPERIMENT_RESCUED": 4,
    "PRIMARY": 3,
    "SECONDARY": 2,
    "REJECTED": 0,
}

AF2_CONFIDENCE_PRIORITY = {
    "HIGH": 3,
    "INTERMEDIATE": 2,
    "LOW": 1,
    "UNVALIDATED": 0,
}


def af2_confidence(candidate):
    """读取AF2分层；兼容旧记录和未验证候选。"""
    af2 = candidate.get("af2_validation") or {}

    confidence = str(af2.get("confidence") or "").upper()
    if confidence in AF2_CONFIDENCE_PRIORITY:
        return confidence

    if af2.get("passed") is True:
        return "HIGH"

    if af2:
        return "LOW"

    return "UNVALIDATED"


def binder_rank_score(b):
    """兼容现有 Ring4 多种评分字段。"""
    for key in ("qc_composite", "composite", "score"):
        value = b.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return float("-inf")


def _experimental_positive(candidate, experimental_rescue_ids):
    """只接受显式实验阳性信息，不做猜测。"""
    bid = candidate.get("binder_id")

    if bid and bid in experimental_rescue_ids:
        return True

    exp = candidate.get("experimental_validation")
    if not isinstance(exp, dict):
        return False

    return bool(
        exp.get("positive")
        or exp.get("passed")
        or exp.get("antibacterial_effect")
    )


def _classify(candidate, experimental_rescue_ids):
    """给单条候选分层。"""

    if _experimental_positive(candidate, experimental_rescue_ids):
        return "EXPERIMENT_RESCUED", "已有显式湿实验阳性证据"

    af2 = candidate.get("af2_validation") or {}
    confidence = af2_confidence(candidate)

    if af2.get("passed") is True or confidence == "HIGH":
        return "PRIMARY", "AF2高置信验证通过"

    seq = (candidate.get("sequence") or "").strip()
    if not seq:
        return "REJECTED", "缺少binder序列"

    # Ring3.5 明确 hard fail 的候选不作为自动备选。
    if candidate.get("interface_hard_pass") is False:
        return "REJECTED", "Ring3.5界面几何硬门失败"

    # 不设新的顶层tier，保持Ring6及后续接口兼容。
    # 在SECONDARY内部使用AF2 confidence进行优先排序。
    if confidence == "INTERMEDIATE":
        return "SECONDARY", "AF2中等支持，作为优先备选保留"

    if confidence == "LOW":
        return "SECONDARY", "AF2低置信，但前序证据未明确失败，作为备选保留"

    return "SECONDARY", "AF2未验证，保留前序高排名候选作为备选"


def run(
    cfg,
    scored=None,
    af2_results=None,
    top_n=3,
    state=None,
    experimental_rescue_ids=None,
):
    log().info(f"===== 环 5：多证据 binder 决策（Top{top_n}）=====")

    experimental_rescue_ids = set(experimental_rescue_ids or [])

    # Ring5始终以Ring4完整候选为基础。
    if scored is None:
        scored = load_json(cfg.ring4_out, default=[]) or []

    if not scored:
        log().warning("  无 Ring4 binder 候选可输出")
        save_json(cfg.ring5_json, [])

        decisions_path = os.path.join(cfg.results_dir, "ring5_decisions.json")
        save_json(decisions_path, [])

        if not is_dry_run():
            with open(cfg.ring5_fasta, "w", encoding="utf-8") as f:
                f.write("# 无 binder 输出\n")

        if state is not None:
            state.set_artifact(5, "top", [])
            state.mark_ring(5, "DONE", "0 条 Top binder")

        return []

    # AF2结果按binder_id覆盖/补充回Ring4记录。
    af2_map = {}
    for item in (af2_results or []):
        bid = item.get("binder_id")
        if bid:
            af2_map[bid] = item

    decisions = []

    for original in scored:
        b = dict(original)
        bid = b.get("binder_id")

        if bid in af2_map:
            af2_item = af2_map[bid]

            if af2_item.get("af2_validation") is not None:
                b["af2_validation"] = af2_item["af2_validation"]

            # 保留AF2阶段可能新增的其它汇总字段，但不覆盖核心ID/sequence。
            for key, value in af2_item.items():
                if key not in ("binder_id", "target", "sequence"):
                    b.setdefault(key, value)

        tier, reason = _classify(b, experimental_rescue_ids)

        b["candidate_tier"] = tier
        b["af2_confidence"] = af2_confidence(b)
        b["selection_reason"] = reason
        b["ring5_rank_score"] = binder_rank_score(b)

        decisions.append(b)

    # 全量决策记录，用于论文/实验追踪/批处理审计。
    decisions_path = os.path.join(cfg.results_dir, "ring5_decisions.json")
    save_json(decisions_path, decisions)

    # 每靶点分组。
    by_target = {}
    for b in decisions:
        target = b.get("target")
        if target:
            by_target.setdefault(target, []).append(b)

    top = []

    for target, items in by_target.items():
        eligible = [
            b for b in items
            if b["candidate_tier"] != "REJECTED"
        ]

        eligible.sort(
            key=lambda b: (
                TIER_PRIORITY.get(b["candidate_tier"], 0),
                AF2_CONFIDENCE_PRIORITY.get(
                    b.get("af2_confidence", "UNVALIDATED"), 0
                ),
                b.get("ring5_rank_score", float("-inf")),
            ),
            reverse=True,
        )

        selected = eligible[:top_n]

        for rank, b in enumerate(selected, 1):
            b["ring5_target_rank"] = rank
            top.append(b)

    # 靶点之间再按层级和评分排序，保证输出稳定。
    top.sort(
        key=lambda b: (
            TIER_PRIORITY.get(b["candidate_tier"], 0),
            AF2_CONFIDENCE_PRIORITY.get(
                b.get("af2_confidence", "UNVALIDATED"), 0
            ),
            b.get("ring5_rank_score", float("-inf")),
        ),
        reverse=True,
    )

    if not is_dry_run():
        with open(cfg.ring5_fasta, "w", encoding="utf-8") as f:
            for b in top:
                bid = b["binder_id"].split(" len=")[0]
                seq = b.get("sequence", "")
                length = b.get("length", len(seq))

                f.write(
                    f">{b['target']}|{bid} "
                    f"tier={b['candidate_tier']} len={length}\n"
                    f"{seq}\n"
                )

    save_json(cfg.ring5_json, top)

    counts = {}
    for b in decisions:
        tier = b["candidate_tier"]
        counts[tier] = counts.get(tier, 0) + 1

    log().info(
        "  Ring5候选分层: "
        + ", ".join(
            f"{k}={counts.get(k, 0)}"
            for k in (
                "PRIMARY",
                "SECONDARY",
                "EXPERIMENT_RESCUED",
                "REJECTED",
            )
        )
    )

    log().info(
        f"  输出 {len(top)} 条 Top binder "
        f"({len(by_target)} 靶点 × Top{top_n})"
    )
    log().info(f"  Decisions: {decisions_path}")
    log().info(f"  FASTA: {cfg.ring5_fasta}")
    log().info(f"  JSON:  {cfg.ring5_json}")

    if state is not None:
        state.set_artifact(5, "top", top)
        state.set_artifact(5, "decisions", decisions)
        state.mark_ring(
            5,
            "DONE",
            f"{len(top)} Top binders；"
            f"Primary={counts.get('PRIMARY', 0)}, "
            f"Secondary={counts.get('SECONDARY', 0)}, "
            f"Experimental={counts.get('EXPERIMENT_RESCUED', 0)}",
        )

    return top
