"""HOUYI (后羿) —— 端到端纳米注射器设计平台。

模块化重构版，解决旧版 pipeline.py 的工程问题：
  - 真断点续跑（每环产物独立落盘）
  - 异常处理（失败不崩溃，记录 ERROR 状态）
  - dry-run 预览
  - 可插拔评分器（length / mic / 未来 mpnn/esm）

环编号（1-based，十环）：
  环1 靶点分析 → 环2 结构预测 → 环3 Binder 设计 → 环4 评分排序
  → 环5 输出 binder → 环6 拼装载（Pdp1_NTD-linker-binder）
  → 环7 尾纤维靶点分析 → 环8 尾纤维 binder/天然结构域筛选
  → 环9 重编程 pvc13 → 环10 纳米注射器总装
"""
import os

from .config import Config
from .utils import State, load_json, save_json, log, CommandError, emit_event
from . import ring1, ring2, ring3, ring4, ring5, ring6, ring7, ring8, ring9, ring10

__all__ = ["Config", "State", "run_pipeline"]


RING_NAMES = {
    1: "靶点分析", 2: "结构预测", 3: "Binder 设计",
    4: "评分排序", 5: "输出 binder", 6: "拼装载",
    7: "尾纤维靶点分析", 8: "尾纤维 binder 筛选",
    9: "重编程 pvc13", 10: "注射器总装",
}


def run_pipeline(cfg: Config, organism: str, targets=None,
                 start=1, stop=10, skip=None, dry_run=False,
                 scorer="length", mic_map=None, top_n=3, num_designs=32,
                 mpnn_samples=3,
                 af2_validate=False,
                 af2_top_k=3,
                 af2_models=5,
                 af2_seeds=3,
                 af2_recycles=6,
                 force_de_novo=False,
    auto_top_n_targets=1,
    allow_unreviewed=False,
    resilient=True):
    """执行十环管线，返回状态数据。

    环1 靶点分析 → 环2 结构预测 → 环3 Binder 设计 → 环4 评分排序
    → 环5 输出 binder → 环6 拼装载（Pdp1_NTD-linker-binder）
    → 环7 尾纤维靶点分析 → 环8 尾纤维 binder/天然结构域筛选
    → 环9 重编程 pvc13 → 环10 纳米注射器总装

    Args:
        cfg: 配置
        organism: 病原菌名
        targets: 指定靶点（None=全部）
        start/stop: 环范围 [start, stop]（1-based）
        skip: 跳过的环列表
        dry_run: 仅预览
        scorer: 环 4 评分器名
        mic_map: MIC 湿实验数据（供 mic 评分器）
        top_n: 每靶点 Top N
        num_designs: 环 3 每靶点 RFdiffusion 骨架数
        mpnn_samples: 环 4 每骨架、每采样温度的 ProteinMPNN 序列数
        af2_validate: 是否在环4后进行 AF2-Multimer 验证
        allow_unreviewed: reviewed 为 0 时是否回落到 TrEMBL（默认关闭）
        af2_top_k: 每靶点进入 AF2 的候选数
        af2_models: AF2 model 数
        af2_seeds: AF2 seed 数
        af2_recycles: AF2 recycle 数
    """
    skip = skip or []
    cfg.set_organism(organism)  # 先确定菌种，确保 results_dir 按菌隔离
    cfg.ensure_dirs()
    from .utils import set_dry_run, ensure_clean_organism
    set_dry_run(dry_run)
    # 检测 organism 变更并清理跨菌种残留（避免 KP 残留污染金葡菌等）
    ensure_clean_organism(cfg, organism)
    state = State(cfg)

    # -----------------------------------------------------------------
    # 端到端容错（2026-10-24）
    # 目标：输入菌名后 1-10 环一定跑到底，不因某一环失败而整体中止。
    #   - 失败环节标记 ERROR，并记入 run_summary.json
    #   - 依赖该环节的下游标 SKIPPED_UPSTREAM（避免拿空产物去算垃圾）
    #   - AF2(4.5) 失败只跳过验证，不阻断环5-10
    #   - 需要旧行为（失败即停）：HOUYI_STRICT_PIPELINE=1 或 resilient=False
    # -----------------------------------------------------------------
    strict_pipeline = (
        os.environ.get("HOUYI_STRICT_PIPELINE", "0") == "1"
        or not resilient
    )

    def ring_status(n):
        return ((state.data.get("rings", {}) or {}).get(str(n)) or {}).get("status")

    def dep_failed(n, deps):
        for d in deps:
            if ring_status(d) in ("ERROR", "SKIPPED_UPSTREAM"):
                state.mark_ring(n, "SKIPPED_UPSTREAM", f"上游环 {d} 未成功")
                emit(n, "skipped", f"跳过：上游环 {d} 未成功")
                log().warning(f"  环 {n} 跳过：上游环 {d} 未成功")
                return True
        return False

    def artifact_of(current, ring, loader):
        """取本次产物；若该环本次失败/被阻塞，返回空，禁止拿上一轮旧文件冒充。"""
        if ring_status(ring) in ("ERROR", "SKIPPED_UPSTREAM", "SKIPPED_NO_PAYLOAD"):
            return []
        if current is not None:
            return current
        return loader() or []

    def payload_ready():
        """环6 是否真正产出了载荷。

        没有载荷时，尾纤维（环8/9）和总装（环10）没有任何意义：
        注射器 = 载荷 + 靶向模块，缺一个都组装不出来。所以这里直接掐断，
        避免像以前那样白跑 30-60 分钟的 Chai-1 + RFdiffusion。
        需要单独研究尾纤维时，可设 HOUYI_ALLOW_FIBER_WITHOUT_PAYLOAD=1 强制继续。
        """
        if os.environ.get("HOUYI_ALLOW_FIBER_WITHOUT_PAYLOAD", "0") == "1":
            return True
        return bool(
            artifact_of(payloads_current, 6, lambda: load_json(cfg.ring6_json))
        )

    # 本次run_pipeline内的显式内存产物。
    # 同次运行优先使用这些对象，只有断点续跑时才回退读取JSON。
    designed_current = None
    scored_current = None
    top_current = None
    payloads_current = None
    fiber_targets_current = None
    fiber_binders_current = None
    fibers_current = None

    def emit(ring, status, message):
        emit_event({"ring": ring, "ring_name": RING_NAMES.get(ring, ""),
                    "status": status, "message": message})

    emit(-1, "start", f"开始执行：{organism}")
    log().info("=" * 50)
    log().info("HOUYI (后羿) 抗菌载荷设计平台")
    log().info(f"输入病原菌: {organism}")
    log().info(f"环范围: {start} -> {stop}，跳过: {skip}")
    log().info(f"评分器: {scorer}" + (" [dry-run]" if dry_run else ""))
    log().info("=" * 50)

    def should_run(ring):
        return start <= ring <= stop and ring not in skip

    # ---- 环 1：靶点分析 ----
    if should_run(1):
        emit(1, "running", "环 1：靶点分析")
        try:
            ring1.run(
                cfg,
                organism,
                targets,
                state,
                dry_run=dry_run,
                auto_top_n_targets=auto_top_n_targets,
                allow_unreviewed=allow_unreviewed,
            )
            targets = state.get_artifact(1, "targets", [])
            emit(1, "done", f"完成：推导出 {len(targets)} 个靶点")
        except Exception as e:
            log().error(f"环 1 失败: {e}")
            state.mark_ring(1, "ERROR", str(e))
            emit(1, "error", f"环 1 失败: {e}")
            if not dry_run and strict_pipeline:
                raise
    else:
        targets = targets or state.get_artifact(1, "targets", [])
        if not targets:
            kb = load_json(cfg.kb_path)
            targets = list(kb["targets"].keys()) if kb else []
        log().info(f"环 1 跳过，使用靶点: {targets}")
        emit(1, "skipped", f"跳过（复用 {len(targets)} 个靶点）")

    # ---- 本次运行 provenance ----
    # TargetRecord 描述靶点；RunRecord 描述这一次管线如何运行。
    from .records import build_run_record, save_run_record, complete_run_record

    run_record = build_run_record(
        cfg=cfg,
        organism=organism,
        targets=targets,
        start=start,
        stop=stop,
        skip=skip,
        scorer=scorer,
        num_designs=num_designs,
        mpnn_samples=mpnn_samples,
        af2_validate=af2_validate,
        af2_top_k=af2_top_k,
        af2_models=af2_models,
        af2_seeds=af2_seeds,
        af2_recycles=af2_recycles,
        dry_run=dry_run,
        force_de_novo=force_de_novo,
    )

    # dry-run只打印预览；真实运行先保存RUNNING记录。
    save_run_record(cfg, run_record)

    # ---- 环 2：结构预测 ----
    if should_run(2) and not dep_failed(2, (1,)):
        emit(2, "running", "环 2：结构预测")
        try:
            ring2.run(cfg, targets, state, dry_run=dry_run)
            emit(2, "done", "完成：结构来源已确定")
        except Exception as e:
            log().error(f"环 2 失败: {e}")
            state.mark_ring(2, "ERROR", str(e))
            emit(2, "error", f"环 2 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 3：Binder 设计 ----
    if should_run(3) and not dep_failed(3, (1, 2)):
        emit(3, "running", "环 3：Binder 设计")
        try:
            designed_current = ring3.run(
                cfg,
                targets,
                state,
                dry_run=dry_run,
                num_designs=num_designs,
                force_de_novo=force_de_novo,
            )
            emit(3, "done", "完成：binder 骨架已生成")
        except Exception as e:
            log().error(f"环 3 失败: {e}")
            state.mark_ring(3, "ERROR", str(e))
            emit(3, "error", f"环 3 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 4：评分排序 ----
    if should_run(4) and not dep_failed(4, (3,)):
        emit(4, "running", "环 4：评分排序")
        scored_current = []
        try:
            scored_current = ring4.run(
                cfg,
                targets,
                scorer,
                mic_map=mic_map,
                state=state,
                dry_run=dry_run,
                mpnn_samples=mpnn_samples,
                designed=designed_current if should_run(3) else None,
            )
            emit(4, "done", "完成：binder 评分排序")
        except Exception as e:
            log().error(f"环 4 失败: {e}")
            state.mark_ring(4, "ERROR", str(e))
            emit(4, "error", f"环 4 失败: {e}")
            if not dry_run and strict_pipeline:
                raise


    # 本次运行的 AF2 -> Ring5 显式交接结果。
    # 保存全部AF2验证结果（包括未通过者），
    # 由Ring5多证据决策层完成Primary/Secondary分层。
    af2_results_for_ring5 = [] if af2_validate else None

    # ---- 环 4.5：AF2-Multimer 验证 ----
    if af2_validate and (should_run(4) or should_run(5)):
        try:
            log().info("环 4.5：AF2-Multimer 验证")

            from pathlib import Path
            from .af2_validator import AF2Validator
            from .records import target_record_map

            scored = (
                scored_current
                if should_run(4)
                else load_json(cfg.ring4_out)
            )
            records = target_record_map(cfg)

            if not scored:
                msg = f"AF2验证失败：未找到 Ring4 候选 {cfg.ring4_out}"
                if dry_run:
                    log().warning(msg)
                else:
                    raise FileNotFoundError(msg)

            elif not records:
                msg = "AF2验证失败：未找到 TargetRecord"
                if dry_run:
                    log().warning(msg)
                else:
                    raise FileNotFoundError(msg)

            else:
                validator = AF2Validator(cfg)
                all_validated = []

                for target in sorted({
                    c.get("target") for c in scored
                    if c.get("target")
                }):
                    rec = records.get(target)
                    if not rec:
                        raise ValueError(
                            f"{target} 缺少 TargetRecord"
                        )

                    pdb_path = rec.get("struct_path")
                    chain = rec.get("target_chain")

                    if not pdb_path:
                        raise ValueError(
                            f"{target} TargetRecord 缺少 struct_path"
                        )
                    if not chain:
                        raise ValueError(
                            f"{target} TargetRecord 缺少 target_chain"
                        )

                    target_candidates = [
                        c for c in scored
                        if c.get("target") == target
                    ]

                    work_dir = (
                        Path(cfg.results_dir)
                        / "af2_validation"
                        / target
                    )

                    validated = validator.validate_selected_candidates(
                        candidates=target_candidates,
                        target_pdb=pdb_path,
                        target_chain=chain,
                        top_k=af2_top_k,
                        work_dir=work_dir,
                        num_models=af2_models,
                        num_seeds=af2_seeds,
                        num_recycles=af2_recycles,
                        reuse_existing=True,
                        dry_run=dry_run,
                        save_output=False,
                    )

                    all_validated.extend(validated)

                if not dry_run:
                    passed = validator.save_validated(all_validated)
                    af2_results_for_ring5 = all_validated
                    log().info(
                        f"AF2验证完成：{len(all_validated)} 条完成验证，"
                        f"{len(passed)} 条通过；全部结果交给Ring5多证据决策"
                    )
                else:
                    af2_results_for_ring5 = all_validated
                    n_passed = sum(
                        1 for c in all_validated
                        if c.get("af2_validation", {}).get("passed")
                    )
                    log().info(
                        f"[dry-run] AF2候选: {len(all_validated)} 条，"
                        f"通过: {n_passed} 条；全部结果交给Ring5预览"
                    )

        except Exception as e:
            af2_results_for_ring5 = None
            # 不覆盖环4 的 DONE 状态，单独记录 AF2 子环节
            try:
                state.data.setdefault("ring4_5", {})
                state.data["ring4_5"]["status"] = "SKIPPED"
                state.data["ring4_5"]["error"] = f"{type(e).__name__}: {e}"
            except Exception:
                pass
            emit(4, "error", f"环 4.5 AF2 验证失败，已跳过: {e}")
            log().warning(
                "环 4.5 AF2 验证失败，已跳过验证并继续环5-10: "
                f"{type(e).__name__}: {e}"
            )
            if not dry_run and strict_pipeline:
                raise
    # ---- 环 5：输出 binder ----
    if should_run(5) and not dep_failed(5, (4,)):
        emit(5, "running", "环 5：输出 Top binder")
        try:
            # 若本次显式启用了AF2，直接使用本次AF2阶段结果，
            # 避免读取旧的ring4_af2_validated.json。
            # 未启用AF2时仍由Ring5自行处理断点续跑/历史validated回退逻辑。
            top_current = ring5.run(
                cfg,
                scored=scored_current if should_run(4) else None,
                af2_results=af2_results_for_ring5,
                top_n=top_n,
                state=state,
            )
            emit(5, "done", "完成：Top binder 已输出")
        except Exception as e:
            log().error(f"环 5 失败: {e}")
            state.mark_ring(5, "ERROR", str(e))
            emit(5, "error", f"环 5 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 6：拼装载 ----
    if should_run(6) and not dep_failed(6, (5,)):
        emit(6, "running", "环 6：拼装载（Pdp1_NTD-linker-binder）")
        try:
            top = (
                top_current
                if should_run(5)
                else load_json(cfg.ring5_json)
            )
            payloads_current = ring6.run(
                cfg,
                top=top,
                state=state,
            )
            emit(6, "done", "完成：载荷已生成")
        except Exception as e:
            log().error(f"环 6 失败: {e}")
            state.mark_ring(6, "ERROR", str(e))
            emit(6, "error", f"环 6 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 7：尾纤维靶点分析 ----
    if should_run(7):
        emit(7, "running", "环 7：尾纤维靶点分析")
        try:
            fiber_targets_current = ring7.run(
                cfg,
                state=state,
                dry_run=dry_run,
                allow_unreviewed=allow_unreviewed,
            )
            emit(7, "done", "完成：尾纤维靶点已打分排序")
        except Exception as e:
            log().error(f"环 7 失败: {e}")
            state.mark_ring(7, "ERROR", str(e))
            emit(7, "error", f"环 7 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 8：尾纤维 binder/天然结构域筛选 ----
    if should_run(8) and not payload_ready():
        state.mark_ring(8, "SKIPPED_NO_PAYLOAD", "环6 无载荷，跳过尾纤维 binder 设计")
        emit(8, "skipped", "跳过：环6 无载荷")
        log().warning(
            "  环8 跳过：环6 无载荷（上游靶点被排除），不再设计尾纤维"
            "（如确需单独研究尾纤维，设 HOUYI_ALLOW_FIBER_WITHOUT_PAYLOAD=1）"
        )
    elif should_run(8) and not dep_failed(8, (7,)):
        emit(8, "running", "环 8：尾纤维 binder/天然结构域筛选")
        try:
            fiber_targets = (
                fiber_targets_current
                if should_run(7)
                else load_json(cfg.ring7_out)
            )
            fiber_binders_current = ring8.run(
                cfg,
                fiber_targets=fiber_targets,
                state=state,
                num_designs=num_designs,
                mpnn_samples=mpnn_samples,
                dry_run=dry_run,
            )
            emit(8, "done", "完成：尾纤维 binder/结构域已筛选")
        except Exception as e:
            log().error(f"环 8 失败: {e}")
            state.mark_ring(8, "ERROR", str(e))
            emit(8, "error", f"环 8 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 9：重编程 pvc13 ----
    if should_run(9) and not payload_ready():
        state.mark_ring(9, "SKIPPED_NO_PAYLOAD", "环6 无载荷，跳过 pvc13 重编程")
        emit(9, "skipped", "跳过：环6 无载荷")
        log().warning("  环9 跳过：环6 无载荷，不做 pvc13 重编程")
    elif should_run(9) and not dep_failed(9, (8,)):
        emit(9, "running", "环 9：重编程 pvc13（N-binder-C）")
        try:
            fiber_binders = (
                fiber_binders_current
                if should_run(8)
                else load_json(cfg.ring8_out)
            )
            fibers_current = ring9.run(
                cfg,
                fiber_binders=fiber_binders,
                state=state,
            )
            emit(9, "done", "完成：重编程尾纤维已生成")
        except Exception as e:
            log().error(f"环 9 失败: {e}")
            state.mark_ring(9, "ERROR", str(e))
            emit(9, "error", f"环 9 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # ---- 环 10：纳米注射器总装（PVC 完整重设计） ----
    def fibers_available():
        return bool(
            artifact_of(fibers_current, 9, lambda: load_json(cfg.ring9_out))
        )

    if should_run(10) and not payload_ready() and not fibers_available():
        state.mark_ring(
            10, "SKIPPED_NO_PAYLOAD",
            "既无载荷也无尾纤维，跳过总装（避免用空结果覆盖历史产物）",
        )
        emit(10, "skipped", "跳过：无载荷/无尾纤维")
        log().warning(
            "  环10 跳过：既无载荷也无尾纤维，不写出空的 nanosyringes.json"
        )
    elif should_run(10):
        emit(10, "running", "环 10：纳米注射器总装（PVC 完整重设计）")
        try:
            payloads = artifact_of(
                payloads_current, 6, lambda: load_json(cfg.ring6_json)
            )
            fibers = artifact_of(
                fibers_current, 9, lambda: load_json(cfg.ring9_out)
            )
            ring10.run(
                cfg,
                payloads=payloads,
                reprogrammed_fibers=fibers,
                state=state,
            )
            emit(10, "done", "完成：纳米注射器规格已生成")
        except Exception as e:
            log().error(f"环 10 失败: {e}")
            state.mark_ring(10, "ERROR", str(e))
            emit(10, "error", f"环 10 失败: {e}")
            if not dry_run and strict_pipeline:
                raise

    # -----------------------------------------------------------------
    # 运行总结：每环状态 + 质量分层 + 交付物路径
    # -----------------------------------------------------------------
    rings_status = {}
    for i in range(1, 11):
        r = (state.data.get("rings", {}) or {}).get(str(i), {}) or {}
        if not (start <= i <= stop) or i in skip:
            # 本次没跑的环节：不要拿上一轮的 DONE 冒充本次结果
            rings_status[str(i)] = {
                "name": RING_NAMES.get(i, ""),
                "status": "NOT_IN_RANGE",
                "info": "",
            }
            continue
        rings_status[str(i)] = {
            "name": RING_NAMES.get(i, ""),
            "status": r.get("status"),
            "info": r.get("info"),
        }

    bad = [
        i for i, v in rings_status.items()
        if v["status"] in ("ERROR", "SKIPPED_UPSTREAM", "SKIPPED_NO_PAYLOAD")
    ]

    # 有没有真正产出交付物（注射器规格）——没有产出就不算"部分完成"
    try:
        _syr = load_json(cfg.ring10_json, default=[]) or []
    except Exception:
        _syr = []
    has_deliverable = bool(_syr)

    if not bad:
        overall = "COMPLETED"
    elif has_deliverable:
        overall = "PARTIAL"
    else:
        overall = "FAILED"

    quality = {}
    try:
        # 只采信本次真正跑成功的环节，避免把上一轮的旧产物当成这次的质量结论
        r7 = (
            load_json(cfg.ring7_out, default=[]) or []
            if rings_status["7"]["status"] in ("DONE", "SKIPPED")
            else []
        )
        if r7:
            quality["fiber_tier"] = r7[0].get("quality_tier")
            quality["fiber_target"] = r7[0].get("fiber_target")
        kinds = {}
        for x in r7:
            t = x.get("quality_tier") or "unknown"
            kinds[t] = kinds.get(t, 0) + 1
        if kinds:
            quality["fiber_tier_counts"] = kinds

        r10 = (
            load_json(cfg.ring10_json, default=[]) or []
            if rings_status["10"]["status"] in ("DONE", "SKIPPED")
            else []
        )
        if r10:
            quality["nanosyringes"] = len(r10)
            quality["nanosyringes_complete"] = sum(
                1 for x in r10 if x.get("complete")
            )
            quality["nanosyringes_complete_strict"] = sum(
                1 for x in r10 if x.get("complete_strict")
            )
    except Exception as e:  # 汇总失败不影响主流程
        log().warning(f"run_summary 质量字段收集失败: {e}")

    summary = {
        "organism": organism,
        "run_id": run_record["run_id"],
        "overall_status": overall,
        "rings": rings_status,
        "blocked_or_failed": bad,
        "quality": quality,
        "deliverables": {
            "nanosyringes_json": cfg.ring10_json,
            "nanosyringes_fasta": cfg.ring10_fasta,
            "reprogrammed_fibers": cfg.ring9_out,
            "targets": cfg.ring1_out,
            "state": cfg.state_path,
        },
    }
    summary_path = os.path.join(cfg.results_dir, "run_summary.json")
    save_json(summary_path, summary)

    log().info("-" * 50)
    log().info(f"运行总结: {overall}")
    for i in range(1, 11):
        v = rings_status[str(i)]
        if v["status"]:
            log().info(f"  环{i:<2} {v['status']:<18} {v.get('info') or ''}")
    if quality:
        log().info(f"  质量分层: {quality}")
    log().info(f"  总结文件: {summary_path}")
    log().info("-" * 50)

    run_record = complete_run_record(
        run_record,
        status=overall,
    )
    save_run_record(cfg, run_record)

    emit(-1, "finish", f"管线执行结束: {overall}")
    log().info("=" * 50)
    if overall == "COMPLETED":
        log().info("管线执行完成（成功）")
    elif overall == "PARTIAL":
        log().info("管线执行完成，但存在失败/跳过的环节 → PARTIAL")
        log().info("  有产物但证据不全，详见上方“运行总结”与 run_summary.json")
    else:
        log().info("管线执行结束，但结果失败 → FAILED")
        log().info("  没有产出可用结果；失败原因见上方各环状态（环1/环7 出错会连带下游跳过）")
    log().info(f"Run ID: {run_record['run_id']}")
    log().info(f"状态文件: {cfg.state_path}")
    log().info("=" * 50)
    # 供 CLI 决定退出码：COMPLETED / PARTIAL / FAILED
    state.data["overall_status"] = overall
    return state.data
