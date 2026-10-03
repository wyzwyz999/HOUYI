#!/usr/bin/env python3
"""
HOUYI (后羿) —— 为结核分枝杆菌 (Mycobacterium tuberculosis) 建立靶点知识库 + 序列文件。

这是验证后羿「细菌名 → 端到端泛化能力」的关键前置步骤：
金葡菌的靶点库不能用于结核杆菌，必须为新菌建全新靶点库。

输入：data/antigens/fetched_sequences.json（11 个 reviewed 靶点序列）
输出：
  1. data/antigens/mtb_target_knowledge_base.json   —— 环0 靶点知识库（organism=Mycobacterium tuberculosis）
  2. data/antigens/mtb_targets_final.json           —— 靶点全长序列（对齐 15_targets_final.json 格式）
"""
import json, os

BASE = r"H:\eazyclaw\saved\MASA3"
FETCHED = os.path.join(BASE, "data", "antigens", "fetched_sequences.json")
KB_OUT = os.path.join(BASE, "data", "antigens", "mtb_target_knowledge_base.json")
SEQ_OUT = os.path.join(BASE, "data", "antigens", "mtb_targets_final.json")

# 靶点定义：ID -> (gene, 蛋白名, 机制分类, PDB, 设计策略, 靶点论据)
# 靶点 ID 命名沿用金葡菌的「类别前缀 + 靶点名」约定，便于统一处理
TARGETS = {
    # ---- 胞内必需酶（分枝菌酸合成 FAS-II 通路，一线/新型药物靶点）----
    "MTB_KasA": {
        "gene": "kasA",
        "protein": "3-oxoacyl-[acyl-carrier-protein] synthase 1 (KasA)",
        "mechanism_class": "细胞壁合成（分枝菌酸 FAS-II 延长酶）",
        "pdb": "4C70",
        "function": "FAS-II 途径核心缩合酶，催化分枝菌酸碳链延长（Claisen 缩合），催化三联体 Cys171/His311/His345",
        "rationale": {
            "surface_exposed": False,
            "virulence_relevance": "kasA 是结核杆菌体外生长必需基因（TnSeq 多组独立验证），分枝菌酸是细胞壁结构/毒力/固有耐药的关键",
            "conservation": "催化三联体高度保守，无哺乳动物同源（FAS-II 细菌特有）",
            "host_homology": "无（哺乳动物用 FAS-I）",
            "clinical_evidence": "DG167/JSF-3285 等 KasA 抑制剂已验证，与异烟肼协同致死，正在结构导向优化"
        },
        "design_strategy": "靶向底物通道/酰基酶中间态（acyl-enzyme mimic），阻断 Cys171 酰化",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_InhA": {
        "gene": "inhA",
        "protein": "Enoyl-[acyl-carrier-protein] reductase [NADH] (InhA)",
        "mechanism_class": "细胞壁合成（分枝菌酸 FAS-II 还原酶，一线药靶点）",
        "pdb": "1BVR",
        "function": "NADH 依赖的烯酰-ACP 还原酶，还原反式双键，是异烟肼(INH)的作用靶点",
        "rationale": {
            "surface_exposed": False,
            "virulence_relevance": "一线药 INH 的直接靶点，抑制则分枝菌酸合成中断、细胞壁崩解",
            "conservation": "活性位点保守",
            "host_homology": "无",
            "clinical_evidence": "INH 自 1952 年即一线用药；直接 InhA 抑制剂(GSK693 等)可绕过 KatG 耐药，多进入临床前/临床"
        },
        "design_strategy": "靶向 NADH 结合口袋/底物结合位点（direct inhibitor，绕过 KatG 激活耐药）",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_MmpL3": {
        "gene": "mmpL3",
        "protein": "Trehalose monomycolate exporter MmpL3",
        "mechanism_class": "细胞壁合成（海藻糖单霉菌酸转运体）",
        "pdb": "7NVH",
        "function": "跨膜转运海藻糖单霉菌酸(TMM)，外膜霉菌酸层组装必需，质子驱动转运",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "必需膜蛋白，抑制则细胞壁外膜组装失败、细菌死亡",
            "conservation": "跨膜质子转运 Asp-Tyr 对保守",
            "host_homology": "无",
            "clinical_evidence": "SQ109(已完成 Phase2b-3)等大量化学骨架经全细胞筛选命中 MmpL3，是目前最热的抗结核新靶点之一"
        },
        "design_strategy": "靶向 TMM 结合腔/质子传递网络（Asp256-Tyr646, Asp645-Tyr257），阻断转运",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_Pks13": {
        "gene": "pks13",
        "protein": "Polyketide synthase Pks13",
        "mechanism_class": "细胞壁合成（分枝菌酸前体聚酮合酶）",
        "pdb": None,
        "function": "催化 FAS-I 与 FAS-II 产物克莱森缩合，生成分枝菌酸前体（α-烷基-β-酮酸）",
        "rationale": {
            "surface_exposed": False,
            "virulence_relevance": "分枝菌酸合成必需末端步骤，必需基因",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "新药 TBAJ-876/Bedaquiline 等联合方案关注点；Pks13 抑制剂(如 TAM16)抗结核活性强"
        },
        "design_strategy": "靶向缩合酶结构域（ketosynthase/AT 域）",
        "wetlab_status": "待设计（新靶点）"
    },
    # ---- 表面暴露抗原（疫苗/诊断/免疫靶点）----
    "MTB_Ag85A": {
        "gene": "fbpA",
        "protein": "Diacylglycerol acyltransferase/mycolyltransferase Ag85A (FbpA)",
        "mechanism_class": "表面抗原（分枝菌酰转移酶复合物 Ag85 亚基 A）",
        "pdb": "1SFR",
        "function": "Ag85 复合物亚基，催化海藻糖二霉菌酸(TDM)合成，主要分泌蛋白/细胞壁锚定",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "细胞壁合成 + 免疫显性抗原，Ag85 是结核疫苗核心组分",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "MVA85A、H56:IC31 等疫苗含 Ag85A；诊断广泛使用"
        },
        "design_strategy": "靶向酶活性位点/纤维连接蛋白结合域（阻断 TDM 合成）",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_Ag85B": {
        "gene": "fbpB",
        "protein": "Diacylglycerol acyltransferase/mycolyltransferase Ag85B (FbpB)",
        "mechanism_class": "表面抗原（Ag85 亚基 B，疫苗金标准抗原）",
        "pdb": "1F0P",
        "function": "Ag85 复合物主要亚基，最强免疫原性抗原之一，催化霉菌酸转移",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "免疫显性，Ag85B 是几乎所有亚单位结核疫苗的核心抗原",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "H4:IC31、M72/AS01E(Phase2b 54%保护效力)、GamTBvac 等疫苗均含 Ag85B"
        },
        "design_strategy": "靶向酶活性位点/免疫表位，中和其毒力功能",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_Ag85C": {
        "gene": "fbpC",
        "protein": "Diacylglycerol acyltransferase/mycolyltransferase Ag85C (FbpC)",
        "mechanism_class": "表面抗原（Ag85 亚基 C）",
        "pdb": "1DQY",
        "function": "Ag85 复合物第三亚基，锚定于细胞壁，参与 TDM 合成",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "细胞壁组装 + 抗原性",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "诊断/疫苗候选组分"
        },
        "design_strategy": "靶向酶活性位点",
        "wetlab_status": "待设计（新靶点）"
    },
    # ---- 毒力分泌系统效应蛋白（ESX-1）----
    "MTB_ESAT6": {
        "gene": "esxA",
        "protein": "6 kDa early secretory antigenic target (ESAT-6, EsxA)",
        "mechanism_class": "毒力（ESX-1 分泌系统效应蛋白）",
        "pdb": "3FAV",
        "function": "ESX-1 VII 型分泌系统分泌的毒力效应蛋白，与 CFP-10 形成异二聚体，破坏吞噬体膜、介导胞内逃逸",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "ESX-1 是结核杆菌毒力必需系统，ESAT-6 缺失株毒力显著下降（RD1 区），疫苗株 BCG 正因缺失 RD1 而减毒",
            "conservation": "高度保守",
            "host_homology": "无",
            "clinical_evidence": "IGRA 诊断(QuantiFERON)金标准抗原，免疫原性极强"
        },
        "design_strategy": "阻断 ESAT-6/CFP-10 异二聚化或膜裂解结构域（毒力中和）",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_CFP10": {
        "gene": "esxB",
        "protein": "ESAT-6-like protein EsxB (CFP-10)",
        "mechanism_class": "毒力（ESX-1 分泌系统效应蛋白）",
        "pdb": "3FAV",
        "function": "ESAT-6 的伴侣蛋白，形成 1:1 异二聚体，协同介导吞噬体膜穿孔",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "ESX-1 毒力关键，与 ESAT-6 协同破坏宿主膜",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "IGRA 诊断核心抗原"
        },
        "design_strategy": "阻断异二聚化界面（毒力中和）",
        "wetlab_status": "待设计（新靶点）"
    },
    # ---- 诊断/分泌蛋白（可作为表面抗原靶点）----
    "MTB_MPT64": {
        "gene": "mpt64",
        "protein": "Immunogenic protein MPT64",
        "mechanism_class": "分泌蛋白（诊断标志/抗原）",
        "pdb": None,
        "function": "结核杆菌复合群特异性分泌蛋白，广泛用于抗原检测诊断",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "结核复合群特异，潜在毒力/免疫调节",
            "conservation": "结核复合群保守（可区分 BCG）",
            "host_homology": "无",
            "clinical_evidence": "MPT64 抗原检测是全球广泛使用的结核快速诊断标志"
        },
        "design_strategy": "高亲和识别（诊断/治疗双用途）",
        "wetlab_status": "待设计（新靶点）"
    },
    "MTB_LpqH": {
        "gene": "lpqH",
        "protein": "Lipoprotein LpqH (19 kDa lipoprotein antigen)",
        "mechanism_class": "表面抗原（脂蛋白，TLR2 配体）",
        "pdb": None,
        "function": "细胞壁锚定脂蛋白，激活 TLR2，诱导宿主免疫调节",
        "rationale": {
            "surface_exposed": True,
            "virulence_relevance": "免疫调节脂蛋白，影响宿主免疫应答",
            "conservation": "保守",
            "host_homology": "无",
            "clinical_evidence": "诊断抗原，广泛研究"
        },
        "design_strategy": "阻断 TLR2 结合/免疫调节功能",
        "wetlab_status": "待设计（新靶点）"
    },
}

# accession -> gene 映射（从 fetched 结果）
GENE_TO_ACC = {
    "kasA": "P9WQD9", "inhA": "P9WGR1", "mmpL3": "P9WJV5", "pks13": "I6X8D2",
    "fbpA": "P9WQP3", "fbpB": "P9WQP1", "fbpC": "P9WQN9",
    "esxA": "P9WNK7", "esxB": "P9WNK5", "mpt64": "P9WIN9", "lpqH": "P9WK61",
}

def main():
    fetched = json.load(open(FETCHED, encoding="utf-8"))

    # 1. 靶点序列文件（对齐 15_targets_final.json）
    seq_out = {}
    for tid, meta in TARGETS.items():
        acc = GENE_TO_ACC[meta["gene"]]
        f = fetched[acc]
        seq_out[tid] = {
            "uniprot_accession": acc,
            "gene": meta["gene"],
            "title": meta["protein"] + f" [Mycobacterium tuberculosis]",
            "query": f"Mycobacterium tuberculosis {meta['gene']} {meta['protein']}",
            "length": f["length"],
            "sequence": f["sequence"],
        }

    # 2. 知识库
    kb = {
        "organism": "Mycobacterium tuberculosis",
        "organism_note": "抗酸杆菌（放线菌门），WHO 头号传染病杀手，专性胞内寄生，细胞壁富含分枝菌酸、对抗生素高度固有耐药，MDR/XDR-TB 是重大耐药威胁",
        "target_selection_principles": [
            "表面暴露性（可被 binder 触及）",
            "毒力/耐药相关性（打击病原体关键功能）",
            "保守性（降低逃逸突变风险）",
            "与宿主无同源性（降低脱靶毒性）",
            "临床/疫苗已验证的免疫原性（降低翻译风险）",
        ],
        "targets": {},
    }
    for tid, meta in TARGETS.items():
        acc = GENE_TO_ACC[meta["gene"]]
        f = fetched[acc]
        kb["targets"][tid] = {
            "gene": meta["gene"],
            "protein": meta["protein"],
            "mechanism_class": meta["mechanism_class"],
            "length_aa": f["length"],
            "uniprot": acc,
            "function": meta["function"],
            "pdb": meta["pdb"],
            "rationale": meta["rationale"],
            "design_strategy": meta["design_strategy"],
            "wetlab_status": meta["wetlab_status"],
        }

    os.makedirs(os.path.dirname(KB_OUT), exist_ok=True)
    with open(KB_OUT, "w", encoding="utf-8") as fp:
        json.dump(kb, fp, ensure_ascii=False, indent=2)
    with open(SEQ_OUT, "w", encoding="utf-8") as fp:
        json.dump(seq_out, fp, ensure_ascii=False, indent=2)

    print(f"=== 结核杆菌靶点知识库完成 ===")
    print(f"靶点数: {len(TARGETS)}")
    for tid in TARGETS:
        print(f"  {tid}: {TARGETS[tid]['protein']} ({TARGETS[tid]['mechanism_class']})")
    print(f"\n知识库: {KB_OUT}")
    print(f"序列:   {SEQ_OUT}")

if __name__ == "__main__":
    main()
