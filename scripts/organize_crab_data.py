"""整理鲍曼不动杆菌设计全部数据到 output CRAB 目录，结构化 + 附 README 说明。
复制：靶点知识库/靶点序列/结构预测/骨架/评分/最终载荷/日志/脚本。
"""
import os, json, shutil

BASE = r"H:\eazyclaw\saved\MASA3"
OUT = os.path.join(BASE, "output CRAB")

def mkd(*p):
    d = os.path.join(OUT, *p)
    os.makedirs(d, exist_ok=True)
    return d

def cp(src, dst_dir, newname=None):
    if not os.path.exists(src):
        print(f"  [skip] 不存在: {src}")
        return
    dst = os.path.join(dst_dir, newname or os.path.basename(src))
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    print(f"  [copy] {src} -> {dst}")

print("=== 01 靶点知识库 ===")
cp(os.path.join(BASE, "data", "antigens", "ab_target_knowledge_base.json"), mkd("01_靶点知识库"))

print("\n=== 02 靶点序列 ===")
d02 = mkd("02_靶点序列")
cp(os.path.join(BASE, "results", "ring1_targets.json"), d02)

# 生成靶点序列 FASTA
r1 = json.load(open(os.path.join(BASE, "results", "ring1_targets.json"), encoding="utf-8"))
tmeta = r1.get("target_meta", {})
fasta_path = os.path.join(d02, "ab_targets_sequences.fasta")
with open(fasta_path, "w", encoding="utf-8") as f:
    for t, m in tmeta.items():
        seq = m.get("sequence", "")
        if seq:
            f.write(f">{t} | {m.get('protein','')} | UniProt={m.get('uniprot','')} | {m.get('length_aa','')}aa\n{seq}\n")
print(f"  [gen] 靶点序列 FASTA -> {fasta_path}")

print("\n=== 03 结构预测 ===")
d03 = mkd("03_结构预测", "structures")
for f in os.listdir(os.path.join(BASE, "data", "pdbs", "ab")):
    if f.endswith(".pdb"):
        cp(os.path.join(BASE, "data", "pdbs", "ab", f), d03)
cp(os.path.join(BASE, "results", "ring2_structure.json"), mkd("03_结构预测"))

print("\n=== 04 Binder骨架 RFdiffusion ===")
d04 = mkd("04_Binder骨架_RFdiffusion")
designs = os.path.join(BASE, "data", "designs", "ab")
for t in os.listdir(designs):
    rfd = os.path.join(designs, t, "rfdiffusion")
    if os.path.isdir(rfd):
        # 只复制骨架 pdb/trb，跳过 _B.pdb(提取链B) 和 _score.py
        dst_t = os.path.join(d04, t)
        os.makedirs(dst_t, exist_ok=True)
        n = 0
        for f in os.listdir(rfd):
            if f.endswith(".pdb") and not f.endswith("_B.pdb"):
                shutil.copy2(os.path.join(rfd, f), os.path.join(dst_t, f))
                n += 1
            elif f.endswith(".trb"):
                shutil.copy2(os.path.join(rfd, f), os.path.join(dst_t, f))
        print(f"  [copy] {t}: {n} 骨架 + trb -> {dst_t}")

print("\n=== 05 评分结果 ===")
d05 = mkd("05_评分结果")
cp(os.path.join(BASE, "results", "ring4_scored.json"), d05)
d05b = mkd("05_评分结果", "per_target_esm_scores")
for t in os.listdir(designs):
    j = os.path.join(designs, t, "rfdiffusion", f"{t}_esm_scores.json")
    if os.path.exists(j):
        shutil.copy2(j, os.path.join(d05b, f"{t}_esm_scores.json"))

print("\n=== 06 最终载荷 ===")
d06 = mkd("06_最终载荷")
for f in ["payloads.fasta", "payloads.json", "top_binders.fasta", "top_binders.json"]:
    cp(os.path.join(BASE, "results", f), d06)

print("\n=== 07 运算日志 ===")
d07 = mkd("07_运算日志")
for f in os.listdir(os.path.join(BASE, "results")):
    if f.startswith("ab_") and f.endswith(".log"):
        cp(os.path.join(BASE, "results", f), d07)

print("\n=== 08 脚本 ===")
d08 = mkd("08_脚本")
for f in os.listdir(os.path.join(BASE, "scripts")):
    if f.startswith("run_ab") or f.startswith("retry") or f.startswith("test_ompA"):
        cp(os.path.join(BASE, "scripts", f), d08)
# hoyi 核心包
cp(os.path.join(BASE, "scripts", "hoyi"), d08, "hoyi")

print("\n=== 09 报告 ===")
d09 = mkd("09_报告")
rpt = os.path.join(OUT, "CRAB_载荷设计报告.html")
if os.path.exists(rpt):
    shutil.copy2(rpt, os.path.join(d09, "CRAB_载荷设计报告.html"))

print("\n全部整理完成。")
