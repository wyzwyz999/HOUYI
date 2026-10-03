#!/usr/bin/env python3
"""ESMFold 批量预测 27 条结核杆菌 binder（HuggingFace EsmForProteinFolding）。

用法: 在 WSL esmfold_full 环境运行。
  python "/mnt/h/eazyclaw/saved/MASA3/scripts/run_esmfold_tb.py"
"""
import os
import json

import torch
torch.set_grad_enabled(False)

FASTA = "/mnt/h/eazyclaw/saved/MASA3/output data TB/1_最终结果/binder_27.fasta"
OUTDIR = "/mnt/h/eazyclaw/saved/MASA3/output data TB/6_ESMFold验证"
WEIGHTS_DIR = "/mnt/h/AI_Models/huggingface/hub/esmfold_merged"

os.makedirs(OUTDIR, exist_ok=True)

def read_fasta(path):
    seqs, name, buf = [], None, []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name:
                    seqs.append((name, "".join(buf)))
                name = line[1:]
                buf = []
            else:
                buf.append(line)
        if name:
            seqs.append((name, "".join(buf)))
    return seqs

seqs = read_fasta(FASTA)
print(f"[ESMFold] 读取 {len(seqs)} 条序列", flush=True)

from transformers import EsmForProteinFolding
from transformers.models.esm.tokenization_esm import EsmTokenizer
from transformers.models.esm.openfold_utils.protein import to_pdb
from transformers.models.esm.openfold_utils.feats import atom14_to_atom37

print("[ESMFold] 加载 tokenizer + 模型 ...", flush=True)
tokenizer = EsmTokenizer(vocab_file=os.path.join(WEIGHTS_DIR, "vocab.txt"))
model = EsmForProteinFolding.from_pretrained(
    WEIGHTS_DIR,
    local_files_only=True,
    use_safetensors=True,
    torch_dtype=torch.float32,
).eval().cuda()
model.esm = model.esm.half()  # 用 fp16 ESM trunk 省显存，与原版一致
print("[ESMFold] 模型加载完成，GPU:", torch.cuda.get_device_name(0), flush=True)

results = []
for i, (name, seq) in enumerate(seqs, 1):
    print(f"[{i}/{len(seqs)}] 预测 {name} (len={len(seq)}) ...", flush=True)
    try:
        inputs = tokenizer([seq], return_tensors="pt", add_special_tokens=False).to("cuda")
        with torch.no_grad():
            output = model(**inputs)

        # 提取 pLDDT（取有效残基长度）
        positions = output.positions[-1].contiguous()  # [B, L, 14, 3] 或 [B, L, 27, 3]
        plddt = output.plddt  # [B, L]
        ptm = output.ptm  # 标量张量

        L = len(seq)
        mean_plddt = plddt[0, :L].mean().item()
        mean_ptm = ptm.item() if hasattr(ptm, "item") else float(ptm)

        # 生成 PDB
        if positions.shape[2] == 14:
            final_atom_positions = atom14_to_atom37(positions[0], output)[:L]
        else:
            final_atom_positions = positions[0][:L]  # 已是 atom37

        final_atom_mask = torch.ones(L, 37).to(positions.device)
        pdb_str = to_pdb("A", seq[:L], final_atom_positions, None, final_atom_mask, residue_index_offset=0)
        # to_pdb 返回 (pdb_str, mean_plddt) 元组则解包
        if isinstance(pdb_str, tuple):
            pdb_str = pdb_str[0]

        pdb_path = os.path.join(OUTDIR, f"{name}.pdb")
        with open(pdb_path, "w") as f:
            f.write(pdb_str)

        results.append({
            "name": name,
            "length": L,
            "mean_plddt": round(mean_plddt, 2),
            "ptm": round(mean_ptm, 3),
        })
        print(f"    -> mean_pLDDT={mean_plddt:.2f}  pTM={mean_ptm:.3f}", flush=True)
    except Exception as e:
        import traceback
        print(f"    !! 失败: {e}", flush=True)
        traceback.print_exc()
        results.append({"name": name, "length": len(seq), "error": str(e)})

summary_path = os.path.join(OUTDIR, "esmfold_summary.json")
with open(summary_path, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n===== ESMFold 验证结果（按 pLDDT 排序）=====")
ok = [r for r in results if "error" not in r]
ok.sort(key=lambda r: r["mean_plddt"], reverse=True)
for r in ok:
    tier = "S(≥95)" if r["mean_plddt"] >= 95 else ("A(≥90)" if r["mean_plddt"] >= 90 else ("B(≥85)" if r["mean_plddt"] >= 85 else "C(<85)"))
    print(f"  {r['name']:<32s} pLDDT={r['mean_plddt']:6.2f}  pTM={r['ptm']:5.3f}  {tier}")

n_s = sum(1 for r in ok if r["mean_plddt"] >= 95)
n_a = sum(1 for r in ok if 90 <= r["mean_plddt"] < 95)
n_b = sum(1 for r in ok if 85 <= r["mean_plddt"] < 90)
n_c = len(ok) - n_s - n_a - n_b
print(f"\nS(≥95): {n_s} | A(≥90): {n_a} | B(≥85): {n_b} | C(<85): {n_c}")
print(f"汇总已保存: {summary_path}")
