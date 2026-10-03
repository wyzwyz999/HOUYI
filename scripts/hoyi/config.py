"""HOUYI (后羿) —— 配置与路径管理模块。

统一管理 Windows/WSL 双端的路径、conda 环境、工具脚本位置，
避免路径散落在各环代码里（旧版 pipeline.py 的硬编码问题）。
"""
import os
from dataclasses import dataclass, field


# ================= PVC13 尾纤维序列（环 9 重编程用） =================
# PVC 尾纤维 pvc13 蛋白：中间受体识别域可被替换，实现靶向重定向。
# 三段式：pvc13_N（保留锚定/组装结构域） + linker + binder + linker + pvc13_C（保留）。
# 参考案例：E01 anti-EGFR DARPin 曾用同法实现宿主细胞 EGFR 重靶向。
PVC13_N = (
    "MNETRYNATVQEQQTLSNPKAVGPDIDKLKDKFKEGSIPLQTDFNELIDIADIGRKACGQAPQQNGPGEG"
    "LKLADDGTLNLKIGTFSNKDFSPLILKDDVLSVDLGSGLTNETNGICVGQGDGITVNTSNVAVKQGNGISV"
    "TSSGGVAVKVSANKGLSVDSSGVAVKVNTDKGISVDGNGVAVKVNTSKGISVDNTGVAVIANASKGISVDG"
    "SGVAVIANTSKGISVDGSGVAVIANTSKGISVDNTGVAVIANASKGISVDGSGVAVIANTSKGISVDGSGV"
    "AVIANTSKGISVDSSGVAVKVKANGGIKVDANGVAIDPNNVLPKGVIVMFSGSTAPTGWALCDGNNGTPNL"
    "IDRFILGGKGTDINGVSTNTASGTKNSKLFDFSSDEATLTIDGKTLGR"
)
PVC13_C = "HDHDIKITGTGKHSHKNKVTVPYYILAFIIKL"
PVC13_LINKER = "GGSGGGGSGG"  # 2xGGSGG 柔性连接子


# 各细菌的数据源映射：organism 关键词 -> (知识库文件, 靶点序列文件, binder 库文件)
# binder 库为 None 表示该菌暂无现成 binder（环2 会如实报告"待真实 RFdiffusion 设计"）
ORGANISM_DATA = {
    "staphylococcus": {
        "kb": "target_knowledge_base.json",
        "antigens": "15_targets_final.json",
        "binders": "binder_library.json",
    },
    "mycobacterium": {
        "kb": "mtb_target_knowledge_base.json",
        "antigens": "mtb_targets_final.json",
        "binders": None,  # 结核杆菌暂无 binder 库
    },
    "acinetobacter": {
        "kb": "ab_target_knowledge_base.json",
        "antigens": "ab_targets_final.json",
        "binders": None,  # 鲍曼不动杆菌暂无 binder 库
    },
    "klebsiella": {
        "kb": "kp_target_knowledge_base.json",
        "antigens": "kp_targets_final.json",
        "binders": None,  # 肺炎克雷伯菌暂无 binder 库
    },
}


def _match_organism(organism: str):
    """根据细菌名匹配数据源（大小写不敏感、子串匹配）。"""
    o = (organism or "").lower()
    for key, val in ORGANISM_DATA.items():
        if key in o:
            return val
    return None


@dataclass
class Config:
    """HOUYI 平台全局配置。

    通过环境变量可覆盖，便于不同机器/部署环境复用。
    默认针对当前开发机（Windows + WSL2，H 盘挂载到 /mnt/h）。
    容器化后设 HOUYI_RUN_MODE=container + HOUYI_BASE_WIN/HOUYI_BASE_WSL 指向容器内路径，
    代码零改动即可迁移。
    """

    # ---- 根路径（Windows 视角） ----
    base_win: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_BASE_WIN", r"H:\eazyclaw\saved\MASA3"))

    # ---- 根路径（WSL 视角） ----
    base_wsl: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_BASE_WSL", "/mnt/h/eazyclaw/saved/MASA3"))

    # ---- 当前细菌数据源（可动态切换） ----
    _organism: str = field(default="", repr=False)
    _data_source: dict = field(default=None, repr=False)

    # ---- WSL 工具/conda 环境 ----
    wsl_conda_base: str = "~/miniforge3/etc/profile.d/conda.sh"
    env_rf: str = "protein_design"
    env_mpnn: str = "protein_design"
    env_esm: str = "protein_design"

    # RFdiffusion / ProteinMPNN 安装路径（容器内可用环境变量覆盖）
    rfd_script: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_RFDIFFUSION", "/home/zhaoxx/RFdiffusion/scripts/run_inference.py"))
    rfd_root: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_RFDIFFUSION_ROOT", "/home/zhaoxx/RFdiffusion"))
    mpnn_script: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_MPNN", "/home/zhaoxx/ProteinMPNN/protein_mpnn_run.py"))
    mpnn_root: str = field(default_factory=lambda: os.environ.get(
        "HOUYI_MPNN_ROOT", "/home/zhaoxx/ProteinMPNN"))

    # ---- 数据/结果子目录 ----
    @property
    def data_dir(self):
        return os.path.join(self.base_win, "data")

    @property
    def results_dir(self):
        return os.path.join(self.base_win, "results")

    def set_organism(self, organism: str):
        """根据细菌名切换数据源。未匹配到已知菌种时保持默认（金葡菌）。"""
        self._organism = organism or ""
        self._data_source = _match_organism(self._organism)

    @property
    def data_source(self):
        return self._data_source or ORGANISM_DATA["staphylococcus"]

    @property
    def kb_path(self):
        return os.path.join(self.data_dir, "antigens", self.data_source["kb"])

    @property
    def antigens_path(self):
        return os.path.join(self.data_dir, "antigens", self.data_source["antigens"])

    @property
    def binder_lib_path(self):
        b = self.data_source["binders"]
        if b is None:
            return None
        return os.path.join(self.data_dir, "binders", b)

    @property
    def state_path(self):
        return os.path.join(self.results_dir, "pipeline_state.json")

    # ---- 尾纤维靶点知识库（环 7 靶向重定向） ----
    @property
    def fiber_kb_path(self):
        return os.path.join(self.data_dir, "antigens", "fiber_target_knowledge_base.json")

    # ---- 各环中间产物路径（环编号 1-6） ----
    @property
    def ring1_out(self):
        return os.path.join(self.results_dir, "ring1_targets.json")

    @property
    def ring2_out(self):
        return os.path.join(self.results_dir, "ring2_structure.json")

    @property
    def ring3_out(self):
        return os.path.join(self.results_dir, "ring3_designed.json")

    @property
    def ring4_out(self):
        return os.path.join(self.results_dir, "ring4_scored.json")

    @property
    def ring5_fasta(self):
        return os.path.join(self.results_dir, "top_binders.fasta")

    @property
    def ring5_json(self):
        return os.path.join(self.results_dir, "top_binders.json")

    @property
    def ring6_fasta(self):
        return os.path.join(self.results_dir, "payloads.fasta")

    @property
    def ring6_json(self):
        return os.path.join(self.results_dir, "payloads.json")

    @property
    def ring7_out(self):
        return os.path.join(self.results_dir, "ring7_fiber_targets.json")

    @property
    def ring8_out(self):
        return os.path.join(self.results_dir, "ring8_fiber_binders.json")

    @property
    def ring9_out(self):
        return os.path.join(self.results_dir, "ring9_reprogrammed_fibers.json")

    @property
    def ring9_fasta(self):
        return os.path.join(self.results_dir, "reprogrammed_fibers.fasta")

    @property
    def ring10_json(self):
        return os.path.join(self.results_dir, "nanosyringes.json")

    @property
    def ring10_fasta(self):
        return os.path.join(self.results_dir, "nanosyringes.fasta")

    def ensure_dirs(self):
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
