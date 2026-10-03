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
from .config import Config
from .utils import State, load_json, log, CommandError, emit_event
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
                 scorer="length", mic_map=None, top_n=3, num_designs=32):
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
    """
    skip = skip or []
    cfg.ensure_dirs()
    cfg.set_organism(organism)  # 按细菌名切换数据源
    from .utils import set_dry_run, ensure_clean_organism
    set_dry_run(dry_run)
    # 检测 organism 变更并清理跨菌种残留（避免 KP 残留污染金葡菌等）
    ensure_clean_organism(cfg, organism)
    state = State(cfg)

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
            ring1.run(cfg, organism, targets, state)
            targets = state.get_artifact(1, "targets", [])
            emit(1, "done", f"完成：推导出 {len(targets)} 个靶点")
        except Exception as e:
            log().error(f"环 1 失败: {e}")
            state.mark_ring(1, "ERROR", str(e))
            emit(1, "error", f"环 1 失败: {e}")
            if not dry_run:
                raise
    else:
        targets = targets or state.get_artifact(1, "targets", [])
        if not targets:
            kb = load_json(cfg.kb_path)
            targets = list(kb["targets"].keys()) if kb else []
        log().info(f"环 1 跳过，使用靶点: {targets}")
        emit(1, "skipped", f"跳过（复用 {len(targets)} 个靶点）")

    # ---- 环 2：结构预测 ----
    if should_run(2):
        emit(2, "running", "环 2：结构预测")
        try:
            ring2.run(cfg, targets, state, dry_run=dry_run)
            emit(2, "done", "完成：结构来源已确定")
        except Exception as e:
            log().error(f"环 2 失败: {e}")
            state.mark_ring(2, "ERROR", str(e))
            emit(2, "error", f"环 2 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 3：Binder 设计 ----
    if should_run(3):
        emit(3, "running", "环 3：Binder 设计")
        try:
            ring3.run(cfg, targets, state, dry_run=dry_run, num_designs=num_designs)
            emit(3, "done", "完成：binder 骨架已生成")
        except Exception as e:
            log().error(f"环 3 失败: {e}")
            state.mark_ring(3, "ERROR", str(e))
            emit(3, "error", f"环 3 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 4：评分排序 ----
    if should_run(4):
        emit(4, "running", "环 4：评分排序")
        try:
            ring4.run(cfg, targets, scorer, mic_map=mic_map, state=state, dry_run=dry_run)
            emit(4, "done", "完成：binder 评分排序")
        except Exception as e:
            log().error(f"环 4 失败: {e}")
            state.mark_ring(4, "ERROR", str(e))
            emit(4, "error", f"环 4 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 5：输出 binder ----
    if should_run(5):
        emit(5, "running", "环 5：输出 Top binder")
        try:
            scored = load_json(cfg.ring4_out) if not should_run(4) else None
            ring5.run(cfg, scored=scored, top_n=top_n, state=state)
            emit(5, "done", "完成：Top binder 已输出")
        except Exception as e:
            log().error(f"环 5 失败: {e}")
            state.mark_ring(5, "ERROR", str(e))
            emit(5, "error", f"环 5 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 6：拼装载 ----
    if should_run(6):
        emit(6, "running", "环 6：拼装载（Pdp1_NTD-linker-binder）")
        try:
            top = load_json(cfg.ring5_json) if not should_run(5) else None
            ring6.run(cfg, top=top, state=state)
            emit(6, "done", "完成：载荷已生成")
        except Exception as e:
            log().error(f"环 6 失败: {e}")
            state.mark_ring(6, "ERROR", str(e))
            emit(6, "error", f"环 6 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 7：尾纤维靶点分析 ----
    if should_run(7):
        emit(7, "running", "环 7：尾纤维靶点分析")
        try:
            ring7.run(cfg, state=state, dry_run=dry_run)
            emit(7, "done", "完成：尾纤维靶点已打分排序")
        except Exception as e:
            log().error(f"环 7 失败: {e}")
            state.mark_ring(7, "ERROR", str(e))
            emit(7, "error", f"环 7 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 8：尾纤维 binder/天然结构域筛选 ----
    if should_run(8):
        emit(8, "running", "环 8：尾纤维 binder/天然结构域筛选")
        try:
            fiber_targets = load_json(cfg.ring7_out) if not should_run(7) else None
            ring8.run(cfg, fiber_targets=fiber_targets, state=state,
                      num_designs=num_designs, dry_run=dry_run)
            emit(8, "done", "完成：尾纤维 binder/结构域已筛选")
        except Exception as e:
            log().error(f"环 8 失败: {e}")
            state.mark_ring(8, "ERROR", str(e))
            emit(8, "error", f"环 8 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 9：重编程 pvc13 ----
    if should_run(9):
        emit(9, "running", "环 9：重编程 pvc13（N-binder-C）")
        try:
            fiber_binders = load_json(cfg.ring8_out) if not should_run(8) else None
            ring9.run(cfg, fiber_binders=fiber_binders, state=state)
            emit(9, "done", "完成：重编程尾纤维已生成")
        except Exception as e:
            log().error(f"环 9 失败: {e}")
            state.mark_ring(9, "ERROR", str(e))
            emit(9, "error", f"环 9 失败: {e}")
            if not dry_run:
                raise

    # ---- 环 10：纳米注射器总装（PVC 完整重设计） ----
    if should_run(10):
        emit(10, "running", "环 10：纳米注射器总装（PVC 完整重设计）")
        try:
            payloads = load_json(cfg.ring6_json) if not should_run(6) else None
            fibers = load_json(cfg.ring9_out) if not should_run(9) else None
            ring10.run(cfg, payloads=payloads, reprogrammed_fibers=fibers, state=state)
            emit(10, "done", "完成：纳米注射器规格已生成")
        except Exception as e:
            log().error(f"环 10 失败: {e}")
            state.mark_ring(10, "ERROR", str(e))
            emit(10, "error", f"环 10 失败: {e}")
            if not dry_run:
                raise

    emit(-1, "finish", "管线执行完成")
    log().info("=" * 50)
    log().info("管线执行完成")
    log().info(f"状态文件: {cfg.state_path}")
    log().info("=" * 50)
    return state.data
