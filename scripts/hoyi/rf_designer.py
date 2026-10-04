"""HOUYI (后羿) —— RFdiffusion binder 设计器。

把 RFdiffusion 从头设计 binder 骨架的能力封装成可复用的模块，
供环 2 调用（替代旧版"只复用现成 binder 库"的空壳逻辑）。

核心能力：
  - 自动探测靶点 PDB 的链/残基号范围
  - 自动构建 contig（[chain start-end/0 40-90]）
  - 调用 run_inference.py 生成 binder 骨架（chain B）
  - 断点续跑（已生成的骨架不重复）
  - 流式进度回调（逐骨架实时推送，供 Web 前端展示）
"""
import os
import glob
import re
import shlex
import subprocess
import threading
from .utils import log


class RFdiffusionDesigner:
    """RFdiffusion 从头设计 binder 骨架。

    依赖 WSL + protein_design 环境 + /home/zhaoxx/RFdiffusion。
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.rfd_script = cfg.rfd_script
        self.env = cfg.env_rf if hasattr(cfg, "env_rf") else "protein_design"

    def _linux(self, path):
        """Windows 视角路径 -> 执行端（WSL/容器）路径。"""
        from .backend import backend
        return backend.to_linux(path)

    def _argv(self, full_cmd):
        """完整命令 -> subprocess argv（wsl 用 wsl -e，容器直接 bash）。"""
        from .backend import backend
        return backend._argv(full_cmd)

    def probe_chain(self, pdb_path, chain="A"):
        """探测 PDB 中指定链的实际残基号范围 [start, end]（PDB 残基号可能非 1 起）。"""
        start, end = None, None
        if not os.path.exists(pdb_path):
            return None
        with open(pdb_path) as f:
            for line in f:
                if not line.startswith("ATOM"):
                    continue
                if len(line) < 22 or line[21] != chain:
                    continue
                try:
                    resn = int(line[22:26])
                except ValueError:
                    continue
                if start is None or resn < start:
                    start = resn
                if end is None or resn > end:
                    end = resn
        if start is None:
            return None
        return start, end

    def _chain_has_gap(self, pdb_path, chain="A"):
        """检查链的残基号是否连续（RFdiffusion 的 contig 要求连续残基号）。

        返回 (has_gap, resi_list)。若 PDB 残基号有缺失（如 57→59 缺 58），
        RFdiffusion 会 assert 失败（MASA² 踩坑），需 reindex。
        """
        resis = []
        if not os.path.exists(pdb_path):
            return True, resis
        with open(pdb_path) as f:
            for line in f:
                if not line.startswith("ATOM") or line[21] != chain:
                    continue
                try:
                    rn = int(line[22:26])
                except ValueError:
                    continue
                if rn not in resis:
                    resis.append(rn)
        has_gap = any(resis[i] - resis[i - 1] != 1 for i in range(1, len(resis)))
        return has_gap, resis

    def _reindex_pdb(self, pdb_path, chain="A"):
        """把链的残基重新编号为连续 1..N，生成 *_cont.pdb（RFdiffusion 兼容）。

        保留所有 ATOM/HETATM 记录，仅重写链内残基号（同一原残基号映射到同一新号）。
        返回 reindex 后的 PDB 路径（与原文件同目录，文件名加 _cont 后缀）。
        """
        base, ext = os.path.splitext(pdb_path)
        out_path = base + "_cont" + ext

        # 建立 原残基号 -> 新连续号 映射（按首次出现顺序）
        mapping = {}
        with open(pdb_path) as f:
            for line in f:
                if line.startswith("ATOM") and line[21] == chain:
                    try:
                        rn = int(line[22:26])
                    except ValueError:
                        continue
                    if rn not in mapping:
                        mapping[rn] = len(mapping) + 1

        with open(pdb_path) as fin, open(out_path, "w") as fout:
            for line in fin:
                if line.startswith("ATOM") and line[21] == chain:
                    try:
                        rn = int(line[22:26])
                    except ValueError:
                        fout.write(line)
                        continue
                    new_rn = mapping[rn]
                    # 保留列宽：残基号字段为 22:26（右对齐4字符）
                    line = line[:22] + f"{new_rn:4d}" + line[26:]
                    fout.write(line)
                else:
                    fout.write(line)
        return out_path

    def design(self, target_id, pdb_path, chain="A",
               num_designs=32, binder_min=40, binder_max=90,
               out_dir=None, dry_run=False, progress_cb=None):
        """为一个靶点生成 binder 骨架。

        Args:
            target_id: 靶点 ID
            pdb_path: 靶点结构 PDB（WSL 视角路径）
            chain: 目标链
            num_designs: 期望骨架总数
            binder_min/max: binder 长度范围
            out_dir: 输出目录（Windows 视角，用于断点续跑计数）
            dry_run: 仅预览
            progress_cb: 进度回调 cb(target_id, done, total)，done 为该靶点已完成骨架数

        Returns:
            dict: {target_id, n_scaffolds, out_dir}
        """
        # 探测链残基号
        rng = self.probe_chain(pdb_path, chain)
        if rng is None:
            raise ValueError(f"{target_id}: PDB {pdb_path} 链 {chain} 无原子，无法设计")
        start, end = rng

        # 无 GPU 时 RFdiffusion 不可用（需 CUDA），诚实提示降级
        from .backend import backend
        if not dry_run and not backend.has_gpu():
            log().warning(f"  {target_id}: 无 GPU，跳过 RFdiffusion binder 设计（CPU 模式需复用现有 binder 库）")
            return {"target_id": target_id, "n_scaffolds": 0, "out_dir": out_dir,
                    "skipped": "no_gpu"}

        # 残基号不连续检测：RFdiffusion 的 contig 要求连续残基号，
        # 若 PDB 有 gap（如 57→59 缺 58）需 reindex 成连续 1..N（MASA² 踩坑）
        has_gap, _ = self._chain_has_gap(pdb_path, chain)
        if has_gap:
            pdb_path = self._reindex_pdb(pdb_path, chain)
            start, end = 1, len({line[22:26] for line in open(pdb_path)
                                 if line.startswith("ATOM") and line[21] == chain})
            log().info(f"  {target_id}: 检测到残基号 gap，已 reindex 为连续 1..{end} ({os.path.basename(pdb_path)})")

        # 断点续跑：已有骨架计数
        if out_dir:
            existing = len([f for f in glob.glob(os.path.join(out_dir, "*.pdb"))
                            if "traj" not in f])
        else:
            existing = 0
        need = max(0, num_designs - existing)
        if need == 0:
            log().info(f"  {target_id}: 已有 {existing} 骨架，跳过")
            return {"target_id": target_id, "n_scaffolds": existing, "out_dir": out_dir}

        out_prefix_wsl = self._linux(out_dir)
        pdb_wsl = self._linux(pdb_path)
        contig = f"[{chain}{start}-{end}/0 {binder_min}-{binder_max}]"

        log().info(f"  {target_id}: RFdiffusion 设计 {need} 骨架 "
                   f"(chain {chain} {start}-{end}, binder {binder_min}-{binder_max}aa)")

        rfd_root = getattr(self.cfg, "rfd_root", "/home/zhaoxx/RFdiffusion")

        schedule_file = os.path.join(
            rfd_root,
            "schedules",
            "T_50_omega_1000_min_sigma_0_02_min_b_1_5_max_b_2_5_schedule_linear.pkl",
        )
        output_prefix = f"{out_prefix_wsl}/{target_id}_"

        # shell 路径安全转义，兼容包含空格的目录
        clean_cmd = f"rm -f {shlex.quote(schedule_file)}"
        cmd = (
            f"{clean_cmd} && "
            f"cd {shlex.quote(rfd_root)} && "
            f"python -u scripts/run_inference.py "
            f"{shlex.quote(f'inference.output_prefix={output_prefix}')} "
            f"{shlex.quote(f'inference.input_pdb={pdb_wsl}')} "
            f"{shlex.quote(f'inference.ckpt_override_path={self.cfg.rfd_ckpt}')} "
            f"{shlex.quote(f'contigmap.contigs={contig}')} "
            f"inference.num_designs={need} "
            f"denoiser.noise_scale_ca=0.5 "
            f"denoiser.noise_scale_frame=0.5 "
            f"diffuser.T=50"
        )

        if dry_run:
            log().info(f"  [dry-run] 将执行: {cmd[:150]}...")
            return {"target_id": target_id, "n_scaffolds": 0, "out_dir": out_dir, "dry_run": True}

        # 执行（后端无关：WSL/容器）—— 流式读 stdout，逐骨架推进度
        from .backend import backend
        full = backend._wrap(cmd, self.env)
        r = self._run_streaming(full, target_id, existing, num_designs,
                                out_dir=out_dir, progress_cb=progress_cb)

        if r.returncode != 0:
            # RFdiffusion 偶发非零退出但骨架已生成，需判断
            new_count = len([f for f in glob.glob(os.path.join(out_dir, "*.pdb"))
                             if "traj" not in f]) if out_dir else 0
            if new_count > existing:
                log().warning(f"  {target_id}: RFdiffusion 退出码 {r.returncode} "
                              f"但已生成 {new_count} 骨架，继续")
            else:
                from .utils import CommandError
                # _run_streaming 合并了 stderr 到 stdout，错误信息存在 r.stdout
                err = getattr(r, "stdout", None) or ""
                raise CommandError(cmd, r.returncode, err)

        n_final = len([f for f in glob.glob(os.path.join(out_dir, "*.pdb"))
                       if "traj" not in f]) if out_dir else num_designs
        log().info(f"  {target_id}: 完成，共 {n_final} 骨架")
        return {"target_id": target_id, "n_scaffolds": n_final, "out_dir": out_dir}

    def _run_streaming(self, full_cmd, target_id, existing, num_designs,
                       out_dir=None, progress_cb=None):
        """流式执行 RFdiffusion，逐行解析 "Making design" 计数并回调进度。

        相比 subprocess.run（阻塞、无反馈），Popen + 逐行读 stdout 能在
        每个骨架完成时实时推送进度（供 Web 前端 SSE 展示）。

        由于 RFdiffusion 会把大量 INFO 日志打到 stdout，这里用 stderr=STDOUT
        合并输出，并把全部输出累积到 proc.stdout（供错误诊断）。
        """
        proc = subprocess.Popen(
            self._argv(full_cmd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace")

        made = 0  # 已从 stdout 观测到的骨架数
        output_lines = []  # 累积全部输出（供诊断）
        # 匹配 run_inference.py 的 log.info(f"Making design {out_prefix}")
        re_making = re.compile(r"Making design")
        for line in proc.stdout:
            if not line:
                break
            output_lines.append(line)
            if re_making.search(line):
                made += 1
                if progress_cb:
                    progress_cb(target_id, existing + made, num_designs)
        proc.wait()
        # 把累积输出挂到 proc.stdout，供 design() 的错误分支诊断
        proc.stdout = "".join(output_lines)
        return proc
