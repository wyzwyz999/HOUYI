"""HOUYI unified records.

把现有 Ring1 / Ring2 / Ring3 产物合并为统一 TargetRecord，
用于后续跨菌株、跨靶点的端到端数据传递。

本模块暂时只做兼容读取，不改写任何历史结果。
"""

from pathlib import Path
import json
import os
import time
import uuid

from .utils import load_json, is_dry_run, log


def build_target_records(cfg):
    """从现有 Ring1/2/3 JSON 构建统一 TargetRecord 列表。"""

    ring1 = load_json(cfg.ring1_out, default={}) or {}
    ring2 = load_json(cfg.ring2_out, default={}) or {}
    ring3 = load_json(cfg.ring3_out, default={}) or {}

    organism = ring1.get("organism")
    target_meta = ring1.get("target_meta", {}) or {}

    records = []

    for target_id in ring1.get("targets", []):
        meta = target_meta.get(target_id, {}) or {}
        struct = ring2.get(target_id, {}) or {}
        design = ring3.get(target_id, {}) or {}

        target_chain = (
            design.get("target_chain")
            or meta.get("pdb_chain")
            or "A"
        )

        binder_chain = (
            design.get("binder_chain")
            or meta.get("binder_chain")
            or "B"
        )

        hotspot_res = (
            design.get("hotspot_res")
            or meta.get("hotspot_res")
            or []
        )

        record = {
            "target_id": target_id,
            "organism": organism,

            # biological identity
            "gene": meta.get("gene"),
            "protein": meta.get("protein"),
            "mechanism_class": meta.get("mechanism_class"),
            "length_aa": meta.get("length_aa"),
            "uniprot": meta.get("uniprot"),
            "sequence": meta.get("sequence"),

            # target-selection metadata
            "function": meta.get("function"),
            "rationale": meta.get("rationale"),
            "design_strategy": meta.get("design_strategy"),
            "wetlab_status": meta.get("wetlab_status"),
            "note": meta.get("note"),

            # structure
            "pdb_id": struct.get("pdb") or meta.get("pdb"),
            "structure_source": struct.get("source"),
            "struct_path": struct.get("struct_path"),
            "target_chain": target_chain,
            "res_range": meta.get("res_range"),

            # design semantics
            "binder_chain": binder_chain,
            "hotspot_res": hotspot_res,

            # Ring3 output
            "design_source": design.get("source"),
            "design_out_dir": design.get("out_dir"),
            "n_binders": design.get("n_binders", 0),
        }

        records.append(record)

    return records


def target_record_map(cfg):
    """返回 target_id -> TargetRecord。"""
    return {
        r["target_id"]: r
        for r in build_target_records(cfg)
    }


def build_run_record(
    cfg,
    organism,
    targets,
    start,
    stop,
    skip,
    scorer,
    num_designs,
    mpnn_samples,
    af2_validate,
    af2_top_k,
    af2_models,
    af2_seeds,
    af2_recycles,
    dry_run=False,
    force_de_novo=False,
):
    """构建一次 HOUYI 调用的运行级 provenance 记录。"""

    ts = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"{ts}-{uuid.uuid4().hex[:8]}"

    return {
        "schema_version": 1,
        "run_id": run_id,
        "organism": organism,
        "targets": list(targets or []),

        "ring_range": {
            "start": start,
            "stop": stop,
            "skip": list(skip or []),
        },

        "parameters": {
            "scorer": scorer,
            "num_designs": num_designs,
            "mpnn_samples": mpnn_samples,
            "af2_validate": bool(af2_validate),
            "af2_top_k": af2_top_k,
            "af2_models": af2_models,
            "af2_seeds": af2_seeds,
            "af2_recycles": af2_recycles,
            "force_de_novo": bool(force_de_novo),
        },

        "dry_run": bool(dry_run),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "status": "RUNNING",

        "results_dir": cfg.results_dir,
        "state_path": cfg.state_path,
    }


def complete_run_record(record, status="COMPLETED"):
    """完成当前 RunRecord。"""
    record = dict(record)
    record["status"] = status
    record["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return record


def save_run_record(cfg, record):
    """保存 RunRecord；dry-run 下只预览，不落盘。"""

    run_id = record["run_id"]
    out_dir = os.path.join(cfg.results_dir, "runs")
    out_path = os.path.join(out_dir, f"{run_id}.json")

    if is_dry_run():
        log().info(
            f"  [dry-run] RunRecord: {run_id} "
            f"organism={record.get('organism')} "
            f"targets={record.get('targets')}"
        )
        return out_path

    os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            record,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log().info(f"RunRecord: {out_path}")
    return out_path
