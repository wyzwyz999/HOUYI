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


def _explain_no_targets(organism, diag, allow_unreviewed):
    """按检索/筛选漏斗生成可操作的 0 靶点说明。

    三种病因必须分开报，否则会把"该物种无 Swiss-Prot 收录"或
    "命中但被关键词筛掉"误报成"菌名不标准"。
    """
    diag = diag or {}
    stage = diag.get("stage")
    reviewed_hits = diag.get("reviewed_hits")
    all_hits = diag.get("all_hits")
    classified = diag.get("classified")
    lines = []

    if stage == "no_hits" or not reviewed_hits:
        if allow_unreviewed:
            lines.append(
                f'环1 无可用靶点：organism_name="{organism}" 在 UniProt '
                f"检索 reviewed 与 TrEMBL 结果均为 0 条。"
            )
            lines.append(
                "这通常说明菌名不是 UniProt 的 organism_name："
                "致病型/血清型/中文/缩写名都查不到，请改用标准拉丁种名。"
            )
        elif all_hits == 0:
            lines.append(
                f'环1 无可用靶点：organism_name="{organism}" 在 UniProt '
                f"完全查不到记录（reviewed 与 TrEMBL 都是 0 条）。"
            )
            lines.append(
                "菌名可能不规范。示例：Adherent-invasive E. coli -> "
                "Escherichia coli；S. Typhimurium -> Salmonella typhimurium；"
                "中文名/缩写名请换成拉丁种名。"
            )
        else:
            lines.append(
                f'环1 无可用靶点：菌名合法。organism_name="{organism}" 在 '
                f"UniProt 有 {all_hits} 条记录，但 reviewed（Swiss-Prot 人工审阅）"
                f"为 0 条。"
            )
            lines.append(
                "即该物种没有被 Swiss-Prot 收录（厌氧菌/新发病原常见），"
                "可选处理："
            )
            lines.append(
                "  a) 加 --allow-unreviewed，用 TrEMBL 自动注释重跑"
                "（结果会标注 provenance=TrEMBL，注释可靠性下降）；"
            )
            lines.append("  b) 用 --targets <基因名|UniProt ID> 手动指定靶点；")
            lines.append("  c) 为该物种建预置靶点库（最稳，可重复使用）。")
        lines.append(
            "核查命令: curl -sG https://rest.uniprot.org/uniprotkb/search "
            f"--data-urlencode 'query=organism_name:\"{organism}\"' "
            "--data 'size=1&format=list' -D - -o /dev/null | grep -i x-total-results"
        )

    elif not classified:
        lines.append(
            f'环1 无可用靶点：organism_name="{organism}" 命中 '
            f"{reviewed_hits} 条 reviewed 蛋白，但没有一条通过机制筛选。"
        )
        lines.append("菌名没问题，是命中结果被关键词规则过滤了：")
        lines.append(f"  - 命中排除词: {diag.get('excluded_count', 0)} 条")
        for ex in (diag.get("exclude_examples") or [])[:5]:
            label = ex.get("gene") or ex.get("accession") or "?"
            protein = (ex.get("protein") or "")[:48]
            lines.append(f'      {label} {protein} <- "{ex.get("word")}"')
        lines.append(f"  - 无机制关键词: {diag.get('no_keyword_count', 0)} 条")
        lines.append(
            "可选处理：用 --targets <基因名|UniProt ID> 手动指定靶点；"
            "或为该物种建预置靶点库。"
        )

    elif stage == "selector_zero":
        lines.append(
            f"环1 无可用靶点：检索到 {diag.get('candidates', 0)} 个候选，"
            f"但 payload 选择器把它们全部排除（多为分泌毒素/粘附素，"
            f"不适合做功能失活靶点）。"
        )
        for ex in (diag.get("selector_examples") or [])[:5]:
            lines.append(f"      {ex}")
        lines.append(
            "可选处理：用 --targets 手动指定靶点，或调整 payload 选择器规则。"
        )

    else:
        lines.append(
            f'环1 无可用靶点：organism_name="{organism}" 未得到可用候选。'
        )
        lines.append(
            f"漏斗: reviewed 命中={reviewed_hits}, 通过筛选={classified}, "
            f"候选={diag.get('candidates', 0)}"
        )

    return "\n".join(lines)


def run(
    cfg,
    organism: str,
    targets_filter=None,
    state=None,
    dry_run=False,
    auto_top_n_targets=1,
    allow_unreviewed=False,
):
    log().info("===== 环 1：靶点分析 =====")

    kb = load_json(cfg.kb_path)
    diag = {}
    target_ranking = None

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
                targets_meta = auto_discover_targets(
                    organism,
                    allow_unreviewed=allow_unreviewed,
                    diagnostics=diag,
                )
            except Exception as e:
                log().error(f"  自动检索失败: {e}")
                raise

            log().info(
                "  检索漏斗: "
                f"reviewed={diag.get('reviewed_hits')}"
                + (
                    f" / TrEMBL={diag.get('unreviewed_hits')}"
                    if diag.get("unreviewed_used")
                    else ""
                )
                + f" -> 通过筛选={diag.get('classified')}"
                f" -> 候选={diag.get('candidates')}"
                f"（provenance={diag.get('provenance')}）"
            )

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
        # 默认自动选择适合作为胞内payload的Top-N靶点。
        # 手动targets_filter仍具有最高优先级。
        from .payload_target_selector import select_payload_targets

        targets, target_ranking = select_payload_targets(
            targets_meta,
            top_n=auto_top_n_targets,
        )

        log().info(
            f"  自动payload靶点选择 Top{auto_top_n_targets}: "
            + ", ".join(targets)
        )

    if not targets:
        if dry_run:
            log().warning("  [dry-run] 无可用靶点（预览模式，正常）")
        elif targets_filter:
            available = ", ".join(all_targets[:10]) or "（无）"
            msg = (
                "环1 无可用靶点：--targets 指定的靶点在检索结果中未匹配: "
                + str(targets_filter)
                + f"。当前可用靶点: {available}"
            )
            log().error(f"  {msg}")
            raise RuntimeError(msg)
        else:
            if targets_meta:
                diag["stage"] = "selector_zero"
                diag["candidates"] = len(targets_meta)
                diag["selector_examples"] = [
                    f"{r.get('target_id')}: "
                    + ", ".join(r.get("matched_concepts") or [])
                    for r in (target_ranking or [])
                    if r.get("excluded")
                ][:5]
            msg = _explain_no_targets(organism, diag, allow_unreviewed)
            log().error(f"  {msg}")
            raise RuntimeError(msg)

    for t in targets:
        info = targets_meta[t]
        log().info(f"    - {t}: {info['protein']} [{info['mechanism_class']}]")

    result = {
        "organism": organism,
        "targets": targets,
        "target_meta": {t: targets_meta[t] for t in targets},
        "auto_discovered": not use_kb,
    }

    if not use_kb:
        result["discovery_diagnostics"] = diag

    if not targets_filter:
        result["auto_target_selection"] = True
        result["auto_top_n_targets"] = int(auto_top_n_targets)
        result["target_ranking"] = target_ranking
    save_json(cfg.ring1_out, result)

    if state is not None:
        state.data["organism"] = organism
        state.set_artifact(1, "targets", targets)
        source = "KB" if use_kb else "auto"
        if not use_kb and diag.get("provenance") == "TrEMBL":
            source += ", TrEMBL"
        state.mark_ring(1, "DONE", f"{len(targets)} targets ({source})")

    return result
