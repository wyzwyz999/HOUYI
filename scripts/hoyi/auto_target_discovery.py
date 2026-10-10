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
    "transcriptional regulator", "transcriptional repressor",
    "transcriptional activator", "response regulator",
    "global transcriptional regulator", "phosphodiesterase",
    # 耐药酶应通过"耐药"类别正常分类，但若被当作一般酶需排除
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


def search_reviewed_proteins(organism, size=200):
    q = f'organism_name:"{organism}" AND reviewed:true'
    url = "https://rest.uniprot.org/uniprotkb/search?" + urllib.parse.urlencode({
        "query": q,
        "fields": "accession,gene_names,protein_name,length,cc_function,organism_name",
        "size": size, "format": "json",
    })
    data = _curl_json(url)
    return (data or {}).get("results", [])


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


def _classify(info):
    text = " ".join([info["name"], " ".join(info["genes"]),
                     " ".join(info["function"])]).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return None, None
    for keywords, category in KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return category, kw
    return None, None


def _get_sequence(accession):
    url = f"https://rest.uniprot.org/uniprotkb/{accession}?format=json"
    data = _curl_json(url)
    return (data or {}).get("sequence", {}).get("value", "")


def auto_discover_targets(organism, max_targets=15):
    """自动检索 + 筛选靶点，返回靶点 dict（target_id -> 靶点元信息）。"""
    log().info(f"  [自动检索] 检索 {organism} 的 reviewed 蛋白...")
    results = search_reviewed_proteins(organism)
    log().info(f"  [自动检索] 命中 {len(results)} 条 reviewed 蛋白")

    # 第一遍：分类收集所有候选（按类别分桶，去重）
    buckets = {}
    seen = set()
    for r in results:
        info = _extract_info(r)
        category, kw = _classify(info)
        if category is None:
            continue
        if info["length"] < 30 or info["length"] > 1200:
            continue
        gene_key = (info["genes"][0] if info["genes"] else info["accession"]).lower()
        if gene_key in seen:
            continue
        seen.add(gene_key)
        buckets.setdefault(category, []).append((info, kw))

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
                "detect_keyword": kw,
            }
            category_counts[category] = category_counts.get(category, 0) + 1
        if len(targets) >= max_targets:
            break

    log().info(f"  [自动检索] 筛选出 {len(targets)} 个候选靶点")
    for tid, v in targets.items():
        log().info(f"    {tid}: {v['protein']} [{v['mechanism_class']}]")

    # 抓序列
    for tid, v in targets.items():
        if v["uniprot"]:
            v["sequence"] = _get_sequence(v["uniprot"])
            time.sleep(0.4)

    return targets
