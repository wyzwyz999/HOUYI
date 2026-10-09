"""HOUYI (后羿) —— 环 4：评分排序（可插拔评分器架构）。

设计目标：让「评分」从硬编码的长度排序，升级为可扩展的评分器体系。

评分器（Scorer）接口：每个评分器输入 binder 列表，输出带 score 的排序结果。
当前内置：
  - LengthScorer   : 长度优先（40-90aa 迷你蛋白最优），fallback，零依赖
  - MicScorer      : MIC/MBC 湿实验标签优先（待接入准确数据）
  - MpnnEsmScorer  : ProteinMPNN 序列设计 + ESM-2 折叠质量（从头设计模式用）
"""
import os
import glob

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


def run(cfg, targets=None, scorer_name="length", mic_map=None, state=None,
        dry_run=False, mpnn_samples=3, designed=None):
    log().info(f"===== 环 4：评分排序（scorer={scorer_name}）=====")

    # 判断是否从头设计模式：ring3 产物里有 rfdiffusion 骨架目录
    ring3 = (
        designed
        if designed is not None
        else load_json(cfg.ring3_out, default={})
    )
    rfd_targets = [t for t, v in ring3.items()
                   if isinstance(v, dict) and v.get("source") == "rfdiffusion" and v.get("out_dir")]

    if rfd_targets and scorer_name in ("length", "mpnn_esm", "esm", "mpnn"):
        # ---- 从头设计模式：ProteinMPNN + ESM 评分 -------
        from .mpnn_esm_scorer import MpnnEsmScorer
        from .interface_geometry import analyze_interface
        from .records import target_record_map

        scorer = MpnnEsmScorer(cfg)
        all_scored = []
        ring35_manifest = {}

        # Ring3.5统一从 TargetRecord 读取元数据。
        # records.py负责兼容旧Ring1/Ring2/Ring3历史产物，
        # Ring4不再自行拼接KB/chain/hotspot。
        records = target_record_map(cfg)

        for t in rfd_targets:
            rec = records.get(t)
            if not rec:
                raise ValueError(
                    f"{t} 缺少 TargetRecord，无法进入 Ring3.5/Ring4"
                )

            out_dir = rec.get("design_out_dir")
            if not out_dir:
                raise ValueError(
                    f"{t} TargetRecord 缺少 design_out_dir"
                )

            target_chain = rec.get("target_chain")
            binder_chain = rec.get("binder_chain")
            hotspot_raw = rec.get("hotspot_res") or []

            if not target_chain:
                raise ValueError(
                    f"{t} TargetRecord 缺少 target_chain"
                )

            if not binder_chain:
                raise ValueError(
                    f"{t} TargetRecord 缺少 binder_chain"
                )

            # ---- Ring3.5：interface geometry gate ----
            # v1只过滤明确没有界面的backbone；
            # hotspot用于记录/后续soft score，不参与当前hard gate。

            hotspot_res = []
            for h in hotspot_raw or []:
                try:
                    # 例如 A123 -> 123
                    hotspot_res.append(
                        int("".join(c for c in str(h) if c.isdigit()))
                    )
                except Exception:
                    pass

            log().info(
                f"  {t}: Ring3.5 hotspot_res="
                f"{hotspot_raw or []}"
            )

            pdbs = sorted([
                f for f in glob.glob(os.path.join(out_dir, "*.pdb"))
                if "traj" not in f
                and not f.endswith(f"_{binder_chain}.pdb")
                and "cont" not in f
            ])

            allowed_pdb_names = []
            interface_records = []
            interface_by_backbone = {}

            for pdb in pdbs:
                try:
                    geom = analyze_interface(
                        pdb,
                        target_chain=target_chain,
                        hotspot_res=hotspot_res,
                    )
                    geom["pdb_name"] = os.path.basename(pdb)
                    interface_records.append(geom)

                    backbone_name = os.path.splitext(
                        os.path.basename(pdb)
                    )[0]
                    interface_by_backbone[backbone_name] = geom

                    if geom.get("hard_pass"):
                        allowed_pdb_names.append(
                            os.path.basename(pdb)
                        )

                except Exception as e:
                    log().warning(
                        f"  {t}: Ring3.5几何分析失败 "
                        f"{os.path.basename(pdb)}: {e}"
                    )

            ring35_manifest[t] = {
                "target_id": t,
                "organism": rec.get("organism"),
                "out_dir": out_dir,
                "target_chain": target_chain,
                "binder_chain": binder_chain,
                "hotspot_res": hotspot_raw,
                "num_backbones": len(pdbs),
                "num_pass": len(allowed_pdb_names),
                "allowed_pdb_names": allowed_pdb_names,
                "interfaces": interface_records,
            }

            log().info(
                f"  {t}: Ring3.5 interface gate "
                f"{len(pdbs)} -> {len(allowed_pdb_names)} 骨架"
            )

            try:
                recs = scorer.run(
                    out_dir,
                    t,
                    num_seq_per_target=mpnn_samples,
                    dry_run=dry_run,
                    allowed_pdb_names=allowed_pdb_names,
                    binder_chain=binder_chain,
                )
            except Exception as e:
                log().error(f"  {t}: MPNN+ESM 评分失败: {e}")
                recs = []
            # 转成统一 binder 记录格式
            for r in recs:
                binder_id = r["binder_id"]

                # binder_id:
                # GENERIC_TARGET__4_B_T0.2_sample5
                # -> backbone:
                # GENERIC_TARGET__4
                chain_tag = f"_{binder_chain}_"
                backbone_name = (
                    binder_id.split(chain_tag, 1)[0]
                    if chain_tag in binder_id
                    else None
                )

                geom = (
                    interface_by_backbone.get(backbone_name, {})
                    if backbone_name
                    else {}
                )

                b = {
                    "target": t,
                    "binder_id": binder_id,
                    "backbone": backbone_name,
                    "sequence": r["sequence"],
                    "length": r["length"],
                    "score": float(
                        r.get("qc_composite", r["composite"])
                    ),
                    "scorer": "mpnn_esm_qc",
                    "esm_composite": r["composite"],
                    "pLL": r["pLL"],
                    "emb_norm": r["emb_norm"],
                    "qc_composite": r.get("qc_composite", r["composite"]),
                    "ekr_frac": r.get("ekr_frac"),
                    "unique_aa": r.get("unique_aa"),
                    "complexity_penalty": r.get("complexity_penalty"),
                    "sampling_temp": r.get("sampling_temp"),
                    "sample": r.get("sample"),

                    # Ring3.5 interface geometry metadata
                    # 当前仅记录，不参与score。
                    "interface_hard_pass": geom.get("hard_pass"),
                    "interface_min_dist": geom.get("min_dist"),
                    "interface_contacts_6A": geom.get("contacts_6A"),
                    "interface_target_res": geom.get("target_if_res"),
                    "interface_binder_res": geom.get("binder_if_res"),
                    "interface_hotspot_contacts": geom.get(
                        "hotspot_contacts_total"
                    ),
                    "interface_hotspot_min_dist": geom.get(
                        "hotspot_min_dist"
                    ),
                }
                all_scored.append(b)
        all_scored.sort(
            key=lambda x: x.get(
                "qc_composite",
                x.get("score", float("-inf")),
            ),
            reverse=True,
        )

        ring35_out = os.path.join(
            str(cfg.results_dir),
            "ring3_5_interface.json",
        )
        save_json(ring35_out, ring35_manifest)
        if dry_run:
            log().info(
                f"  [dry-run] Ring3.5 manifest 未写盘: {ring35_out}"
            )
        else:
            log().info(
                f"  Ring3.5 manifest 已保存: {ring35_out}"
            )

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
