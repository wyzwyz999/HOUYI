"""HOUYI (后羿) —— 环 1：靶点分析。

从知识库推导靶点；若该细菌无预置知识库，自动检索（Phase 4）。
产出：targets 列表 + 每靶点元信息。

模式：
  - 预置库命中：直接读知识库（金葡菌/结核杆菌已建）
  - 无预置库：auto_target_discovery 自动检索 + 规则筛选
  - targets_filter：用户手动指定靶点（靶点可控），覆盖自动结果
"""
import os
from .utils import load_json, save_json, log


def run(cfg, organism: str, targets_filter=None, state=None, dry_run=False):
    log().info("===== 环 1：靶点分析 =====")

    kb = load_json(cfg.kb_path)

    # 判断是否命中预置库（organism 匹配 + 有靶点）
    use_kb = (kb is not None
              and kb.get("organism", "").lower() == organism.lower()
              and kb.get("targets"))

    if use_kb:
        log().info(f"  命中预置知识库: {kb['organism']} ({len(kb['targets'])} 靶点)")
        targets_meta = kb["targets"]
    else:
        if kb is not None and kb.get("targets"):
            log().warning(f"  知识库 organism={kb.get('organism')}，请求={organism}，不匹配，触发自动检索")
        else:
            log().info(f"  无预置知识库，触发自动靶点检索（Phase 4）")

        # 自动检索
        from .auto_target_discovery import auto_discover_targets
        if dry_run:
            log().info("  [dry-run] 跳过自动检索（预览模式）")
            targets_meta = {}
        else:
            try:
                targets_meta = auto_discover_targets(organism)
            except Exception as e:
                log().error(f"  自动检索失败: {e}")
                targets_meta = {}

    # 可选过滤（靶点可控：用户手动指定）
    all_targets = list(targets_meta.keys())
    if targets_filter:
        # 支持用户指定已有靶点 ID，或直接给基因名
        filtered = []
        for f in targets_filter:
            if f in all_targets:
                filtered.append(f)
            else:
                # 尝试按基因名匹配
                matched = [t for t in all_targets
                           if targets_meta[t].get("gene", "").lower() == f.lower()]
                filtered.extend(matched)
                if not matched:
                    log().warning(f"  未找到靶点: {f}")
        targets = list(dict.fromkeys(filtered))  # 去重保序
    else:
        targets = all_targets

    if not targets:
        log().warning("  无可用靶点（自动检索未命中且无预置库）")

    for t in targets:
        info = targets_meta[t]
        log().info(f"    - {t}: {info['protein']} [{info['mechanism_class']}]")

    result = {
        "organism": organism,
        "targets": targets,
        "target_meta": {t: targets_meta[t] for t in targets},
        "auto_discovered": not use_kb,
    }
    save_json(cfg.ring1_out, result)

    if state is not None:
        state.data["organism"] = organism
        state.set_artifact(1, "targets", targets)
        state.mark_ring(1, "DONE",
                        f"{len(targets)} targets "
                        f"({'auto' if not use_kb else 'KB'})")

    return result
