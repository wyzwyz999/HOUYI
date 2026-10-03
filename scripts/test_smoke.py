"""HOUYI 工程卫生冒烟测试（D4）。

覆盖最近工程卫生改动，作为回归保护：
  - C2: organism 变更检测 + 残留清理
  - C3: 孤儿产物清理
  - B4: DivIVA PDB 字段修复（非法 PDB ID）
  - 各环模块 import 正常

用法：
  python scripts/test_smoke.py
"""
import sys
import os
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from hoyi import Config, run_pipeline  # noqa: E402
from hoyi.utils import (ensure_clean_organism, clear_artifacts,  # noqa: E402
                        _last_organism, _RING_ARTIFACTS)


def test_module_imports():
    """十环模块都能 import。"""
    from hoyi import ring1, ring2, ring3, ring4, ring5, ring6, ring7, ring8, ring9, ring10
    mods = [ring1, ring2, ring3, ring4, ring5, ring6, ring7, ring8, ring9, ring10]
    assert all(hasattr(m, "run") for m in mods), "所有环模块应有 run()"
    print("  ✓ 十环模块 import + run() 存在")


def test_artifact_list_no_orphan():
    """清理列表包含旧孤儿文件 ring7_tail_fibers.json。"""
    assert "ring7_tail_fibers.json" in _RING_ARTIFACTS, "应包含旧孤儿文件"
    assert "ring1_targets.json" in _RING_ARTIFACTS
    assert "nanosyringes.json" in _RING_ARTIFACTS
    print("  ✓ 清理列表覆盖中间产物 + 孤儿文件")


def test_diviva_pdb_valid():
    """B4: DivIVA 的 pdb 字段应是合法 PDB ID（非 '2WUJ (B.subtilis 同源)'）。"""
    cfg = Config()
    kb = json.load(open(cfg.kb_path, encoding="utf-8"))
    diviva = kb["targets"]["F1_DivIVA"]
    pdb = diviva.get("pdb", "")
    assert pdb and "(" not in pdb, f"pdb 字段应为纯 ID，实际: {pdb!r}"
    print(f"  ✓ DivIVA pdb 字段合法: {pdb}")


def test_organism_change_detection():
    """C2: organism 变更检测逻辑（用临时目录，不污染真实 results）。"""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = os.path.join(tmp, "pipeline_state.json")
        # 写入上次 organism = KP
        json.dump({"organism": "Klebsiella pneumoniae"},
                  open(state_path, "w", encoding="utf-8"))
        assert _last_organism(state_path) == "Klebsiella pneumoniae"
        print("  ✓ _last_organism 正确读取上次菌种")

        # 变更检测（dry-run 下不真正清理）
        from hoyi.utils import set_dry_run, is_dry_run
        old = is_dry_run()
        set_dry_run(True)
        # 模拟：结果目录里放一个假产物
        results_dir = os.path.join(tmp, "results")
        os.makedirs(results_dir, exist_ok=True)
        fake = os.path.join(results_dir, "ring1_targets.json")
        open(fake, "w").write("{}")

        class FakeCfg:
            def __init__(self, sp, rd):
                self.state_path = sp
                self.results_dir = rd
        changed, removed = ensure_clean_organism(
            FakeCfg(state_path, results_dir), "Staphylococcus aureus")
        # dry-run 下不清理
        assert changed is False and removed == [], "dry-run 下不应清理"
        set_dry_run(old)
        print("  ✓ dry-run 下 organism 变更不触发真实清理")


def test_clear_artifacts():
    """clear_artifacts 只删中间产物，保留 state 文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 放一个中间产物 + 一个 state 文件
        open(os.path.join(tmp, "ring1_targets.json"), "w").write("{}")
        open(os.path.join(tmp, "pipeline_state.json"), "w").write("{}")
        removed = clear_artifacts(tmp)
        assert "ring1_targets.json" in removed
        assert os.path.exists(os.path.join(tmp, "pipeline_state.json")), "state 文件应保留"
        assert not os.path.exists(os.path.join(tmp, "ring1_targets.json")), "中间产物应删除"
        print("  ✓ clear_artifacts 只删中间产物，保留 state")


def test_auto_discovery_rules():
    """B1: 自动检索的类别优先级 + 每类上限规则存在且合理。"""
    from hoyi.auto_target_discovery import (CATEGORY_PRIORITY, CATEGORY_MAX_PER_TYPE,
                                            CATEGORY_PREFIX, KEYWORD_RULES, EXCLUDE_KEYWORDS)
    # 类别优先级覆盖所有机制类别
    for cat in CATEGORY_PREFIX:
        assert cat in CATEGORY_PRIORITY, f"{cat} 应有优先级"
    # 每类上限存在（耐药类应限制得较严，避免 β-内酰胺酶垄断）
    assert CATEGORY_MAX_PER_TYPE.get("耐药", 99) <= 2, "耐药类应限制 ≤2 个"
    # 转录调控蛋白应被排除（胞内不可及）
    assert "transcriptional regulator" in EXCLUDE_KEYWORDS
    print("  ✓ 自动检索规则（优先级/上限/排除转录因子）存在")


def test_chai1_has_retry():
    """B1: Chai-1 预测应有重试机制（对抗瞬时 CUDA OOM）。"""
    from hoyi.structure_predictor import StructurePredictor
    import inspect
    src = inspect.getsource(StructurePredictor.predict_chai1)
    assert "max_retries" in src, "predict_chai1 应有重试逻辑"
    print("  ✓ Chai-1 预测带重试机制")


def test_backend_abstraction():
    """路线A: 执行后端抽象（wsl/container/native）路径转换 + 命令执行正确。"""
    from hoyi.backend import ExecutionBackend
    # wsl 模式：Windows 盘符路径转 WSL 挂载点
    w = ExecutionBackend("wsl")
    assert w.to_linux(r"H:\a\b.pdb") == "/mnt/h/a/b.pdb"
    assert w._argv("python x.py") == ["wsl", "-e", "bash", "-lc", "python x.py"]
    # container 模式：路径透传 + bash 直连
    c = ExecutionBackend("container")
    assert c.to_linux("/app/data/x.pdb") == "/app/data/x.pdb"
    assert c._argv("python x.py") == ["bash", "-lc", "python x.py"]
    assert "opt/conda" in c.conda_base
    print("  ✓ 执行后端抽象（wsl/container）路径+命令正确")


def main():
    print("=== HOUYI 工程卫生冒烟测试 ===")
    test_module_imports()
    test_artifact_list_no_orphan()
    test_diviva_pdb_valid()
    test_organism_change_detection()
    test_clear_artifacts()
    test_auto_discovery_rules()
    test_chai1_has_retry()
    test_backend_abstraction()
    print("\n✅ 全部通过")


if __name__ == "__main__":
    main()
