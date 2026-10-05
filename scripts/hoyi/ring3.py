"""HOUYI (后羿) —— 环 3：binder 设计。

两种模式：
  1. 复用模式：该细菌已有现成 binder 库（如金葡菌），直接加载。
  2. 从头设计：无 binder 库（如结核杆菌），真正调用 RFdiffusion 生成 binder 骨架。

产出：designed 映射（每靶点 binder 数量 + 来源 + 骨架目录）。
"""
import os
from .utils import load_json, save_json, log, emit_event
from .rf_designer import RFdiffusionDesigner


def run(cfg, targets, state=None, num_designs=32, dry_run=False):
    log().info("===== 环 3：binder 设计（RFdiffusion）=====")
    binder_lib = load_json(cfg.binder_lib_path) if cfg.binder_lib_path else None
    designed = {}

    if binder_lib:
        # ---- 复用模式 ----
        by_target = {}
        for b in binder_lib:
            by_target.setdefault(b["target"], []).append(b)
        log().info(f"  复用已有 binder 库: {len(binder_lib)} 条")
        for t in targets:
            if t in by_target:
                designed[t] = {"n_binders": len(by_target[t]), "source": "existing"}
                log().info(f"  {t}: 已有 {len(by_target[t])} 条 binder")
            else:
                designed[t] = {"n_binders": 0, "source": "to_design"}
                log().warning(f"  {t}: 无 binder，需真实 RFdiffusion 设计")
    else:
        # ---- 从头设计模式 ----
        log().info(f"  无 binder 库，进入从头设计（RFdiffusion）")
        designer = RFdiffusionDesigner(cfg)
        # 优先从环1 产物读靶点元信息（兼容自动检索），回退到知识库
        ring1 = load_json(cfg.ring1_out, default={})
        tmeta = ring1.get("target_meta", {})
        if not tmeta:
            kb = load_json(cfg.kb_path, default={"targets": {}})
            tmeta = kb.get("targets", {})
        # 环2 结构状态（含 struct_path，支持 Chai-1 预测结果）
        ring2 = load_json(cfg.ring2_out, default={})
        pdb_dir = os.path.join(cfg.data_dir, "pdbs",
                               _org_slug(cfg.data_source.get("kb", "")))

        total_targets = len(targets)

        def _emit_progress(done_targets, target, subtotal, subtotal_total, msg):
            """发布环2细粒度进度：{ring, current, total, percent, target, subtotal...}"""
            percent = int(done_targets * 100 / max(total_targets, 1))
            emit_event({
                "ring": 3, "ring_name": "Binder 设计", "status": "progress",
                "message": msg, "current": done_targets, "total": total_targets,
                "percent": percent, "target": target,
                "subtotal": subtotal, "subtotal_total": subtotal_total,
            })

        for idx, t in enumerate(targets):
            tinfo = tmeta.get(t, {})
            # 结构文件路径：优先用环2 产出（含 Chai-1 预测），回退到 pdb_id
            struct_path = (ring2.get(t, {}) or {}).get("struct_path")
            if not struct_path:
                pdb_id = tinfo.get("pdb")
                if not pdb_id:
                    designed[t] = {"n_binders": 0, "source": "no_structure"}
                    log().warning(f"  {t}: 无结构文件，跳过")
                    _emit_progress(idx + 1, t, 0, 0, f"{t}: 无结构文件，跳过")
                    continue
                struct_path = os.path.join(pdb_dir, f"{pdb_id}.pdb")

            pdb_path = struct_path
            out_dir = os.path.join(cfg.data_dir, "designs", _org_slug(cfg.data_source.get("kb", "")),
                                   t, "rfdiffusion")

            if not os.path.exists(pdb_path):
                designed[t] = {"n_binders": 0, "source": "pdb_missing"}
                log().warning(f"  {t}: 结构文件 {os.path.basename(pdb_path)} 不存在，跳过")
                _emit_progress(idx + 1, t, 0, 0, f"{t}: 结构文件缺失，跳过")
                continue

            if not dry_run:
                os.makedirs(out_dir, exist_ok=True)

            try:
                chain = tinfo.get("pdb_chain", "A")
                hotspot_res = tinfo.get("hotspot_res")
                # 进度回调：逐骨架推送
                def _cb(tid, done, total, _t=t):
                    _emit_progress(idx, _t, done, total,
                                   f"{_t}: 生成 {done}/{total} 骨架")
                res = designer.design(t, pdb_path, chain=chain,
                                      num_designs=num_designs,
                                      hotspot_res=hotspot_res,
                                      out_dir=out_dir, dry_run=dry_run,
                                      progress_cb=_cb)
                designed[t] = {"n_binders": res["n_scaffolds"],
                               "source": "rfdiffusion",
                               "out_dir": out_dir}
                _emit_progress(idx + 1, t, res["n_scaffolds"], num_designs,
                               f"{t}: 完成，{res['n_scaffolds']}/{num_designs} 骨架")
            except Exception as e:
                log().error(f"  {t}: RFdiffusion 失败: {e}")
                designed[t] = {"n_binders": 0, "source": "rf_error", "error": str(e)}
                _emit_progress(idx + 1, t, 0, num_designs, f"{t}: RFdiffusion 失败: {e}")
                if not dry_run:
                    # 单靶点失败不阻断整条管线（记录后继续）
                    continue

    save_json(cfg.ring3_out, designed)

    if state is not None:
        state.set_artifact(3, "designed", designed)
        n = sum(1 for v in designed.values() if v.get("n_binders", 0) > 0)
        state.mark_ring(3, "DONE", f"{n} 靶点有 binder")

    return designed


def _org_slug(kb_filename):
    """从知识库文件名推导细菌 slug（如 mtb_target_knowledge_base.json -> mtb）。"""
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
    return "sa"  # 默认金葡菌
