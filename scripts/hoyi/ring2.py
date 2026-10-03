"""HOUYI (后羿) —— 环 2：结构预测（Phase 5）。

真正拿到结构文件（不再只是"标记来源"）：
  - 有 PDB → 自动下载结构到 data/pdbs/<org>/
  - 无 PDB → 自动 Chai-1 预测结构

产出：struct_status 映射，含每靶点的结构文件路径。
"""
import os
from .utils import load_json, save_json, log, emit_event
from .structure_predictor import StructurePredictor


def _org_slug(kb_filename):
    base = os.path.basename(kb_filename or "")
    for kw in ["mtb", "tuberculosis", "mycobacterium"]:
        if kw in base.lower():
            return "mtb"
    for kw in ["ab", "acinetobacter", "baumannii"]:
        if kw in base.lower():
            return "ab"
    for kw in ["kp", "klebsiella", "pneumoniae"]:
        if kw in base.lower():
            return "kp"
    return "sa"


def run(cfg, targets, state=None, dry_run=False):
    log().info("===== 环 2：结构预测 =====")

    # 优先从环1 产物读靶点元信息（兼容自动检索）
    ring1 = load_json(cfg.ring1_out, default={})
    target_meta = ring1.get("target_meta", {})
    if not target_meta:
        kb = load_json(cfg.kb_path, default={"targets": {}})
        target_meta = kb.get("targets", {})

    pdb_dir = os.path.join(cfg.data_dir, "pdbs", _org_slug(cfg.data_source.get("kb", "")))
    os.makedirs(pdb_dir, exist_ok=True)

    predictor = StructurePredictor(cfg)
    struct_status = {}
    total = len(targets)

    for idx, t in enumerate(targets):
        tinfo = target_meta.get(t, {})
        pdb_id = tinfo.get("pdb")
        percent = int(idx * 100 / max(total, 1))
        emit_event({
            "ring": 2, "ring_name": "结构预测", "status": "progress",
            "message": f"{t}: 处理中...", "current": idx, "total": total,
            "percent": percent, "target": t,
        })

        if pdb_id:
            # 有 PDB：下载结构文件
            if dry_run:
                struct_status[t] = {"pdb": pdb_id, "source": "known_template",
                                    "struct_path": os.path.join(pdb_dir, f"{pdb_id}.pdb")}
                log().info(f"  {t}: [dry-run] 将下载 PDB {pdb_id}")
            else:
                path = predictor.download_pdb(pdb_id, pdb_dir)
                if path:
                    struct_status[t] = {"pdb": pdb_id, "source": "downloaded_pdb",
                                        "struct_path": path}
                    log().info(f"  {t}: 已下载 PDB {pdb_id}")
                else:
                    struct_status[t] = {"pdb": pdb_id, "source": "pdb_download_failed"}
                    log().warning(f"  {t}: PDB {pdb_id} 下载失败")
        else:
            # 无 PDB：Chai-1 预测
            seq = tinfo.get("sequence", "")
            if not seq:
                # 尝试从靶点序列文件读
                seq = _get_sequence(cfg, t)
            if not seq:
                struct_status[t] = {"pdb": None, "source": "no_sequence"}
                log().warning(f"  {t}: 无 PDB 且无序列，无法预测")
                continue

            if dry_run:
                struct_status[t] = {"pdb": None, "source": "chai1_prediction"}
                log().info(f"  {t}: [dry-run] 将 Chai-1 预测（{len(seq)}aa）")
            else:
                path = predictor.predict_chai1(seq, t, pdb_dir)
                if path:
                    struct_status[t] = {"pdb": None, "source": "chai1_predicted",
                                        "struct_path": path}
                    log().info(f"  {t}: Chai-1 预测完成")
                else:
                    struct_status[t] = {"pdb": None, "source": "chai1_failed"}
                    log().warning(f"  {t}: Chai-1 预测失败")

        emit_event({
            "ring": 2, "ring_name": "结构预测", "status": "progress",
            "message": f"{t}: 完成（{struct_status[t]['source']}）",
            "current": idx + 1, "total": total,
            "percent": int((idx + 1) * 100 / max(total, 1)), "target": t,
        })

    n_known = sum(1 for v in struct_status.values()
                  if v["source"] in ("known_template", "downloaded_pdb", "chai1_predicted"))
    save_json(cfg.ring2_out, struct_status)

    if state is not None:
        state.set_artifact(2, "structure", struct_status)
        state.mark_ring(2, "DONE", f"{n_known}/{len(targets)} 结构就绪")

    return struct_status


def _get_sequence(cfg, target_id):
    """从靶点序列文件读序列（回退）。"""
    seq_file = cfg.antigens_path
    data = load_json(seq_file, default={})
    if isinstance(data, dict) and target_id in data:
        return data[target_id].get("sequence", "")
    return ""
