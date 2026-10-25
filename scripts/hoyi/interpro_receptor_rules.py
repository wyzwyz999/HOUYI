"""InterPro / Pfam 结构域证据（Ring7 的补充判定，2026-10-25）。

用途：有些真正的表面受体在 UniProt 里名字只是 `hypothetical protein`、
或者名字里没有受体家族字样，但结构域会明确写 Autotransporter / Adhesin /
Pilin 等。这里按 UniProt accession 查 EBI InterPro，作为"名称判定"的补充。

设计原则：
  - 只读、可缓存、失败即降级：任何网络问题都不允许影响主流程
  - 默认开启，`HOUYI_NO_INTERPRO=1` 可完全关闭（离线/复现阶段）
  - 查询结果落盘到 data/interpro_cache/<ACC>.json，同一 accession 只查一次
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from .utils import log

API = (
    "https://www.ebi.ac.uk/interpro/api/entry/all/protein/uniprot/"
    "{acc}/?page_size=200"
)

# 结构域名 / 家族名 -> 受体家族标签
RECEPTOR_DOMAIN_RULES = [
    (r"autotransporter|two-partner secretion", "Autotransporter"),
    (r"adhesin|adhesion|agglutinin", "Adhesin"),
    (r"hemagglutinin|haemagglutinin", "Hemagglutinin"),
    (r"\bpilin\b|type iv leader peptidase|fimbri|\bpilus\b", "Pilin/Fimbriae"),
    (r"\bporin\b|outer membrane protein|ompa|ompc|ompf", "Outer membrane protein"),
    (r"mscramm|collagen[- ]binding|fibronectin[- ]binding", "MSCRAMM"),
    (r"coagulase", "Coagulase"),
    (r"\byada\b|pertactin|intimin|invasin", "Adhesin"),
    (r"sortase|lpxtg", "Cell-wall anchored"),
    (r"s-layer|surface layer protein", "S-layer"),
]


def _repo_root():
    # scripts/hoyi/domain_evidence.py -> repo root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _cache_dir():
    return os.environ.get(
        "HOUYI_INTERPRO_CACHE",
        os.path.join(_repo_root(), "data", "interpro_cache"),
    )


def is_disabled():
    return os.environ.get("HOUYI_NO_INTERPRO", "0") == "1"


def _cache_path(acc):
    return os.path.join(_cache_dir(), f"{acc}.json")


def _read_cache(acc):
    p = _cache_path(acc)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _write_cache(acc, data):
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        with open(_cache_path(acc), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_domains(acc, timeout=20, retries=2):
    """返回 (ok, [ {db, acc, type, name}, ... ])。失败返回 (False, [])。"""
    cached = _read_cache(acc)
    if cached is not None:
        return True, (cached.get("domains") or [])

    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                API.format(acc=acc),
                headers={"Accept": "application/json", "User-Agent": "HOUYI/2.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
            domains = []
            for item in payload.get("results") or []:
                md = item.get("metadata") or {}
                name = (
                    md.get("name")
                    or (md.get("description") and md["description"][0].get("text"))
                    or ""
                )
                domains.append(
                    {
                        "db": md.get("source_database") or "",
                        "acc": md.get("accession") or "",
                        "type": md.get("type") or "",
                        "name": name,
                    }
                )
            _write_cache(acc, {"accession": acc, "domains": domains})
            return True, domains
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last_err = e
            time.sleep(1.0 + attempt)
    log().warning(f"  [InterPro] {acc} 查询失败，忽略结构域证据: {last_err}")
    return False, []


def classify(acc):
    """返回结构域证据 dict：{ok, accession, domains, family_labels, family_match}。"""
    if not acc or is_disabled():
        return {
            "ok": False,
            "accession": acc,
            "domains": [],
            "family_labels": [],
            "family_match": False,
        }

    ok, domains = fetch_domains(acc)
    labels = []
    for d in domains:
        text = f"{d.get('name', '')} {d.get('acc', '')} {d.get('db', '')}".lower()
        for pattern, family in RECEPTOR_DOMAIN_RULES:
            if re.search(pattern, text):
                labels.append(f"{family}({d.get('acc') or d.get('db')})")
                break

    return {
        "ok": ok,
        "accession": acc,
        "domains": domains,
        "family_labels": sorted(set(labels)),
        "family_match": bool(labels),
    }
