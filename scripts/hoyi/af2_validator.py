"""HOUYI —— AF2/ColabFold binder validation.

职责：
1. 解析 ColabFold AlphaFold2-Multimer scores JSON；
2. 汇总多 model / seed 的稳健性指标；
3. 将 AF2 验证摘要合并回候选记录；
4. 输出 ring4_af2_validated.json。

后续可扩展：
- 自动准备 target:binder FASTA
- 自动调用 colabfold_batch
"""

import json
import os
import re
import shlex
import statistics
from pathlib import Path

from .utils import log, save_json


class AF2Validator:
    """AF2-Multimer 结果解析与稳健性验证。"""

    def __init__(self, cfg):
        self.cfg = cfg

    @staticmethod
    def _mean_value(value):
        if isinstance(value, dict):
            vals = [v for v in value.values()
                    if isinstance(v, (int, float))]
            return statistics.mean(vals) if vals else None

        if isinstance(value, list):
            vals = [v for v in value
                    if isinstance(v, (int, float))]
            return statistics.mean(vals) if vals else None

        if isinstance(value, (int, float)):
            return float(value)

        return None

    @staticmethod
    def extract_pdb_chain_sequence(pdb_path, chain="A"):
        """从 PDB 中提取指定链的一字母氨基酸序列及残基范围。"""

        aa3to1 = {
            "ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C",
            "GLN":"Q","GLU":"E","GLY":"G","HIS":"H","ILE":"I",
            "LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P",
            "SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V",
            "MSE":"M",
        }

        pdb_path = Path(pdb_path)

        if not pdb_path.exists():
            raise FileNotFoundError(f"PDB不存在: {pdb_path}")

        seen = set()
        residues = []

        with pdb_path.open() as f:
            for line in f:
                if not line.startswith("ATOM"):
                    continue
                if len(line) < 26 or line[21] != chain:
                    continue

                resn = line[17:20].strip()

                try:
                    resi = int(line[22:26])
                except ValueError:
                    continue

                key = (chain, resi)
                if key in seen:
                    continue

                seen.add(key)
                residues.append(
                    (resi, aa3to1.get(resn, "X"))
                )

        if not residues:
            raise ValueError(
                f"PDB {pdb_path} 中未找到 chain {chain}"
            )

        seq = "".join(aa for _, aa in residues)

        return {
            "sequence": seq,
            "length": len(seq),
            "start": residues[0][0],
            "end": residues[-1][0],
            "chain": chain,
        }

    @staticmethod
    def prepare_fasta(target_sequence, binder_sequence,
                      binder_id, out_path):
        """生成 ColabFold multimer 输入 FASTA。"""

        target_sequence = (
            target_sequence.strip().replace(" ", "").replace("\n", "")
        )
        binder_sequence = (
            binder_sequence.strip().replace(" ", "").replace("\n", "")
        )

        if not target_sequence:
            raise ValueError("target sequence 为空")

        if not binder_sequence:
            raise ValueError("binder sequence 为空")

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w") as f:
            f.write(f">{binder_id}\n")
            f.write(f"{target_sequence}:{binder_sequence}\n")

        return str(out_path)

    @staticmethod
    def select_candidates(candidates, top_k=3):
        """按 target 分组，优先 qc_composite 选择 AF2 待验证候选。"""

        groups = {}

        for c in candidates:
            target = c.get("target")
            if not target:
                continue
            groups.setdefault(target, []).append(c)

        selected = []

        def rank_score(c):
            for key in ("qc_composite", "composite", "score"):
                value = c.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
            return float("-inf")

        for target, items in groups.items():
            items = sorted(
                items,
                key=rank_score,
                reverse=True,
            )
            selected.extend(items[:top_k])

        return selected

    def run_colabfold(self, fasta_path, out_dir,
                        num_models=5,
                        num_seeds=3,
                        num_recycles=6,
                        dry_run=False):
        """调用 ColabFold/AF2-Multimer 验证一个 target:binder FASTA。"""

        from .backend import backend

        fasta_path = Path(fasta_path)
        out_dir = Path(out_dir)

        if not fasta_path.exists():
            raise FileNotFoundError(f"AF2 FASTA不存在: {fasta_path}")

        colabfold_bin = os.environ.get(
            "HOUYI_COLABFOLD_BIN",
            "colabfold_batch",
        )

        data_dir = os.environ.get(
            "HOUYI_COLABFOLD_DATA",
            "",
        )

        if not Path(colabfold_bin).exists():
            raise FileNotFoundError(
                f"colabfold_batch不存在: {colabfold_bin}"
            )

        if not data_dir:
            raise RuntimeError(
                "HOUYI_COLABFOLD_DATA 未设置"
            )

        if not Path(data_dir).exists():
            raise FileNotFoundError(
                f"ColabFold参数目录不存在: {data_dir}"
            )

        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = " ".join([
            shlex.quote(colabfold_bin),
            shlex.quote(str(fasta_path)),
            shlex.quote(str(out_dir)),
            "--msa-mode", "mmseqs2_uniref_env",
            "--pair-mode", "unpaired_paired",
            "--pair-strategy", "greedy",
            "--model-type", "alphafold2_multimer_v3",
            "--num-models", str(num_models),
            "--num-seeds", str(num_seeds),
            "--num-recycle", str(num_recycles),
            "--num-relax", "0",
            "--data", shlex.quote(data_dir),
        ])

        log().info(
            f"AF2/ColabFold: models={num_models}, "
            f"seeds={num_seeds}, recycles={num_recycles}"
        )

        if dry_run:
            log().info(f"[dry-run] {cmd}")
            return {
                "returncode": 0,
                "command": cmd,
                "out_dir": str(out_dir),
                "dry_run": True,
            }

        r = backend.run(
            cmd,
            env_name=None,
            timeout=None,
            capture=True,
            text=True,
        )

        if r.returncode != 0:
            stderr_tail = (r.stderr or "").strip()[-2000:]
            raise RuntimeError(
                f"ColabFold运行失败，returncode={r.returncode}\n"
                f"{stderr_tail}"
            )

        return {
            "returncode": r.returncode,
            "command": cmd,
            "out_dir": str(out_dir),
            "stdout": r.stdout,
            "stderr": r.stderr,
        }


    def validate_selected_candidates(
        self,
        candidates,
        target_pdb=None,
        target_chain="A",
        target_sequence=None,
        top_k=3,
        work_dir=None,
        num_models=5,
        num_seeds=3,
        num_recycles=6,
        reuse_existing=True,
        dry_run=False,
        save_output=True,
    ):
        """批量执行 Ring4 Top-K 候选的 AF2-Multimer 验证。

        优先从 target_pdb + target_chain 提取与 RFdiffusion 一致的
        target 序列；也允许显式传入 target_sequence 便于测试。

        流程：
        select_candidates
        -> prepare_fasta
        -> run/reuse ColabFold
        -> validate_candidate
        -> save_validated
        """

        selected = self.select_candidates(
            candidates,
            top_k=top_k,
        )

        if not selected:
            raise ValueError("没有可用于 AF2 验证的候选")

        # 正式流程优先使用 PDB chain，保证与 RFdiffusion target 一致。
        if target_pdb is not None:
            target_info = self.extract_pdb_chain_sequence(
                target_pdb,
                chain=target_chain,
            )
            target_sequence = target_info["sequence"]

        if not target_sequence:
            raise ValueError(
                "必须提供 target_pdb 或 target_sequence"
            )

        if work_dir is None:
            work_dir = (
                Path(self.cfg.results_dir)
                / "af2_validation"
            )
        else:
            work_dir = Path(work_dir)

        work_dir.mkdir(parents=True, exist_ok=True)

        validated = []
        expected_n = int(num_models) * int(num_seeds)

        for candidate in selected:
            binder_id = candidate.get("binder_id")
            binder_sequence = candidate.get("sequence")

            if not binder_id:
                raise ValueError("候选缺少 binder_id")
            if not binder_sequence:
                raise ValueError(
                    f"{binder_id} 缺少 sequence"
                )

            safe_id = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "_",
                str(binder_id),
            )

            # AF2缓存必须同时匹配 binder_id 和实际 target:binder 序列。
            # ProteinMPNN重跑后，同一个binder_id可能对应不同sequence；
            # 此时绝不能复用旧AF2结果。
            import hashlib

            expected_fasta = (
                f">{binder_id}\n"
                f"{target_sequence}:{binder_sequence}\n"
            )

            candidate_dir = work_dir / safe_id
            fasta_path = candidate_dir / "input.fasta"

            # 若旧目录存在但FASTA与当前序列不一致，
            # 改用带序列hash的新目录，保留旧结果同时避免污染。
            if candidate_dir.exists():
                existing_fasta = None

                if fasta_path.exists():
                    try:
                        existing_fasta = fasta_path.read_text()
                    except Exception:
                        existing_fasta = None

                if (
                    existing_fasta is not None
                    and existing_fasta.strip()
                    != expected_fasta.strip()
                ):
                    seq_hash = hashlib.sha256(
                        f"{target_sequence}:{binder_sequence}".encode()
                    ).hexdigest()[:10]

                    log().warning(
                        f"{binder_id}: 检测到同名候选序列已变化，"
                        f"禁止复用旧AF2缓存；切换到 {safe_id}__{seq_hash}"
                    )

                    candidate_dir = (
                        work_dir / f"{safe_id}__{seq_hash}"
                    )
                    fasta_path = candidate_dir / "input.fasta"

            result_dir = candidate_dir / "colabfold"

            # 只有当前目录中的FASTA与本次序列完全一致，
            # 才允许把已有score文件认定为可复用缓存。
            fasta_matches = False

            if fasta_path.exists():
                try:
                    fasta_matches = (
                        fasta_path.read_text().strip()
                        == expected_fasta.strip()
                    )
                except Exception:
                    fasta_matches = False

            score_files = list(
                result_dir.glob(
                    "*_scores_rank_*_alphafold2_multimer_v3_"
                    "model_*_seed_*.json"
                )
            )

            complete_existing = (
                reuse_existing
                and fasta_matches
                and len(score_files) >= expected_n
            )

            if complete_existing:
                log().info(
                    f"复用已有 AF2 结果 {binder_id}: "
                    f"{len(score_files)} predictions "
                    f"[FASTA一致]"
                )
            else:
                # 未命中可靠缓存时，先写入本次准确FASTA，
                # 再启动ColabFold。
                self.prepare_fasta(
                    target_sequence=target_sequence,
                    binder_sequence=binder_sequence,
                    binder_id=binder_id,
                    out_path=fasta_path,
                )

                run_info = self.run_colabfold(
                    fasta_path=fasta_path,
                    out_dir=result_dir,
                    num_models=num_models,
                    num_seeds=num_seeds,
                    num_recycles=num_recycles,
                    dry_run=dry_run,
                )

                if dry_run:
                    out = candidate.copy()
                    out["af2_validation"] = {
                        "dry_run": True,
                        "result_dir": str(result_dir),
                        "command": run_info["command"],
                    }
                    validated.append(out)
                    continue

            out = self.validate_candidate(
                candidate=candidate,
                result_dir=result_dir,
            )

            validated.append(out)

        if dry_run:
            return validated

        if save_output:
            return self.save_validated(validated)

        return validated

    def parse_result_dir(self, result_dir):
        """解析一个候选的 ColabFold 输出目录。"""
        result_dir = Path(result_dir)

        files = sorted(
            result_dir.glob("*_scores_rank_*_alphafold2_multimer_v3_model_*_seed_*.json")
        )

        if not files:
            raise FileNotFoundError(
                f"未找到 AF2-Multimer scores JSON: {result_dir}"
            )

        rows = []

        for f in files:
            d = json.loads(f.read_text())

            model_match = re.search(r"model_(\d+)", f.name)
            seed_match = re.search(r"seed_(\d+)", f.name)

            plddt = self._mean_value(d.get("plddt"))
            ptm = self._mean_value(d.get("ptm"))
            iptm = self._mean_value(d.get("iptm"))
            ipsae = self._mean_value(
                d.get("ipsae", d.get("ipSAE"))
            )
            pdockq2 = self._mean_value(
                d.get("pdockq2", d.get("pDockQ2"))
            )

            rows.append({
                "model": int(model_match.group(1)) if model_match else None,
                "seed": int(seed_match.group(1)) if seed_match else None,
                "plddt": plddt,
                "ptm": ptm,
                "iptm": iptm,
                "ipsae": ipsae,
                "pdockq2": pdockq2,
                "score_file": str(f),
            })

        return rows

    @staticmethod
    def summarize(rows):
        """汇总多 model / seed AF2 结果。"""

        def values(key):
            return [
                r[key] for r in rows
                if isinstance(r.get(key), (int, float))
            ]

        iptm = values("iptm")
        ptm = values("ptm")
        plddt = values("plddt")
        ipsae = values("ipsae")
        pdockq2 = values("pdockq2")

        if not iptm:
            raise ValueError("AF2结果中没有有效 ipTM")

        best = max(rows, key=lambda r: (
            r.get("iptm")
            if isinstance(r.get("iptm"), (int, float))
            else float("-inf")
        ))

        summary = {
            "num_predictions": len(rows),

            "iptm_min": round(min(iptm), 3),
            "iptm_max": round(max(iptm), 3),
            "iptm_mean": round(statistics.mean(iptm), 3),
            "iptm_median": round(statistics.median(iptm), 3),

            "iptm_ge_0_5": sum(v >= 0.5 for v in iptm),
            "iptm_ge_0_6": sum(v >= 0.6 for v in iptm),
            "iptm_ge_0_7": sum(v >= 0.7 for v in iptm),

            "ptm_mean": round(statistics.mean(ptm), 3) if ptm else None,
            "plddt_mean": round(statistics.mean(plddt), 3) if plddt else None,
            "ipsae_mean": round(statistics.mean(ipsae), 3) if ipsae else None,
            "pdockq2_mean": round(statistics.mean(pdockq2), 3)
            if pdockq2 else None,

            "best_model": best.get("model"),
            "best_seed": best.get("seed"),
            "best_iptm": best.get("iptm"),
            "best_score_file": best.get("score_file"),
        }

        return summary

    @staticmethod
    def classify_confidence(rows):
        """
        基于多次 AF2-Multimer 预测的稳健统计进行分层。

        HIGH:
            中位数 ipTM >= 0.70
            且 >= 60% 预测 ipTM >= 0.70

        INTERMEDIATE:
            中位数 ipTM >= 0.60
            或 >= 50% 预测 ipTM >= 0.60
            或 best ipTM >= 0.70

        LOW:
            其余情况

        不使用 min(ipTM) 作为硬门槛，避免单个异常 seed
        否定多数模型支持的候选。
        """
        import statistics

        iptm = [
            r.get("iptm") for r in rows
            if isinstance(r.get("iptm"), (int, float))
        ]

        if not iptm:
            return "LOW"

        median_iptm = statistics.median(iptm)
        best_iptm = max(iptm)

        frac_ge_07 = sum(v >= 0.70 for v in iptm) / len(iptm)
        frac_ge_06 = sum(v >= 0.60 for v in iptm) / len(iptm)

        if (
            median_iptm >= 0.70
            and frac_ge_07 >= 0.60
        ):
            return "HIGH"

        if (
            median_iptm >= 0.60
            or frac_ge_06 >= 0.50
            or best_iptm >= 0.70
        ):
            return "INTERMEDIATE"

        return "LOW"

    @staticmethod
    def passes(rows):
        """
        兼容现有 Ring5。
        只有 HIGH confidence 才记为 passed=True。
        """
        return AF2Validator.classify_confidence(rows) == "HIGH"

    def validate_candidate(self, candidate, result_dir,
                           representative_pdb=None):
        """把 AF2 验证结果合并到一个候选记录。"""

        rows = self.parse_result_dir(result_dir)
        summary = self.summarize(rows)

        summary["passed"] = self.passes(rows)
        summary["confidence"] = self.classify_confidence(rows)
        summary["model_type"] = "alphafold2_multimer_v3"

        if representative_pdb:
            summary["representative_pdb"] = str(representative_pdb)

        out = candidate.copy()
        out["af2_validation"] = summary

        log().info(
            f"AF2验证 {candidate.get('binder_id')}: "
            f"n={summary['num_predictions']} "
            f"ipTM={summary['iptm_min']:.3f}-"
            f"{summary['iptm_max']:.3f}, "
            f"mean={summary['iptm_mean']:.3f}, "
            f"passed={summary['passed']}"
        )

        return out

    def save_validated(self, candidates):
        """仅保存通过 AF2 验证的候选。"""
        passed = [
            c for c in candidates
            if c.get("af2_validation", {}).get("passed")
        ]

        save_json(self.cfg.ring4_af2_validated_out, passed)

        log().info(
            f"AF2 validated 输出: "
            f"{self.cfg.ring4_af2_validated_out} "
            f"({len(passed)} 条)"
        )

        return passed
