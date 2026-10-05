"""HOUYI (后羿) —— 环 4：评分排序（可插拔评分器架构）。

设计目标：让「评分」从硬编码的长度排序，升级为可扩展的评分器体系。

评分器（Scorer）接口：每个评分器输入 binder 列表，输出带 score 的排序结果。
当前内置：
  - LengthScorer   : 长度优先（40-90aa 迷你蛋白最优），fallback，零依赖
  - MicScorer      : MIC/MBC 湿实验标签优先（待接入准确数据）
  - MpnnEsmScorer  : ProteinMPNN 序列设计 + ESM-2 折叠质量（从头设计模式用）
"""
from .utils import load_json, save_json, log


class BaseScorer:
    name = "base"

    def score(self, binders):
        """输入 binder 列表，返回 (binder, score) 列表，按 score 降序。"""
        raise NotImplementedError


class LengthScorer(BaseScorer):
    name = "length"

    @staticmethod
    def _len_score(l):
        """40-90 aa 迷你蛋白区间给 0，越偏离 65 越差。"""
        if 40 <= l <= 90:
            return 0.0
        return float(-abs(l - 65))

    def score(self, binders):
        scored = []
        for b in binders:
            s = dict(b)
            s["score"] = self._len_score(b["length"])
            s["scorer"] = self.name
            scored.append(s)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored


class MicScorer(BaseScorer):
    """MIC/MBC 湿实验标签评分器。

    mic_map: {target_前缀: {"mic50": μg/mL, "mbc": μg/mL}}
    低 MIC（强活性）得高分。数据未接入时抛出，由调用方 fallback。
    """

    name = "mic"

    def __init__(self, mic_map):
        self.mic_map = mic_map

    def score(self, binders):
        # 归一化：MIC 越低分越高，用 1/MIC 并放大
        scored = []
        for b in binders:
            # 匹配靶点前缀（如 "E5_FemABX" 对应 "FemA"）
            mic = None
            for prefix, v in self.mic_map.items():
                if prefix.lower() in b["target"].lower():
                    mic = v
                    break
            if mic is None:
                s = dict(b)
                s["score"] = 0.0
                s["scorer"] = "mic_unscored"
            else:
                s = dict(b)
                # MIC50 越小越好，取负值使排序一致；MBC 全 100% 时仅作参考
                s["score"] = -float(mic["mic50"])
                s["scorer"] = self.name
                s["mic50"] = mic["mic50"]
                s["mbc"] = mic["mbc"]
            scored.append(s)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored


SCORER_REGISTRY = {
    "length": LengthScorer,
}


def get_scorer(name, **kwargs):
    if name == "length":
        return LengthScorer()
    if name == "mic":
        mic_map = kwargs.get("mic_map")
        if not mic_map:
            raise ValueError("MicScorer 需要 mic_map 参数")
        return MicScorer(mic_map)
    raise ValueError(f"未知评分器: {name}")


def run(cfg, targets=None, scorer_name="length", mic_map=None, state=None, dry_run=False):
    log().info(f"===== 环 4：评分排序（scorer={scorer_name}）=====")

    # 判断是否从头设计模式：ring3 产物里有 rfdiffusion 骨架目录
    ring3 = load_json(cfg.ring3_out, default={})
    rfd_targets = [t for t, v in ring3.items()
                   if isinstance(v, dict) and v.get("source") == "rfdiffusion" and v.get("out_dir")]

    if rfd_targets and scorer_name in ("length", "mpnn_esm", "esm", "mpnn"):
        # ---- 从头设计模式：ProteinMPNN + ESM 评分 -------
        from .mpnn_esm_scorer import MpnnEsmScorer
        scorer = MpnnEsmScorer(cfg)
        all_scored = []
        for t in rfd_targets:
            out_dir = ring3[t]["out_dir"]
            try:
                recs = scorer.run(out_dir, t, dry_run=dry_run)
            except Exception as e:
                log().error(f"  {t}: MPNN+ESM 评分失败: {e}")
                recs = []
            # 转成统一 binder 记录格式
            for r in recs:
                b = {
                    "target": t,
                    "binder_id": r["binder_id"],
                    "sequence": r["sequence"],
                    "length": r["length"],
                    "score": float(r["composite"]),
                    "scorer": "mpnn_esm",
                    "esm_composite": r["composite"],
                    "pLL": r["pLL"],
                    "emb_norm": r["emb_norm"],
                    "sampling_temp": r.get("sampling_temp"),
                    "sample": r.get("sample"),
                }
                all_scored.append(b)
        all_scored.sort(key=lambda x: x["score"], reverse=True)
        save_json(cfg.ring4_out, all_scored)
        if state is not None:
            state.set_artifact(4, "scored", all_scored)
            state.mark_ring(4, "DONE", f"{len(all_scored)} 条 binder 评分完成 (mpnn_esm)")
        return all_scored

    # ---- 现成库模式：原评分逻辑 ----
    binders = load_json(cfg.binder_lib_path) if cfg.binder_lib_path else None
    if not binders:
        # 该菌暂无 binder 库且无 RFdiffusion 产物
        log().warning(f"  ⚠️ 该细菌暂无 binder，跳过评分（需真实 RFdiffusion 设计）")
        save_json(cfg.ring4_out, [])
        if state is not None:
            state.set_artifact(4, "scored", [])
            state.mark_ring(4, "DONE", "0 条 binder（无 binder 库）")
        return []

    # 可选：只评指定靶点
    if targets:
        binders = [b for b in binders if b["target"] in targets]
        log().info(f"  过滤后 binder 数: {len(binders)}")

    # 选评分器（mic 数据缺失时 fallback 到 length）
    try:
        scorer = get_scorer(scorer_name, mic_map=mic_map)
    except ValueError as e:
        log().warning(f"  {e}，fallback 到 length 评分器")
        scorer = LengthScorer()

    scored = scorer.score(binders)
    log().info(f"  共 {len(scored)} 条 binder，已按 {scorer.name} 排序")

    save_json(cfg.ring4_out, scored)

    if state is not None:
        state.set_artifact(4, "scored", scored)
        state.mark_ring(4, "DONE", f"{len(scored)} 条 binder 评分完成 ({scorer.name})")

    return scored
