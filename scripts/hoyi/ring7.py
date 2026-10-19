"""HOUYI Ring7 — tail-fiber receptor discovery and ranking.

策略：
1. 当前菌在人工 fiber KB 中有记录 -> 使用人工 KB。
2. 当前菌无 KB 记录 -> cold-start，从 UniProt reviewed 蛋白自动发现
   表面暴露/外膜/受体候选。
3. 自动发现阶段只对有明确文本证据的维度赋分；
   无证据的 essentiality/template_availability/species_coverage 保守记 0。
"""

import os
import time

from .utils import load_json, save_json, log, emit_event
from .auto_target_discovery import (
    search_reviewed_proteins,
    _extract_info,
    _get_sequence,
    _curl_json,
)


# ---------------------------------------------------------------------
# Cold-start receptor rules
# 越靠前代表越强的“可被尾纤维接触”证据。
# ---------------------------------------------------------------------

STRONG_SURFACE_RULES = [
    ("surface-exposed", 0.98, 0.85),
    ("cell surface", 0.97, 0.85),
    ("surface protein", 0.95, 0.82),
    ("surface antigen", 0.95, 0.85),
    ("outer membrane receptor", 0.97, 0.90),
    ("outer membrane protein", 0.92, 0.75),
    ("siderophore receptor", 0.95, 0.88),
    ("heme receptor", 0.95, 0.88),
    ("iron receptor", 0.95, 0.85),
    ("adhesin", 0.92, 0.82),
    ("invasin", 0.90, 0.82),
    ("porin", 0.88, 0.65),
    ("fimbrial", 0.86, 0.70),
    ("pilus", 0.84, 0.68),
    ("pilin", 0.84, 0.68),
    ("surface-anchored", 0.95, 0.85),
    ("cell wall-anchored", 0.95, 0.85),
    ("cell wall anchored", 0.95, 0.85),
    ("covalently anchored", 0.95, 0.85),
    ("autotransporter", 0.93, 0.82),
    ("hemagglutinin", 0.92, 0.80),
    ("haemagglutinin", 0.92, 0.80),
    ("s-layer", 0.92, 0.85),
    ("surface layer", 0.92, 0.85),
    ("adhesin-like", 0.92, 0.82),
    ("pili", 0.84, 0.68),
    ("curli", 0.86, 0.75),
    ("flagellin", 0.85, 0.70),
    ("outer membrane", 0.90, 0.78),
]

# 明显不适合作为细胞表面尾纤维受体的胞内/代谢类关键词。
RECEPTOR_EXCLUDE = [
    "ribosomal",
    "ribosome",
    "dna polymerase",
    "rna polymerase",
    "transcriptional regulator",
    "transcription factor",
    "translation factor",
    "elongation factor",
    "chaperone",
    "helicase",
    "cytoplasmic",
    "cytosolic",
    "aminotransferase",
    "dehydrogenase",
    "isomerase",
    "synthetase",
    "nuclease",
]

# 结构化注释证据（UniProt keywords 字段，配合亚细胞定位使用）
STRUCT_KW = {
    "cell wall",
    "outer membrane",
    "surface antigen",
    "cell surface",
}


def _composite_score(info, weights):
    """按加权求和计算尾纤维靶点综合分（0-1）。"""
    score = 0.0
    for key, w in weights.items():
        v = info.get(key, 0.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        score += w * v
    return round(score, 4)


def _coldstart_receptor_match(info):
    """判断 UniProt 蛋白是否具备明确表面受体证据。

    Returns:
        tuple | None:
          (matched_keyword, exposure_score, specificity_score)
    """
    text = " ".join(
        [
            info.get("name", ""),
            " ".join(info.get("genes", [])),
            " ".join(info.get("function", [])),
        ]
    ).lower()

    for kw in RECEPTOR_EXCLUDE:
        if kw in text:
            return None

    for kw, exposure, specificity in STRONG_SURFACE_RULES:
        if kw in text:
            return kw, exposure, specificity

    return None



def _check_surface_localization(accession):
    """用完整 UniProt 记录做表面可及性硬门控。"""
    if not accession:
        return False, [], "no_accession"

    d = _curl_json(
        f"https://rest.uniprot.org/uniprotkb/{accession}?format=json"
    ) or {}

    locations = []
    notes = []

    for c in d.get("comments", []):
        if c.get("commentType") != "SUBCELLULAR LOCATION":
            continue

        for x in c.get("subcellularLocations", []):
            loc = ((x.get("location") or {}).get("value") or "").strip()
            if loc:
                locations.append(loc)

        for t in (c.get("note") or {}).get("texts", []):
            v = (t.get("value") or "").strip()
            if v:
                notes.append(v)

    text = " ".join(locations + notes).lower()

    strong_positive = [
        "cell outer membrane",
        "cell surface",
        "surface-exposed",
        "fimbrium",
        "fimbria",
        "pilus",
        "cell wall",
    ]

    hard_negative = [
        "cytoplasm",
        "cytosol",
        "periplasm",
        "cell inner membrane",
    ]

    # 有明确表面证据时，即使同时存在其他定位，也允许保留
    if any(k in text for k in strong_positive):
        return True, locations, "surface_supported"

    if any(k in text for k in hard_negative):
        return False, locations, "non_surface"

    # secreted-only 不作为稳定细胞表面受体
    if "secreted" in text:
        return False, locations, "secreted_only"

    return False, locations, "no_surface_evidence"



def _search_receptor_records(organism, size=500, max_pages=20):
    """检索 reviewed 蛋白，额外取回亚细胞定位与关键词字段（结构化证据通道）。"""
    import requests

    q = f'organism_name:"{organism}" AND reviewed:true'
    url = "https://rest.uniprot.org/uniprotkb/search"
    params = {
        "query": q,
        "fields": (
            "accession,gene_names,protein_name,length,cc_function,"
            "organism_name,cc_subcellular_location,keyword"
        ),
        "size": size,
        "format": "json",
    }
    out = []
    pages = 0
    with requests.Session() as session:
        while url is not None and pages < max_pages:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise RuntimeError("UNIPROT_INVALID_RESPONSE")
            out.extend(data.get("results") or [])
            url = (resp.links.get("next") or {}).get("url")
            params = {}
            pages += 1
    return out


def _structured_surface_evidence(record):
    """从检索返回的结构化字段判定表面可及性证据（不额外发起逐条请求）。

    判定优先级与旧版完整记录门控一致：
      1) 亚细胞定位文本存在强阳性 -> 放行（即使同时存在其他定位）；
      2) keywords 命中细胞壁/外膜类，且无硬阴性定位 -> 保守放行；
      3) 否则无结构化表面证据。

    Returns:
        tuple | None:
            (evidence_tag, exposure, specificity, locations)
    """
    locations = []
    notes = []
    for c in record.get("comments") or []:
        if c.get("commentType") != "SUBCELLULAR LOCATION":
            continue
        for x in c.get("subcellularLocations") or []:
            loc = ((x.get("location") or {}).get("value") or "").strip()
            if loc:
                locations.append(loc)
        for t in (c.get("note") or {}).get("texts") or []:
            v = (t.get("value") or "").strip()
            if v:
                notes.append(v)
    loc_text = " ".join(locations + notes).lower()

    strong_positive = [
        "cell outer membrane",
        "cell surface",
        "surface-exposed",
        "fimbrium",
        "fimbria",
        "pilus",
        "cell wall",
    ]
    hard_negative = [
        "cytoplasm",
        "cytosol",
        "periplasm",
        "cell inner membrane",
    ]

    kw_names = {
        (k.get("name") or "").lower()
        for k in record.get("keywords") or []
    }
    kw_hit = sorted(kw_names & STRUCT_KW)

    if any(p in loc_text for p in strong_positive):
        tag = "CC:surface_supported"
        if kw_hit:
            tag += "+KW:" + "/".join(kw_hit)
        return tag, 0.90, 0.78, locations

    if kw_hit and not any(h in loc_text for h in hard_negative):
        return "KW:" + "/".join(kw_hit), 0.85, 0.72, locations

    return None


def auto_discover_fiber_targets(organism, max_targets=8):
    """Cold-start 自动发现尾纤维表面受体候选。

    双通道证据，均要求明确的表面可及性证据：
      A) 名称/基因/功能文本命中 STRONG_SURFACE_RULES；
      B) UniProt 结构化注释命中（亚细胞定位强阳性 / 细胞壁-外膜关键词）。
    未经证据支持的评分维度统一保守为 0。
    """
    log().info(
        f"  [Ring7 cold-start] 检索 {organism} 的 reviewed 表面受体候选..."
    )

    results = _search_receptor_records(organism, size=500)

    log().info(
        f"  [Ring7 cold-start] UniProt reviewed 命中 {len(results)} 条蛋白"
    )

    raw_candidates = []
    seen = set()

    for r in results:
        info = _extract_info(r)

        if info["length"] < 30 or info["length"] > 2000:
            continue

        match = _coldstart_receptor_match(info)       # 通道 A：文本证据
        struct_ev = _structured_surface_evidence(r)   # 通道 B：结构化证据

        if match is None and struct_ev is None:
            continue

        if struct_ev is None:
            # 文本命中但结构化字段无表面证据：
            # 与旧版完整记录门控的数据源一致，结论相同 -> 丢弃
            log().info(
                f"    [Ring7 gate] DROP {info['accession']}: "
                f"{info['name']} | reason=no_surface_evidence"
            )
            continue

        if match is not None:
            keyword, exposure, specificity = match
        else:
            keyword, exposure, specificity = struct_ev[:3]

        gene = info["genes"][0] if info["genes"] else ""
        accession = info["accession"]

        dedup_key = (gene or accession).lower()
        if not dedup_key or dedup_key in seen:
            continue

        # 表面可及性硬门控：基于检索返回的亚细胞定位/关键词结构化字段
        # （与旧版完整记录门控同一 UniProt 数据源，省去逐条二次请求）
        locations = struct_ev[3]

        seen.add(dedup_key)

        info["_surface_locations"] = locations
        info["_localization_reason"] = struct_ev[0]

        preliminary = (
            0.30 * exposure +
            0.20 * specificity
        )

        raw_candidates.append(
            (
                preliminary,
                info,
                keyword,
                exposure,
                specificity,
            )
        )

    raw_candidates.sort(key=lambda x: x[0], reverse=True)
    raw_candidates = raw_candidates[:max_targets]

    candidates = {}

    for _, info, keyword, exposure, specificity in raw_candidates:
        gene = info["genes"][0] if info["genes"] else ""
        accession = info["accession"]

        target_id = (
            f"AUTO_{gene}"
            if gene
            else f"AUTO_{accession}"
        )

        sequence = ""
        if accession:
            sequence = _get_sequence(accession)
            time.sleep(0.25)

        candidates[target_id] = {
            "protein": info["name"],
            "gene": gene,
            "receptor_type": "surface_protein",
            "organism": organism,

            # 无天然 tail-fiber 模板时不伪造
            "reference_fiber": None,
            "reference_uniprot": accession,
            "reference_pdb": None,
            "reference_sequence": sequence,
            "pdb_chain": "A",

            "binding_site": (
                f"自动发现候选；UniProt 文本证据关键词={keyword}；"
                "具体结合位点尚未验证"
            ),

            # 有明确文本证据的维度
            "exposure": exposure,
            "specificity": specificity,

            # 无证据的维度必须保守为 0
            "essentiality": 0.0,
            "template_availability": 0.0,
            "species_coverage": 0.0,

            "mechanism_class": "tail_fiber_redirect",
            "auto_detected": True,
            "evidence_keyword": keyword,
            "evidence_source": "UniProt reviewed annotation + subcellular localization",
            "surface_locations": info.get("_surface_locations", []),
            "localization_reason": info.get("_localization_reason", ""),
            "note": (
                "Ring7 cold-start 自动发现。"
                "当前仅依据 reviewed UniProt 的表面/外膜文本证据；"
                "尚未进行受体结合位点和实验验证。"
            ),
        }

    log().info(
        f"  [Ring7 cold-start] 筛选出 {len(candidates)} 个表面受体候选"
    )

    for tid, info in candidates.items():
        log().info(
            f"    {tid}: {info['protein']} "
            f"[{info['evidence_keyword']}]"
        )

    return candidates


def run(cfg, fiber_targets=None, state=None, dry_run=False):
    """环 7：尾纤维靶点分析。

    Args:
        cfg: 配置
        fiber_targets: 指定靶点（None=按菌名过滤 KB；无 KB 时 cold-start）
        state: 状态对象
        dry_run: 预览

    Returns:
        list: 按优先级排序的尾纤维靶点列表（含综合分）。
    """

    log().info("===== 环 7：尾纤维靶点分析（表面受体）=====")

    # -------------------------------------------------------------
    # KB 加载：缺文件必须显式 warning，禁止静默误判成“无匹配”
    # -------------------------------------------------------------

    if not os.path.exists(cfg.fiber_kb_path):
        log().warning(
            f"  fiber KB 文件不存在: {cfg.fiber_kb_path}；"
            "将直接进入 cold-start 自动受体发现"
        )
        kb = {}
    else:
        kb = load_json(cfg.fiber_kb_path, default={})

    kb_targets = kb.get("targets", {}) if isinstance(kb, dict) else {}

    # 如果 KB 没有权重，仍使用平台既定默认权重
    weights = kb.get(
        "scoring_weights",
        {
            "exposure": 0.30,
            "essentiality": 0.20,
            "specificity": 0.20,
            "template_availability": 0.15,
            "species_coverage": 0.15,
        },
    )

    organism = cfg._organism or ""

    # -------------------------------------------------------------
    # 收集候选
    # -------------------------------------------------------------

    if fiber_targets:
        candidates = {
            t: kb_targets.get(t, {})
            for t in fiber_targets
            if t in kb_targets
        }

        missing = [
            t for t in fiber_targets
            if t not in kb_targets
        ]

        if missing:
            log().warning(
                f"  指定的 fiber target 不在 KB 中: {missing}"
            )

    else:
        candidates = {}

        if not organism:
            candidates = dict(kb_targets)

        else:
            org_query = organism.lower()

            for t, info in kb_targets.items():
                org = (
                    info.get("organism", "") or ""
                ).lower()

                if (
                    org
                    and (
                        org_query in org
                        or org in org_query
                    )
                ):
                    candidates[t] = info

            # -----------------------------------------------------
            # 真正 cold-start fallback
            # -----------------------------------------------------

            if not candidates:
                log().warning(
                    f"  fiber KB 中无 organism={organism} 的匹配受体，"
                    "触发 Ring7 cold-start 自动受体发现"
                )

                if dry_run:
                    log().info(
                        "  [dry-run] 跳过联网自动受体检索"
                    )
                else:
                    candidates = auto_discover_fiber_targets(
                        organism,
                        max_targets=8,
                    )

    if not candidates:
        log().warning("  Ring7 无候选：数据完整性尚未确认，按阻塞处理")
        save_json(cfg.ring7_out, [])

        if state is not None:
            state.set_artifact(7, "fiber_targets", [])
            state.mark_ring(
                7,
                "SKIPPED",
                "Ring7空候选（数据完整性未确认）",
            )

        return []

    # -------------------------------------------------------------
    # 沿用原有评分体系
    # -------------------------------------------------------------

    results = []

    for t, info in candidates.items():
        score = _composite_score(info, weights)

        rec = {
            "fiber_target": t,
            "protein": info.get("protein", ""),
            "gene": info.get("gene", ""),
            "receptor_type": info.get(
                "receptor_type",
                "surface_protein",
            ),
            "organism": info.get("organism", ""),
            "reference_fiber": info.get("reference_fiber"),
            "reference_uniprot": info.get("reference_uniprot"),
            "reference_pdb": info.get("reference_pdb"),
            "reference_sequence": info.get("reference_sequence"),
            "pdb_chain": info.get("pdb_chain", "A"),
            "binding_site": info.get("binding_site", ""),
            "composite_score": score,
            "priority_rank": 0,

            # provenance
            "auto_detected": info.get("auto_detected", False),
            "evidence_keyword": info.get("evidence_keyword"),
            "evidence_source": info.get("evidence_source"),
        }

        results.append(rec)

    results.sort(
        key=lambda x: x["composite_score"],
        reverse=True,
    )

    for i, r in enumerate(results):
        r["priority_rank"] = i + 1

    save_json(cfg.ring7_out, results)

    log().info("  尾纤维靶点优先级（按综合分降序）：")

    for r in results:
        source = (
            "AUTO"
            if r.get("auto_detected")
            else "KB"
        )

        log().info(
            f"    #{r['priority_rank']} "
            f"{r['fiber_target']} "
            f"({r['protein']}) "
            f"score={r['composite_score']} "
            f"[{source}]"
        )

    if state is not None:
        state.set_artifact(
            7,
            "fiber_targets",
            results,
        )

        state.mark_ring(
            7,
            "DONE",
            f"{len(results)} 尾纤维靶点完成打分",
        )

    return results
