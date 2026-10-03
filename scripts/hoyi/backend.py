"""HOUYI (后羿) —— 执行后端抽象层（容器化改造核心）。

把「命令执行」和「路径转换」从各环代码里抽象出来，统一支持三种运行模式：

  - wsl       : 当前开发机（Windows + WSL2），命令经 `wsl -e bash -lc` 执行，
                Windows 路径需转换成 WSL 视角（H: -> /mnt/h）。
  - container : Docker 容器内（纯 Linux），直接 subprocess 执行，
                路径透传（无 Windows↔WSL 转换）。
  - native    : 本机 Linux 直接执行（无容器、无 WSL）。

这样环 2/3/4 等重计算模块不再到处写 `wsl -e` 和 `replace("H:", "/mnt/h")`，
换部署环境只需改 RUN_MODE（环境变量 HOUYI_RUN_MODE），代码零改动。

用法：
    from .backend import backend
    backend.run("python scripts/run_inference.py ...")   # 执行命令
    wsl_path = backend.to_linux("H:\\\\foo\\\\bar.pdb")     # Windows -> 目标视角路径
"""
import os
import subprocess


class ExecutionBackend:
    """命令执行 + 路径转换后端。"""

    def __init__(self, mode=None):
        # 运行模式：wsl / container / native（默认 wsl，兼容旧行为）
        self.mode = (mode or os.environ.get("HOUYI_RUN_MODE", "wsl")).lower()

    # ---- GPU 检测 ----------------
    def has_gpu(self) -> bool:
        """检测执行端是否有可用 GPU（容器/WSL 内看 nvidia-smi / torch）。

        返回 True 表示有 CUDA GPU；False 表示 CPU-only（需降级）。
        结果缓存，避免重复调用。
        """
        if hasattr(self, "_has_gpu_cache"):
            return self._has_gpu_cache
        val = self._detect_gpu()
        self._has_gpu_cache = val
        return val

    def _detect_gpu(self) -> bool:
        # 优先看 nvidia-smi（最直接）
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return True
        except Exception:
            pass
        # 容器内可能 nvidia-smi 不在 PATH，退回 torch 检测
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    # ---- 路径转换 ----
    def to_linux(self, path):
        """把 Windows 视角路径转成执行端（WSL/容器/native）能读的路径。

        - wsl 模式：H:\\a\\b -> /mnt/h/a/b（WSL 挂载点）
        - container/native：透传（已经是 Linux 路径）
        """
        if not path:
            return path
        if self.mode == "wsl":
            # 仅当路径看起来是 Windows 盘符路径时才转换
            p = str(path).replace("\\", "/")
            if len(p) >= 2 and p[1] == ":":
                drive = p[0].lower()
                p = f"/mnt/{drive}" + p[2:]
            return p
        return str(path)

    def to_win(self, path):
        """把执行端路径转回 Windows 视角（仅 wsl 模式需要，反向）。"""
        if not path:
            return path
        if self.mode == "wsl":
            p = str(path)
            # /mnt/h/xxx -> H:/xxx
            if p.startswith("/mnt/"):
                drive = p[5].upper()
                return f"{drive}:" + p[6:].replace("/", "\\")
        return str(path)

    # ---- 命令执行 ----
    def run(self, cmd, env_name=None, cwd=None, timeout=None,
            capture=True, text=True, check=False, streaming=False):
        """执行命令，返回 subprocess 结果（或 Popen 若 streaming）。

        Args:
            cmd: 要执行的 shell 命令
            env_name: conda 环境名（wsl 模式会 source conda.sh + activate）
            cwd: 工作目录
            timeout: 超时（秒）
            capture: 是否捕获输出
            check: 失败是否抛异常
            streaming: 是否流式（返回 Popen）
        """
        full = self._wrap(cmd, env_name)
        if streaming:
            proc = subprocess.Popen(
                self._argv(full), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace")
            return proc
        r = subprocess.run(self._argv(full), capture_output=capture,
                           text=text, cwd=cwd, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r

    def _argv(self, full_cmd):
        """把完整命令转成 subprocess 的 argv 列表。

        wsl 模式：["wsl", "-e", "bash", "-lc", full_cmd]
        container/native：["bash", "-lc", full_cmd]
        """
        if self.mode == "wsl":
            return ["wsl", "-e", "bash", "-lc", full_cmd]
        return ["bash", "-lc", full_cmd]

    def _wrap(self, cmd, env_name):
        """包裹命令：conda 激活（如指定）+ 原命令。"""
        if not env_name:
            return cmd
        if self.mode == "wsl":
            conda_base = os.environ.get(
                "HOUYI_CONDA_BASE", "~/miniforge3/etc/profile.d/conda.sh")
            return f"source {conda_base} && conda activate {env_name} && {cmd}"
        # container/native：conda 已激活或直接在 PATH
        conda_base = os.environ.get(
            "HOUYI_CONDA_BASE", "/opt/conda/etc/profile.d/conda.sh")
        return f"source {conda_base} && conda activate {env_name} && {cmd}"

    # ---- conda 环境相关 ----
    @property
    def conda_base(self):
        if self.mode == "wsl":
            return os.environ.get("HOUYI_CONDA_BASE", "~/miniforge3/etc/profile.d/conda.sh")
        return os.environ.get("HOUYI_CONDA_BASE", "/opt/conda/etc/profile.d/conda.sh")


# 全局单例（默认按 HOUYI_RUN_MODE 环境变量）
backend = ExecutionBackend()
