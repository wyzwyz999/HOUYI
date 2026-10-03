"""HOUYI (后羿) —— 环 6：拼装载（payload 组装）。

把环5 输出的候选 binder 拼上先导肽，组装成可装入胞外注射系统（PVC）的载荷蛋白。

结构：Pdp1_NTD — linker — binder
  - Pdp1_NTD：先导肽（N 端引导头，把载荷装进 PVC）
  - linker  ：2xGGSGG 柔性连接子
  - binder  ：环5 输出的候选 binder（结合靶点的功能域）

产出：载荷蛋白氨基酸序列（FASTA + JSON），端到端最终交付物。
"""
from .utils import save_json, load_json, log, is_dry_run

# 先导肽 Pdp1_NTD（氨基酸序列，59 aa）
PDP1_NTD = "MPRYANYQINPKQNIKNSHGKSSSSDFSSGYLSFSNNSLDDPFIRQQVKREFIWEGHMKEIEEASRL"

# 2xGGSGG 柔性连接子（氨基酸序列，10 aa）
LINKER = "GGSGGGGSGG"


def build_payload(binder_sequence: str) -> str:
    """把 binder 序列拼成完整载荷：Pdp1_NTD + linker + binder。

    Args:
        binder_sequence: 候选 binder 的氨基酸序列（单字母）。

    Returns:
        str: 完整载荷氨基酸序列。
    """
    seq = (binder_sequence or "").strip().upper()
    if not seq:
        return PDP1_NTD + LINKER  # 无 binder 时仅输出引导头（异常兜底）
    return PDP1_NTD + LINKER + seq


def run(cfg, top=None, state=None):
    log().info("===== 环 6：拼装载（Pdp1_NTD-linker-binder）=====")

    if top is None:
        top = load_json(cfg.ring5_json)
        if not top:
            top = []

    if not top:
        # 无 binder：输出空产物，不崩溃
        log().warning("  无 binder 可拼装（环5 无 Top binder 输出）")
        save_json(cfg.ring6_json, [])
        if not is_dry_run():
            with open(cfg.ring6_fasta, "w", encoding="utf-8") as f:
                f.write("# 无载荷输出\n")
        if state is not None:
            state.set_artifact(6, "payloads", [])
            state.mark_ring(6, "DONE", "0 条载荷（无 binder）")
        return []

    # 逐条拼装载荷
    payloads = []
    for b in top:
        binder_seq = b.get("sequence", "")
        payload_seq = build_payload(binder_seq)
        payload = dict(b)  # 保留 binder 原始字段（target/binder_id/score 等）
        payload["payload_sequence"] = payload_seq
        payload["payload_length"] = len(payload_seq)
        payload["pdp1_ntd"] = PDP1_NTD
        payload["linker"] = LINKER
        payload["binder_sequence"] = binder_seq
        payloads.append(payload)

    # FASTA 输出（载荷序列）
    if not is_dry_run():
        with open(cfg.ring6_fasta, "w", encoding="utf-8") as f:
            for p in payloads:
                bid = p["binder_id"].split(" len=")[0]
                f.write(f">{p['target']}|{bid} len={p['payload_length']} payload\n"
                        f"{p['payload_sequence']}\n")

    save_json(cfg.ring6_json, payloads)

    log().info(f"  输出 {len(payloads)} 条载荷（Pdp1_NTD + linker + binder）")
    log().info(f"  FASTA: {cfg.ring6_fasta}")
    log().info(f"  JSON:  {cfg.ring6_json}")

    if state is not None:
        state.set_artifact(6, "payloads", payloads)
        state.mark_ring(6, "DONE", f"{len(payloads)} 条载荷生成")

    return payloads
