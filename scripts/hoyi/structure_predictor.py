"""HOUYI (后羿) —— 环1 结构自动预测（Phase 5）。

把「结构预测」从"标记来源"升级为"真正拿到结构文件"：
  - 有 PDB：自动从 RCSB 下载结构文件到 data/pdbs/<org>/
  - 无 PDB：自动用 Chai-1 从序列预测结构（单链模式），输出 PDB 供后续 RFdiffusion

依赖：
  - Windows 侧 curl.exe 下载 RCSB
  - WSL protein_design 环境（含 chai_lab 0.6.x）
"""
import os
import time
import json
import subprocess
from .utils import log


class StructurePredictor:
    """环1 结构自动预测：PDB 下载 / Chai-1 预测。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.env = "protein_design"

    def _linux(self, path):
        """把 Windows 视角路径转成执行端（WSL/容器）能读的路径。"""
        from .backend import backend
        return backend.to_linux(path)

    def download_pdb(self, pdb_id, out_dir):
        """从 RCSB 下载 PDB 结构文件。返回本地路径或 None。"""
        out_path = os.path.join(out_dir, f"{pdb_id}.pdb")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path
        url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
        try:
            from .backend import backend
            curl = "curl.exe" if backend.mode == "wsl" else "curl"
            r = subprocess.run([curl, "-s", "-m", "60", "-o", out_path, url],
                               capture_output=True, text=True, timeout=90)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                return out_path
        except Exception as e:
            log().warning(f"  下载 PDB {pdb_id} 失败: {e}")
        return None

    def predict_chai1(self, sequence, target_id, out_dir):
        """用 Chai-1 从序列预测单体结构。返回 PDB 路径或 None。"""
        out_path = os.path.join(out_dir, f"{target_id}_chai1.pdb")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return out_path

        # 无 GPU 时 Chai-1 不可用（纯 CPU 极慢/不支持），诚实提示降级
        from .backend import backend
        if not backend.has_gpu():
            log().warning(f"  {target_id}: 无 GPU，跳过 Chai-1 结构预测（CPU 模式需手动提供 PDB）")
            return None

        # 超长序列（>1000aa）Chai-1 预测不稳（显存/时间），诚实报告需结构域分割
        if len(sequence) > 1000:
            log().warning(f"  {target_id}: 序列 {len(sequence)}aa 过长，Chai-1 预测受限（需结构域分割）")
            return None

        # Chai-1 要求输出目录为空，用独立子目录；FASTA 放父目录（不能放进 chai_out）
        chai_out = os.path.join(out_dir, f"_{target_id}_chai1")
        # 清空旧残留（Chai-1 要求空目录，且上次失败可能留下文件）
        if os.path.exists(chai_out):
            import shutil
            shutil.rmtree(chai_out)
        os.makedirs(chai_out, exist_ok=True)

        # 写 FASTA 到父目录（Chai-1 要求 output_dir 完全空，且 entity type 用 protein）
        fasta_win = os.path.join(out_dir, f"_{target_id}.fasta")
        with open(fasta_win, "w", encoding="utf-8") as f:
            f.write(f">protein|{target_id}\n{sequence}\n")
        fasta_wsl = self._linux(fasta_win)
        chai_out_wsl = self._linux(chai_out)

        pred_script = self._build_chai_script(target_id, fasta_wsl, chai_out_wsl)
        script_win = os.path.join(out_dir, f"_chai_{target_id}.py")
        with open(script_win, "w", encoding="utf-8") as f:
            f.write(pred_script)

        from .backend import backend

        if backend.mode == "wsl":
            conda_base = os.environ.get(
                "HOUYI_CONDA_BASE",
                "~/miniforge3/etc/profile.d/conda.sh"
            )
            full = (
                f"source {conda_base} && "
                f"conda activate {self.env} && "
                f"export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && "
                f"export DISABLE_PANDERA_IMPORT_WARNING=True && "
                f"python {self._linux(script_win)}"
            )
        else:
            # native/container：直接复用当前已验证可 import chai_lab 的 Python
            full = (
                f"export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True && "
                f"export DISABLE_PANDERA_IMPORT_WARNING=True && "
                f"python {self._linux(script_win)}"
            )
        log().info(f"  {target_id}: Chai-1 预测结构（{len(sequence)}aa）...")

        # Chai-1 是重计算任务，偶发资源竞争（WSL 内存尖峰/GPU 显存碎片）会导致瞬时失败。
        # 重试机制：失败时重试，大概率成功（Chai-1 失败多为瞬时 OOM 而非确定性错误）。
        from .backend import backend
        max_retries = int(os.environ.get("HOUYI_CHAI1_RETRIES", "2"))
        for attempt in range(1, max_retries + 1):
            r = backend.run(full)
            if r.returncode == 0:
                break
            stderr_tail = (r.stderr or "").strip()[-500:]
            log().warning(
                f"  {target_id}: Chai-1 预测失败（第 {attempt}/{max_retries} 次）: {stderr_tail}")
            if attempt < max_retries:
                time.sleep(3 * attempt)  # 退避后重试，给 WSL 释放瞬时资源时间
        else:
            log().error(f"  {target_id}: Chai-1 预测失败（已重试 {max_retries} 次）")
            return None

        # 预测产物在 chai_out 子目录里，复制到 out_dir
        pred_pdb = os.path.join(chai_out, f"{target_id}_chai1.pdb")
        if os.path.exists(pred_pdb) and os.path.getsize(pred_pdb) > 1000:
            import shutil
            shutil.copy(pred_pdb, out_path)
            return out_path
        log().warning(f"  {target_id}: Chai-1 未产出结构文件")
        return None

    def _build_chai_script(self, target_id, fasta_wsl, out_wsl):
        """生成 Chai-1 单链预测脚本。"""
        return f'''import os, gc
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("DISABLE_PANDERA_IMPORT_WARNING", "True")
import torch
from pathlib import Path
from chai_lab.chai1 import run_inference

FASTA = Path("{fasta_wsl}")
OUT = Path("{out_wsl}")
OUT.mkdir(parents=True, exist_ok=True)

gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

run_inference(
    fasta_file=FASTA,
    output_dir=OUT,
    use_esm_embeddings=False,
    use_msa_server=False,
    use_templates_server=False,
    num_trunk_recycles=1,
    num_diffn_timesteps=150,
    num_diffn_samples=1,
    num_trunk_samples=1,
    seed=42,
    low_memory=True,
)

# 提取预测的 PDB（cif -> pdb 或直接找 pdb）
import glob
cifs = glob.glob(str(OUT) + "/*.cif")
pdbs = glob.glob(str(OUT) + "/*.pdb")
print(f"[{target_id}] Chai-1 产物: cif={{len(cifs)}} pdb={{len(pdbs)}}")

if not pdbs and cifs:
    try:
        import gemmi
        st = gemmi.read_structure(cifs[0])
        st.write_pdb(str(OUT) + "/{target_id}_chai1.pdb")
        print(f"[{target_id}] cif -> pdb 转换成功")
    except Exception as e:
        print(f"[{target_id}] cif转pdb失败: {{e}}")
elif pdbs:
    import shutil
    shutil.copy(pdbs[0], str(OUT) + "/{target_id}_chai1.pdb")
    print(f"[{target_id}] 复制 pdb 完成")
'''
