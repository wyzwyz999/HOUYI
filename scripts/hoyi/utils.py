"""HOUYI (后羿) —— 工具模块：日志、WSL 执行、状态管理。

统一结构化日志、WSL 命令执行（带失败处理）、状态文件的读写，
解决旧版 pipeline.py 的「无异常处理、命令失败不中断、假断点续跑」三大问题。
"""
import os
import json
import time
import subprocess
import logging
from typing import Optional, Dict, Any

# ============ 结构化日志 ============
_logger = None


def get_logger(verbose: bool = False) -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("hoyi")
        _logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        if not _logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
            _logger.addHandler(h)
    return _logger


log = get_logger


# ============ WSL 命令执行 ============
class CommandError(RuntimeError):
    """WSL 命令执行失败异常，携带 returncode 和 stderr。"""

    def __init__(self, cmd: str, returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"命令失败 (exit {returncode}): {cmd}\n{stderr[-800:]}")


def run_wsl(cmd: str, env_name: Optional[str] = None,
            cwd: Optional[str] = None, dry_run: bool = False,
            timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """执行命令（后端无关：WSL / 容器 / 本机，由 HOUYI_RUN_MODE 决定）。

    Args:
        cmd: 要执行的 shell 命令
        env_name: conda 环境名（可选）
        cwd: 工作目录
        dry_run: 仅打印不执行
        timeout: 超时（秒）

    Raises:
        CommandError: 命令失败时抛出（不再静默吞掉）
    """
    from .backend import backend
    if env_name:
        conda_base = backend.conda_base
        full_cmd = f"source {conda_base} && conda activate {env_name} && " + cmd
    else:
        full_cmd = cmd

    log().info(f"  RUN: {full_cmd[:120]}")
    if dry_run:
        return subprocess.CompletedProcess(full_cmd, 0, "", "(dry-run)")

    r = backend.run(full_cmd, cwd=cwd, timeout=timeout)

    if r.returncode != 0:
        raise CommandError(full_cmd, r.returncode, r.stderr)
    return r


# ============ 状态文件管理 ============
class State:
    """管线状态管理：完整记录每环产物，支持真正的断点续跑。

    旧版只在 state 里存 rings 摘要，中间产物丢失，导致跳过环读不到结果。
    新版把每环的完整产物都落盘到独立 JSON，state 只存元信息 + 产物指针。
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        p = self.cfg.state_path
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log().warning(f"状态文件损坏，重建: {e}")
        return {"organism": None, "rings": {}, "artifacts": {}}

    def save(self):
        if is_dry_run():
            return
        os.makedirs(self.cfg.results_dir, exist_ok=True)
        json.dump(self.data, open(self.cfg.state_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    def mark_ring(self, ring: int, status: str, info: str = ""):
        self.data["rings"][str(ring)] = {
            "status": status,  # DONE / SKIPPED / ERROR / PENDING
            "info": info,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()

    def set_artifact(self, ring: int, key: str, value: Any):
        """记录某环的产物（内存指针，实际数据已落盘到独立 JSON）。"""
        self.data.setdefault("artifacts", {}).setdefault(str(ring), {})[key] = value
        self.save()

    def get_artifact(self, ring: int, key: str, default=None):
        return self.data.get("artifacts", {}).get(str(ring), {}).get(key, default)

    def ring_status(self, ring: int) -> Optional[str]:
        return self.data.get("rings", {}).get(str(ring), {}).get("status")


# ============ 全局 dry-run 开关 ============
_DRY_RUN = False


def set_dry_run(flag: bool):
    """设置全局 dry-run 开关（save_json / State.save 将变 no-op）。"""
    global _DRY_RUN
    _DRY_RUN = flag


def is_dry_run() -> bool:
    return _DRY_RUN


# ============ 进度事件总线 ============
# 让 Web 后端能订阅 pipeline 每环的执行事件，实时推送给前端。
# 解耦设计：各环业务逻辑不感知，只在 run_pipeline 编排层发布事件。
_event_listeners = []


def on_event(callback):
    """注册事件监听器。callback(event: dict)。"""
    _event_listeners.append(callback)


def emit_event(event: Dict[str, Any]):
    """发布事件给所有监听器。事件字段：{ring, status, message, time}。"""
    event = dict(event)
    event.setdefault("time", time.strftime("%H:%M:%S"))
    for cb in list(_event_listeners):
        try:
            cb(event)
        except Exception:
            pass  # 监听器异常不阻断管线


# ============ JSON 安全读写 ============
def load_json(path: str, default=None):
    """安全读取 JSON，失败返回 default 并告警（不崩溃）。"""
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path, encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log().warning(f"读取 JSON 失败 {path}: {e}")
        return default


def save_json(path: str, data: Any):
    if _DRY_RUN:
        log().info(f"  [dry-run] 跳过写盘: {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ============ 产物隔离与残留清理 ============
# 中间产物（ringN_*.json / *.fasta）不分菌种隔离，切换菌种重跑会残留上一菌种的数据，
# 导致「环跳过时读到错误靶点」的坑（如 KP 残留污染金葡菌）。
# 这里提供：检测 organism 变更 + 清理旧中间产物的能力。

_RING_ARTIFACTS = [
    "ring1_targets.json", "ring2_structure.json", "ring3_designed.json",
    "ring4_scored.json", "top_binders.json", "top_binders.fasta",
    "payloads.json", "payloads.fasta",
    "ring7_fiber_targets.json", "ring8_fiber_binders.json",
    "ring9_reprogrammed_fibers.json", "reprogrammed_fibers.fasta",
    "nanosyringes.json", "nanosyringes.fasta",
    "ring7_tail_fibers.json",  # 旧版环7 孤儿产物（已废弃）
]


def _last_organism(state_path: str):
    """读取上次运行的 organism（无 state 则返回 None）。"""
    if not os.path.exists(state_path):
        return None
    try:
        d = json.load(open(state_path, encoding="utf-8"))
        return d.get("organism")
    except (json.JSONDecodeError, OSError):
        return None


def clear_artifacts(results_dir: str):
    """删除所有中间产物（不含 state 文件本身）。"""
    removed = []
    for name in _RING_ARTIFACTS:
        p = os.path.join(results_dir, name)
        if os.path.exists(p):
            try:
                os.remove(p)
                removed.append(name)
            except OSError as e:
                log().warning(f"  清理失败 {name}: {e}")
    return removed


def ensure_clean_organism(cfg, organism: str):
    """检测 organism 变更，若与上次不同则清理旧中间产物，避免跨菌种残留。

    返回 (changed: bool, removed: list)。只在非 dry-run 下真正清理。
    """
    if is_dry_run():
        return False, []
    last = _last_organism(cfg.state_path)
    if last is not None and last != organism:
        log().info(f"  检测到 organism 变更: {last} -> {organism}，清理旧中间产物")
        removed = clear_artifacts(cfg.results_dir)
        if removed:
            log().info(f"  已清理 {len(removed)} 个旧产物: {', '.join(removed)}")
        return True, removed
    return False, []
