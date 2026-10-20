"""HOUYI (后羿) —— 环0 靶点自动检索（Phase 4）。

从细菌名自动推导关键毒力/耐药/表面靶点，供环0 在无预置靶点库时兜底。

策略（用户决策 2026-10-01）：
  - 路线B优先：已有预置靶点库（金葡菌/结核杆菌）直接复用
  - 路线A兜底：无预置库时，UniProt 检索 reviewed 蛋白 + 强信号关键词筛选 + 排除黑名单
  - 靶点可控：用户可手动指定靶点覆盖自动结果

强信号关键词（完整词组）+ 排除黑名单（代谢/管家酶），避免把天冬氨酸转氨酶之类误判成靶点。
"""
import os
import sys
import time
import json
import subprocess
import shutil
import urllib.parse
import requests

from .utils import log


# 强信号关键词 -> 机制分类（按特异度排序）
KEYWORD_RULES = [
    (["hemolysin", "leukocidin", "alpha-toxin", "pore-forming toxin", "cytotoxin",
      "virulence factor", "exotoxin", "enterotoxin", "neurotoxin"], "毒力因子"),
    (["adhesin", "MSCRAMM", "fibronectin-binding protein", "collagen-binding",
      "invasin", "intimin", "colonization factor"], "粘附素/入侵"),
    (["penicillin-binding protein", "beta-lactamase", "methicillin resistance",
      "vancomycin resistance", "multidrug efflux", "efflux pump",
      "antibiotic resistance", "drug efflux"], "耐药"),
    (["cell wall", "peptidoglycan", "mycolic acid", "lipopolysaccharide",
      "lipid A", "teichoic acid", "murein", "cell envelope"], "细胞壁/膜合成"),
    (["surface protein", "surface antigen", "outer membrane protein",
      "lipoprotein", "surface-exposed", "cell surface"], "表面抗原"),
    (["quorum sensing", "response regulator", "two-component",
      "sensor histidine kinase", "autoinducer", "accessory gene regulator"], "群体感应/调控"),
    (["siderophore receptor", "siderophore", "heme receptor", "iron uptake",
      "ferric", "hemoglobin receptor", "transferrin"], "营养摄取（铁/金属）"),
    (["biofilm", "capsular polysaccharide", "exopolysaccharide",
      "polysaccharide intercellular adhesin", "capsule biosynthesis"], "生物膜/荚膜"),
]

# 排除黑名单：命中即排除（代谢/管家酶/转录调控/胞内酶）
EXCLUDE_KEYWORDS = [
    "aminotransferase", "carbamoyl phosphate", "trna ligase", "aminoacyl-trna",
    "isomerase", "dehydrogenase", "kinase", "phosphatase", "decarboxylase",
    "deaminase", "epimerase", "hydrolase", "protease", "peptidase", "nuclease",
    "ribosomal", "ribosome", "dna polymerase", "rna polymerase", "helicase",
    "chaperone", "translation", "transcription factor", "elongation factor",
    "replication", "glycosyltransferase", "aminopeptidase", "phosphorylase",
    "mutase", "racemase", "transaminase", "synthetase", "lyase", "dehydratase",
    "dna repair", "metabolism", "metabolic", "biosynthesis of amino",
    # 转录调控蛋白（胞内，表面不可及，非理想抗原靶点）
    # 注意：不要在这里放 "response regulator" —— 它是
    # KEYWORD_RULES 里的正向概念（群体感应/调控）。此前两处冲突，
    # 而排除词先判定，导致该类靶点永远无法被选中。
    "transcriptional regulator", "transcriptional repressor",
    "transcriptional activator",
    "global transcriptional regulator", "phosphodiesterase",
    # 耐药酶应通过"耐药"类别正常分类，但若被当作一般酶需排除
]

# 排除词豁免表（先于 EXCLUDE_KEYWORDS 判定）。
# 这些条目的注释里通常也含 "protease"/"kinase" 等通用管家酶词，
# 但它们本身是明确的毒力/可成药靶点，不应被通用排除词误伤
# （例：牙龈卟啉单胞菌的 gingipain 就曾因 "protease" 被整条丢弃）。
FORCE_INCLUDE_RULES = [
    (["gingipain", "iga protease", "immunoglobulin a protease",
      "c5a peptidase"], "毒力因子"),
    (["collagenase", "hyaluronidase", "neuraminidase",
      "streptokinase", "staphylokinase", "coagulase", "elastase"], "毒力因子"),
    (["sortase", "autolysin", "n-acetylmuramoyl-l-alanine amidase"],
     "细胞壁/膜合成"),
    # 只放"传感器组氨酸激酶"这一具体短语：泛化的 "histidine kinase"
    # 会把管家型激酶一起拉进来，反而稀释候选质量。
    (["sensor histidine kinase"], "群体感应/调控"),
    (["response regulator", "two-component system"], "群体感应/调控"),
]

CATEGORY_PREFIX = {
    "毒力因子": "VT", "粘附素/入侵": "AD", "耐药": "DR",
    "细胞壁/膜合成": "CW", "表面抗原": "SA", "群体感应/调控": "QS",
    "营养摄取（铁/金属）": "NU", "生物膜/荚膜": "BF",
}

# 机制类别优先级：越靠前越优先被选中（毒力/表面靶点 > 代谢/调控）
# 耐药酶（β-内酰胺酶等）因 UniProt 注释丰富易垄断，排后面并限制数量
CATEGORY_PRIORITY = [
    "毒力因子", "粘附素/入侵", "表面抗原", "细胞壁/膜合成",
    "营养摄取（铁/金属）", "生物膜/荚膜", "群体感应/调控", "耐药",
]

# 每类别的上限：避免单一类别（尤其耐药酶）垄断候选列表
CATEGORY_MAX_PER_TYPE = {
    "毒力因子": 6, "粘附素/入侵": 4, "表面抗原": 4,
    "细胞壁/膜合成": 3, "营养摄取（铁/金属）": 3, "生物膜/荚膜": 3,
    "群体感应/调控": 3, "耐药": 2,
}


def _curl_json(url, retries=3):
    curl_bin = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_bin:
        log().error("  [自动检索] 未找到 curl/curl.exe")
        return None

    for i in range(retries):
        try:
            r = subprocess.run(
                [curl_bin, "-s", "-m", "30", url],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
            log().warning(
                f"  [自动检索] curl 请求失败: returncode={r.returncode}"
            )
        except Exception as e:
            log().warning(f"  [自动检索] 请求异常: {e}")
        time.sleep(1.5)
    return None


def search_proteins(organism, reviewed_only=True, size=500,
                    max_pages=200, max_records=None):
    """分页检索 UniProt 蛋白（默认只要 reviewed），并确认结果完整。

    reviewed_only=False 时检索该 organism_name 的全部条目（含 TrEMBL）。
    max_records 用于给 TrEMBL 兜底设上限：一旦达到上限就停止翻页，
    返回部分结果（调用方会收到 truncated 日志），避免为冷门/高注释物种
    一次拉取十万级记录。
    """
    if not 1 <= size <= 500:
        raise ValueError("Invalid UniProt page size")
    if max_pages < 1:
        raise ValueError("Invalid UniProt max_pages")

    q = f'organism_name:"{organism}"'
    if reviewed_only:
        q += " AND reviewed:true"
    base_url = "https://rest.uniprot.org/uniprotkb/search"
    params = {
        "query": q,
        "fields": "accession,gene_names,protein_name,length,cc_function,organism_name",
        "size": size,
        "format": "json",
    }

    all_results = []
    seen = set()
    total = None
    url = base_url
    pages = 0
    truncated = False

    try:
        with requests.Session() as session:
            while url is not None and pages < max_pages:
                response = None
                last_exc = None
                for attempt in range(4):
                    try:
                        response = session.get(
                            url,
                            params=params,
                            timeout=60,
                        )
                        response.raise_for_status()
                        break
                    except requests.RequestException as exc:
                        last_exc = exc
                        response = None
                        time.sleep(2 * (attempt + 1))
                if response is None:
                    raise RuntimeError(
                        f"UNIPROT_REQUEST_FAILED: {last_exc}"
                    )
                data = response.json()

                if not isinstance(data, dict):
                    raise RuntimeError("UNIPROT_INVALID_RESPONSE")

                batch = data.get("results")
                if not isinstance(batch, list):
                    raise RuntimeError("UNIPROT_INVALID_RESULTS")

                if total is None:
                    header = response.headers.get("x-total-results")
                    if header is not None:
                        total = int(header)

                for record in batch:
                    if not isinstance(record, dict):
                        raise RuntimeError("UNIPROT_INVALID_RECORD")
                    accession = record.get("primaryAccession")
                    if not accession:
                        raise RuntimeError("UNIPROT_MISSING_ACCESSION")
                    if accession not in seen:
                        seen.add(accession)
                        all_results.append(record)

                pages += 1
                if max_records is not None and len(all_results) >= max_records:
                    truncated = True
                    log().warning(
                        f"  [自动检索] 已达 TrEMBL 上限 {max_records} 条，"
                        f"停止翻页（reported_total={total}），仅用已取回部分筛选"
                    )
                    break
                url = response.links.get("next", {}).get("url")
                params = None

    except requests.RequestException as exc:
        raise RuntimeError(f"UNIPROT_REQUEST_FAILED: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"UNIPROT_INVALID_RESPONSE: {exc}") from exc

    if url is not None and not truncated:
        raise RuntimeError("UNIPROT_COMPLETENESS_UNCONFIRMED")

    if not truncated and (total is None or len(all_results) != total):
        raise RuntimeError(
            f"UNIPROT_COMPLETENESS_UNCONFIRMED: "
            f"retrieved={len(all_results)} reported_total={total}"
        )

    return all_results


def search_reviewed_proteins(organism, size=500, max_pages=200):
    """兼容旧调用：只检索 reviewed 蛋白。"""
    return search_proteins(
        organism,
        reviewed_only=True,
        size=size,
        max_pages=max_pages,
    )


def count_proteins(organism, reviewed_only=False, timeout=20):
    """轻量计数（只读 x-total-results），用于失败归因，失败返回 None。"""
    q = f'organism_name:"{organism}"'
    if reviewed_only:
        q += " AND reviewed:true"
    try:
        r = requests.get(
            "https://rest.uniprot.org/uniprotkb/search",
            params={"query": q, "size": 1, "format": "list"},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        header = r.headers.get("x-total-results")
        return int(header) if header is not None else None
    except Exception:
        return None



def _extract_info(result):
    pd = result.get("proteinDescription", {})
    if "recommendedName" in pd:
        name = pd["recommendedName"].get("fullName", {}).get("value", "")
    elif "submissionNames" in pd:
        name = pd["submissionNames"][0].get("fullName", {}).get("value", "")
    else:
        name = ""
    genes = []
    for g in result.get("genes", []):
        gn = g.get("geneName", {})
        if isinstance(gn, dict) and gn.get("value"):
            genes.append(gn["value"])
    funcs = []
    for c in result.get("comments", []):
        if c.get("commentType") == "FUNCTION":
            for t in c.get("texts", []):
                funcs.append(t.get("value", ""))
    return {
        "accession": result.get("primaryAccession", ""),
        "name": name,
        "genes": genes,
        "function": funcs,
        "length": result.get("sequence", {}).get("length", 0),
    }


def _candidate_text(info):
    return " ".join([
        info["name"],
        " ".join(info["genes"]),
        " ".join(info["function"]),
    ]).lower()


def _classify_verbose(info):
    """返回 (category, keyword, reason)。

    命中时 reason 为 None；未命中时 reason 为 ("exclude", 命中的排除词)
    或 ("no_keyword", None)。判定顺序：豁免表 -> 排除词 -> 强信号关键词，
    保证 "sensor histidine kinase" / "response regulator" 这类
    既是正向概念、又含通用管家酶词的条目不被误杀。
    """
    text = _candidate_text(info)

    for keywords, category in FORCE_INCLUDE_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return category, kw, None

    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return None, None, ("exclude", kw)

    for keywords, category in KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return category, kw, None

    return None, None, ("no_keyword", None)


def _classify(info):
    category, kw, _ = _classify_verbose(info)
    return category, kw


def _get_sequence(accession):
    url = f"https://rest.uniprot.org/uniprotkb/{accession}?format=json"
    data = _curl_json(url)
    return (data or {}).get("sequence", {}).get("value", "")


UNREVIEWED_MAX_RECORDS = 20000


def auto_discover_targets(organism, max_targets=15, allow_unreviewed=False,
                          diagnostics=None):
    """自动检索 + 筛选靶点，返回靶点 dict（target_id -> 靶点元信息）。

    allow_unreviewed=True 时，若 reviewed 为 0 条，回落到 TrEMBL 全部条目
    （上限 UNREVIEWED_MAX_RECORDS 条），并在每个靶点标注 provenance。

    diagnostics 为可选 dict，会被填入检索/筛选漏斗的中间计数，
    供 ring1 在 0 靶点时给出准确归因（区分"没检索到"与"检索到但被筛掉"）。
    """
    diag = diagnostics if diagnostics is not None else {}
    diag.update({
        "organism": organism,
        "reviewed_hits": 0,
        "unreviewed_used": False,
        "unreviewed_hits": None,
        "all_hits": None,
        "classified": 0,
        "excluded_count": 0,
        "no_keyword_count": 0,
        "length_rejected": 0,
        "bucket_counts": {},
        "candidates": 0,
        "exclude_examples": [],
        "stage": None,
        "provenance": "reviewed",
    })

    log().info(f"  [自动检索] 检索 {organism} 的 reviewed 蛋白...")
    results = search_proteins(organism, reviewed_only=True)
    n_reviewed = len(results)
    diag["reviewed_hits"] = n_reviewed
    log().info(f"  [自动检索] 命中 {n_reviewed} 条 reviewed 蛋白")

    provenance = "reviewed"
    if n_reviewed == 0 and allow_unreviewed:
        log().warning(
            "  [自动检索] reviewed 为 0，按 --allow-unreviewed 回落到 "
            "TrEMBL（自动注释，可靠性低于 Swiss-Prot）"
        )
        results = search_proteins(
            organism,
            reviewed_only=False,
            max_records=UNREVIEWED_MAX_RECORDS,
        )
        provenance = "TrEMBL"
        diag["unreviewed_used"] = True
        diag["unreviewed_hits"] = len(results)
        diag["provenance"] = provenance
        log().info(
            f"  [自动检索] TrEMBL 命中 {len(results)} 条（已标注 "
            f"provenance=TrEMBL）"
        )

    if not results:
        diag["stage"] = "no_hits"
        diag["all_hits"] = count_proteins(organism, reviewed_only=False)
        log().warning(
            f"  [自动检索] 0 条可用蛋白（不限 reviewed 的库内总数: "
            f"{diag['all_hits']}）"
        )
        return {}

    # 第一遍：分类收集所有候选（按类别分桶，去重）
    buckets = {}
    seen = set()
    n_excluded = 0
    n_no_keyword = 0
    n_length = 0
    exclude_examples = []
    for r in results:
        info = _extract_info(r)
        category, kw, reason = _classify_verbose(info)
        if category is None:
            kind, word = reason
            if kind == "exclude":
                n_excluded += 1
                if len(exclude_examples) < 5:
                    exclude_examples.append({
                        "accession": info["accession"],
                        "gene": info["genes"][0] if info["genes"] else "",
                        "protein": info["name"],
                        "word": word,
                    })
            else:
                n_no_keyword += 1
            continue
        if info["length"] < 30 or info["length"] > 1200:
            n_length += 1
            continue
        gene_key = (info["genes"][0] if info["genes"] else info["accession"]).lower()
        if gene_key in seen:
            continue
        seen.add(gene_key)
        buckets.setdefault(category, []).append((info, kw))

    diag.update({
        "classified": sum(len(v) for v in buckets.values()),
        "excluded_count": n_excluded,
        "no_keyword_count": n_no_keyword,
        "length_rejected": n_length,
        "bucket_counts": {k: len(v) for k, v in buckets.items()},
        "exclude_examples": exclude_examples,
    })
    log().info(
        f"  [自动检索] 关键词筛选: 通过 {diag['classified']} 条 / "
        f"排除词命中 {n_excluded} 条 / 无机制关键词 {n_no_keyword} 条 / "
        f"长度不符 {n_length} 条"
    )

    # 第二遍：按类别优先级 + 每类上限选取，避免单一类别垄断
    targets = {}
    category_counts = {}
    for category in CATEGORY_PRIORITY:
        cands = buckets.get(category, [])
        cap = CATEGORY_MAX_PER_TYPE.get(category, 3)
        for info, kw in cands:
            if len(targets) >= max_targets:
                break
            if category_counts.get(category, 0) >= cap:
                break
            prefix = CATEGORY_PREFIX.get(category, "TG")
            tid = f"{prefix}_{info['genes'][0] if info['genes'] else info['accession']}"
            targets[tid] = {
                "gene": info["genes"][0] if info["genes"] else "",
                "protein": info["name"],
                "mechanism_class": category,
                "length_aa": info["length"],
                "uniprot": info["accession"],
                "function": " ".join(info["function"])[:300],
                "pdb": None,
                "auto_detected": True,
                "provenance": provenance,
                "detect_keyword": kw,
            }
            category_counts[category] = category_counts.get(category, 0) + 1
        if len(targets) >= max_targets:
            break

    diag["candidates"] = len(targets)
    diag["stage"] = "ok" if targets else "classified_zero"

    log().info(f"  [自动检索] 筛选出 {len(targets)} 个候选靶点")
    for tid, v in targets.items():
        log().info(f"    {tid}: {v['protein']} [{v['mechanism_class']}]")

    # 抓序列
    for tid, v in targets.items():
        if v["uniprot"]:
            v["sequence"] = _get_sequence(v["uniprot"])
            time.sleep(0.4)

    return targets
