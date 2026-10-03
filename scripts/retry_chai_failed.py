"""补救脚本：单独重试 Chai-1 失败的靶点（BasE/LpxC/PmrC）。

策略：每次预测前 wsl --shutdown 重启 WSL 释放显存，降 timesteps 减少显存峰值。
"""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyi.structure_predictor import StructurePredictor
from hoyi import Config

cfg = Config()
kb_path = r'H:\eazyclaw\saved\MASA3\data\antigens\ab_target_knowledge_base.json'
kb = json.load(open(kb_path, encoding='utf-8'))
pdb_dir = r'H:\eazyclaw\saved\MASA3\data\pdbs\ab'

predictor = StructurePredictor(cfg)

# 失败靶点：用降 timesteps 的脚本
failed = ['AB_BasE', 'AB_LpxC', 'AB_PmrC']

for tid in failed:
    seq = kb['targets'][tid]['sequence']
    print(f"\n=== {tid} ({len(seq)}aa) ===")
    # 重启 WSL 释放显存
    subprocess.run(["wsl", "--shutdown"], capture_output=True)
    time.sleep(15)
    # 写 fasta + 脚本（降 timesteps）
    fasta_win = os.path.join(pdb_dir, f"_{tid}.fasta")
    with open(fasta_win, "w") as f:
        f.write(f">protein|{tid}\n{seq}\n")
    fasta_wsl = fasta_win.replace("\\", "/").replace("H:", "/mnt/h")
    chai_out = os.path.join(pdb_dir, f"_{tid}_chai1")
    if os.path.exists(chai_out):
        import shutil; shutil.rmtree(chai_out)
    os.makedirs(chai_out, exist_ok=True)
    chai_out_wsl = chai_out.replace("\\", "/").replace("H:", "/mnt/h")

    # 降 timesteps 的脚本
    script = f'''import os, gc
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("DISABLE_PANDERA_IMPORT_WARNING", "True")
import torch
from pathlib import Path
from chai_lab.chai1 import run_inference

FASTA = Path("{fasta_wsl}")
OUT = Path("{chai_out_wsl}")
OUT.mkdir(parents=True, exist_ok=True)
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
run_inference(fasta_file=FASTA, output_dir=OUT, use_esm_embeddings=False,
    use_msa_server=False, use_templates_server=False, num_trunk_recycles=1,
    num_diffn_timesteps=100, num_diffn_samples=1, num_trunk_samples=1,
    seed=42, low_memory=True)
import glob
cifs = glob.glob(str(OUT) + "/*.cif")
pdbs = glob.glob(str(OUT) + "/*.pdb")
print(f"[{tid}] cif={{len(cifs)}} pdb={{len(pdbs)}}")
if not pdbs and cifs:
    import gemmi
    st = gemmi.read_structure(cifs[0])
    st.write_pdb(str(OUT) + "/{tid}_chai1.pdb")
    print(f"[{tid}] cif->pdb ok")
'''
    script_win = os.path.join(pdb_dir, f"_retry_{tid}.py")
    with open(script_win, "w") as f:
        f.write(script)
    script_wsl = script_win.replace("\\", "/").replace("H:", "/mnt/h")

    full = ("source ~/miniforge3/etc/profile.d/conda.sh && conda activate protein_design && "
            f"export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && "
            f"export DISABLE_PANDERA_IMPORT_WARNING=True && python {script_wsl}")
    r = subprocess.run(["wsl", "-e", "bash", "-lc", full],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    pred_pdb = os.path.join(chai_out, f"{tid}_chai1.pdb")
    if os.path.exists(pred_pdb) and os.path.getsize(pred_pdb) > 1000:
        import shutil
        shutil.copy(pred_pdb, os.path.join(pdb_dir, f"{tid}_chai1.pdb"))
        print(f"{tid}: 成功")
    else:
        print(f"{tid}: 失败")
        print(r.stderr[-600:])

subprocess.run(["wsl", "--shutdown"], capture_output=True)
print("\nDONE")
