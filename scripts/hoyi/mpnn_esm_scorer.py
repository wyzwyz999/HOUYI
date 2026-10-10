"""HOUYI (后羿) —— ProteinMPNN 序列设计 + ESM-2 折叠评分器。

把 RFdiffusion 生成的 binder 骨架（chain B）转成真实序列并评分：
  ProteinMPNN 序列设计（多温度采样）→ ESM-2 650M 折叠质量 composite score。

composite score 校准（复用 MASA² 经验）：emb_norm*100 + pLL*10，>=1020 对应 pLDDT>=90。

供环 3 调用，替换旧版只有"长度优先"的 LengthScorer。
"""
import os
import glob
import json
import subprocess
from .utils import log
import shlex


class MpnnEsmScorer:
    """ProteinMPNN + ESM-2 折叠质量评分器。

    依赖 WSL protein_design 环境（含 transformers + torch）+ ProteinMPNN。
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.mpnn_script = cfg.mpnn_script  # ProteinMPNN 脚本路径（容器可覆盖）
        self.env = cfg.env_mpnn

    def _linux(self, path):
        from .backend import backend
        return backend.to_linux(path)

    def extract_chain(self, pdb_path, out_path, chain="B"):
        """从 RFdiffusion 复合 PDB 提取指定 binder 链。"""
        with open(pdb_path) as fin, open(out_path, "w") as fout:
            for line in fin:
                if line.startswith("ATOM") and line[21] == chain:
                    fout.write(line)
                elif line.startswith(("TER", "END")):
                    fout.write(line)
        return out_path

    def run(self, design_dir, target_id, num_seq_per_target=3,
            temps=(0.10, 0.15, 0.20), dry_run=False,
            allowed_pdb_names=None, binder_chain="B"):
        """对某靶点所有 RFdiffusion 骨架做 MPNN 序列设计 + ESM 评分。

        Args:
            design_dir: RFdiffusion 输出目录（含 *_*.pdb 骨架）
            target_id: 靶点 ID
            num_seq_per_target: 每骨架 ProteinMPNN 采样序列数
            temps: 采样温度列表

        Returns:
            list[dict]: 每条 binder 记录 {target, binder_id, sequence, length, esm_score, pLL, emb_norm}
        """
        design_wsl = self._linux(design_dir)
        mpnn_dir_wsl = self._linux(design_dir + "_mpnn")

        pdbs = sorted([
            f for f in glob.glob(os.path.join(design_dir, "*.pdb"))
            if "traj" not in f
            and not f.endswith(f"_{binder_chain}.pdb")
            and "cont" not in f
        ])

        # Ring3.5 interface gate:
        # 如果提供允许的backbone文件名，只让这些结构进入ProteinMPNN。
        # 不删除原始PDB，仅做流程级过滤。
        if allowed_pdb_names is not None:
            allowed = set(allowed_pdb_names)
            before = len(pdbs)
            pdbs = [
                p for p in pdbs
                if os.path.basename(p) in allowed
            ]

        if not pdbs:
            log().warning(f"  {target_id}: 无骨架可评分")
            return []

        # 把整个评分流程写成 WSL 端 python 脚本执行（避免 PowerShell 转义问题）
        py = self._build_score_script(
            design_wsl,
            mpnn_dir_wsl,
            target_id,
            pdbs,
            num_seq_per_target,
            temps,
            binder_chain,
        )
        # 写入脚本（Windows 侧写，WSL/容器读）
        script_win = os.path.join(design_dir, "_score.py")
        with open(script_win, "w", encoding="utf-8") as f:
            f.write(py)

        if dry_run:
            log().info(f"  [dry-run] {target_id}: 将跑 MPNN+ESM 评分 ({len(pdbs)} 骨架)")
            return []

        from .backend import backend
        python_exe = os.environ.get("HOUYI_PYTHON", "python")
        cmd = (
            "export HF_ENDPOINT=https://hf-mirror.com && "
            f"{shlex.quote(python_exe)} {shlex.quote(self._linux(script_win))}"
        )
        full = backend._wrap(cmd, self.env)
        r = backend.run(full)
        if r.returncode != 0:
            from .utils import CommandError
            raise CommandError(full, r.returncode, r.stderr)

        # 读回结果
        out_json = os.path.join(design_dir, f"{target_id}_esm_scores.json")
        if os.path.exists(out_json):
            results = json.load(open(out_json, encoding="utf-8"))
            log().info(f"  {target_id}: MPNN+ESM 评分 {len(results)} 条")
            return results
        log().warning(f"  {target_id}: 评分结果未生成")
        return []

    def _build_score_script(self, design_wsl, mpnn_dir_wsl, target_id,
                            pdbs, num_seq_per_target, temps,
                            binder_chain):
        """生成 WSL 端 python 评分脚本源码。"""
        temps_str = ", ".join(str(t) for t in temps)
        pdb_names = [os.path.basename(p) for p in pdbs]
        mpnn_root = getattr(self.cfg, "mpnn_root", "/home/zhaoxx/ProteinMPNN")
        return f'''import os, json, glob, subprocess, shlex, torch
from pathlib import Path

DESIGN = "{design_wsl}"
MPNN_DIR = "{mpnn_dir_wsl}"
MPNN = "{mpnn_root}"
TARGET = "{target_id}"
NUMS = {num_seq_per_target}
TEMPS = [{temps_str}]
PDB_NAMES = {pdb_names!r}
BINDER_CHAIN = {binder_chain!r}
OUT_JSON = DESIGN + "/{target_id}_esm_scores.json"

os.makedirs(MPNN_DIR, exist_ok=True)

# 加载 ESM-2 650M
print(f"[{{TARGET}}] 加载 ESM-2 650M...", flush=True)
from transformers import AutoTokenizer, AutoModelForMaskedLM
tokenizer = AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")
model = AutoModelForMaskedLM.from_pretrained("facebook/esm2_t33_650M_UR50D")
model.eval()
if torch.cuda.is_available():
    model = model.to("cuda")

def esm_score(seq):
    if len(seq) < 20:
        return {{"pLL": -99.0, "emb_norm": 0.0, "composite": 0}}
    inputs = tokenizer(seq, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {{k: v.to("cuda") for k, v in inputs.items()}}
    with torch.no_grad():
        out = model(**inputs, output_hidden_states=True)
    hidden = out.hidden_states[-1]
    emb_norm = hidden.norm(dim=-1).mean().item()
    logits = out.logits
    labels = inputs["input_ids"]
    loss_fn = torch.nn.CrossEntropyLoss(reduction="mean")
    pLL = -loss_fn(logits[0, :-1], labels[0, 1:]).item()
    composite = int(emb_norm * 100 + pLL * 10)
    ekr_frac = sum(aa in "EKR" for aa in seq) / len(seq)
    unique_aa = len(set(seq))

    ekr_penalty = max(0.0, ekr_frac - 0.60) * 300
    diversity_penalty = max(0, 10 - unique_aa) * 8
    complexity_penalty = int(round(ekr_penalty + diversity_penalty))
    qc_composite = composite - complexity_penalty

    return {{
        "pLL": round(pLL, 4),
        "emb_norm": round(emb_norm, 4),
        "composite": composite,
        "ekr_frac": round(ekr_frac, 4),
        "unique_aa": unique_aa,
        "complexity_penalty": complexity_penalty,
        "qc_composite": qc_composite,
    }}

def extract_binder_chain(pdb_path, chain):
    out = str(pdb_path).replace(
        ".pdb",
        "_" + chain + ".pdb"
    )
    with open(pdb_path) as fin, open(out, "w") as fout:
        for line in fin:
            if line.startswith("ATOM") and line[21] == chain:
                # 提取出的binder统一重命名为A，
                # 仅用于ProteinMPNN单链输入兼容。
                fout.write(line[:21] + "A" + line[22:])
            elif line.startswith(("TER", "END")):
                fout.write(line)
        fout.write("TER\\nEND\\n")
    return out

def designed_seqs(fa_path):
    with open(fa_path) as f:
        content = f.read()
    seqs = []
    for block in content.strip().split(">")[1:]:
        lines = block.strip().split("\\n")
        seq = "".join(lines[1:]).strip().upper()
        if seq:
            seqs.append(seq)
    # 跳过第一条（ProteinMPNN 输出的原始 backbone 序列，CA-only 下为全 GLY）
    return seqs[1:] if len(seqs) > 1 else []

results = []
for i, name in enumerate(PDB_NAMES):
    pdb_path = DESIGN + "/" + name
    binder_pdb = extract_binder_chain(
        pdb_path,
        BINDER_CHAIN
    )
    catoms = 0
    with open(binder_pdb) as f:
        for line in f:
            if line.startswith("ATOM"):
                catoms += 1
    if catoms < 30:
        print(
            f"  [{{TARGET}}] {{name}}: chain "
            + BINDER_CHAIN
            + f" too small ({{catoms}}), skip",
            flush=True
        )
        continue

    # ProteinMPNN 多温度采样（CA-only：RFdiffusion 只有 backbone，无完整侧链）
    fa_base = name.replace(".pdb", "")
    for temp in TEMPS:
        temp_tag = str(temp).replace(".", "p")
        temp_dir = os.path.join(MPNN_DIR, "temp_" + temp_tag)
        os.makedirs(temp_dir, exist_ok=True)

        cmd = [
            "python", MPNN + "/protein_mpnn_run.py",
            "--pdb_path", binder_pdb,
            # binder已在临时PDB中统一重命名为A
            "--pdb_path_chains", "A",
            "--out_folder", temp_dir,
            "--num_seq_per_target", str(NUMS),
            "--sampling_temp", str(temp),
            "--seed", "42",
            "--batch_size", "1",
            "--ca_only",
        ]

        rr = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=MPNN
        )

        if rr.returncode != 0:
            print(
                "  [" + TARGET + "] " + name + " temp=" + str(temp)
                + ": ProteinMPNN failed: " + rr.stderr,
                flush=True
            )
            continue

        fas = sorted(Path(temp_dir).glob("seqs/*" + fa_base + "*.fa"))
        if not fas:
            print(
                "  [" + TARGET + "] " + name + " temp=" + str(temp)
                + ": no FASTA output",
                flush=True
            )
            continue

        for fa in fas:
            seqs = designed_seqs(str(fa))
            for sample_idx, seq in enumerate(seqs, 1):
                if len(seq) < 20 or len(seq) > 120:
                    continue
                m = esm_score(seq)
                m["target"] = TARGET
                m["binder_id"] = (
                    fa.stem + "_T" + str(temp) + "_sample" + str(sample_idx)
                )
                m["sampling_temp"] = temp
                m["sample"] = sample_idx
                m["sequence"] = seq
                m["length"] = len(seq)
                results.append(m)
    if (i + 1) % 5 == 0:
        print(f"  [{{TARGET}}] {{i+1}}/{{len(PDB_NAMES)}} 骨架完成", flush=True)

results.sort(key=lambda x: x.get("qc_composite", x["composite"]), reverse=True)
with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2)
print(f"[{{TARGET}}] 完成，共 {{len(results)}} 条 binder 序列", flush=True)
'''
