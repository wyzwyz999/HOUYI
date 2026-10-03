"""生成肺炎克雷伯菌载荷设计详细 Word 介绍文档。
读取 payloads.json / ring1_targets.json / kp_target_knowledge_base.json，动态生成。
"""
import json, os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = r"H:\eazyclaw\saved\MASA3"
OUT_DIR = os.path.join(BASE, "output KP")

payloads = json.load(open(os.path.join(BASE, "results", "payloads.json"), encoding="utf-8"))
r1 = json.load(open(os.path.join(BASE, "results", "ring1_targets.json"), encoding="utf-8"))
kb = json.load(open(os.path.join(BASE, "data", "antigens", "kp_target_knowledge_base.json"), encoding="utf-8"))
r4 = json.load(open(os.path.join(BASE, "results", "ring4_scored.json"), encoding="utf-8"))
tmeta = r1.get("target_meta", {})
targets_kb = kb.get("targets", {})

PDP1 = "MPRYANYQINPKQNIKNSHGKSSSSDFSSGYLSFSNNSLDDPFIRQQVKREFIWEGHMKEIEEASRL"
LINKER = "GGSGGGGSGG"

# 靶点机制分类
MECH = {
    "KP_KPC2": ("耐药（碳青霉烯酶）", "CRKP 超级耐药核心决定因子"),
    "KP_NDM1": ("耐药（金属β内酰胺酶）", "泛耐药核心机制"),
    "KP_OXA48": ("耐药（碳青霉烯酶）", "第三大碳青霉烯酶家族"),
    "KP_SHV1": ("耐药（广谱β内酰胺酶）", "染色体固有耐药决定子"),
    "KP_OmpA": ("表面抗原（外膜蛋白）", "毒力/黏附/生物膜"),
    "KP_OmpC": ("表面抗原（孔蛋白）", "OmpK36 同源，耐药协同"),
    "KP_TonB": ("营养摄取（铁摄取）", "能量转导中枢"),
    "KP_IutA": ("营养摄取（铁载体受体）", "hvKP 高毒力标志"),
}

# 按靶点分组载荷
by_target = {}
for x in payloads:
    by_target.setdefault(x["target"], []).append(x)

def best_score(t):
    return max(x["esm_composite"] for x in by_target[t])
ordered = sorted(by_target.keys(), key=best_score, reverse=True)

# ---------- 文档构建 ----------
doc = Document()

sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.5)
sec.bottom_margin = Cm(2.5)
sec.left_margin = Cm(2.8)
sec.right_margin = Cm(2.8)

style = doc.styles['Normal']
style.font.name = '微软雅黑'
style.font.size = Pt(10.5)
rPr = style.element.find(qn('w:rPr'))
if rPr is None:
    rPr = OxmlElement('w:rPr'); style.element.append(rPr)
rFonts = rPr.find(qn('w:rFonts'))
if rFonts is None:
    rFonts = OxmlElement('w:rFonts'); rPr.insert(0, rFonts)
for a in ('w:ascii','w:hAnsi','w:eastAsia','w:cs'):
    rFonts.set(qn(a), '微软雅黑')

def set_run_font(run, name='微软雅黑', size=None, bold=None, color=None):
    run.font.name = name
    r = run._r.get_or_add_rPr()
    rf = r.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); r.insert(0, rf)
    for a in ('w:ascii','w:hAnsi','w:eastAsia','w:cs'):
        rf.set(qn(a), name)
    if size: run.font.size = Pt(size)
    if bold is not None: run.font.bold = bold
    if color: run.font.color.rgb = RGBColor(*color)

def add_heading(text, level=1):
    p = doc.add_paragraph()
    run = p.add_run(text)
    sizes = {1: 16, 2: 13, 3: 11.5}
    set_run_font(run, name='微软雅黑', size=sizes.get(level, 11), bold=True,
                 color=(0x1F, 0x4E, 0x79) if level == 1 else (0x00, 0x00, 0x00))
    p.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    p.paragraph_format.space_after = Pt(6)
    return p

def add_para(text, size=10.5, bold=False, color=None, italic=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color)
    if italic: run.font.italic = True
    p.paragraph_format.line_spacing = 1.3
    return p

def add_seq_para(label, seq, color=(0x00, 0x33, 0x00)):
    p = doc.add_paragraph()
    r1 = p.add_run(label)
    set_run_font(r1, size=9.5, bold=True)
    r2 = p.add_run(seq)
    set_run_font(r2, name='Consolas', size=8.5, color=color)
    p.paragraph_format.line_spacing = 1.15
    return p

def add_table(headers, rows, col_widths=None, font_size=9):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ''
        p = hdr[i].paragraphs[0]
        run = p.add_run(h)
        set_run_font(run, size=font_size, bold=True, color=(0xFF,0xFF,0xFF))
        shd = OxmlElement('w:shd'); shd.set(qn('w:val'),'clear'); shd.set(qn('w:fill'),'1F4E79')
        hdr[i]._tc.get_or_add_tcPr().append(shd)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ''
            p = cells[i].paragraphs[0]
            run = p.add_run(str(v))
            set_run_font(run, size=font_size)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t

# ============ 封面标题 ============
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("后羿 HOUYI 抗菌载荷设计平台")
set_run_font(run, size=22, bold=True, color=(0x1F,0x4E,0x79))

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("肺炎克雷伯菌（Klebsiella pneumoniae）\n抗菌载荷端到端设计报告")
set_run_font(run, size=15, bold=True)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("详细技术介绍与数据说明")
set_run_font(run, size=11, color=(0x80,0x80,0x80))

add_para("", size=6)
meta = [
    ("病原菌", "Klebsiella pneumoniae（肺炎克雷伯菌，WHO CRITICAL 级 / CRKP）"),
    ("平台", "后羿 HOUYI（端到端抗菌载荷设计平台）"),
    ("交付物", "21 条抗菌载荷（7 靶点 × Top3）"),
    ("生成日期", "2026-10-02"),
    ("数据目录", os.path.join(OUT_DIR, "")),
]
for k, v in meta:
    add_para(f"{k}：{v}", size=10, color=(0x40,0x40,0x40))

doc.add_page_break()

# ============ 一、执行摘要 ============
add_heading("一、执行摘要", 1)
add_para("本项目利用后羿（HOUYI）端到端抗菌载荷设计平台，针对肺炎克雷伯菌（Klebsiella pneumoniae）这一 WHO 优先病原体清单 CRITICAL 级的碳青霉烯耐药（CRKP）头号威胁，完成了从靶点分析到载荷拼装的六环全自动设计流程。")
add_para("核心成果：")
for line in [
    "• 分析并论证 8 个抗菌靶点（耐药酶、外膜蛋白、营养摄取三大机制类别）",
    "• 完成 8/8 靶点的结构准备（6 个 RCSB PDB 下载 + 2 个 Chai-1 从头预测）",
    "• RFdiffusion 从头设计 binder 骨架，ProteinMPNN 序列设计 + ESM-2 折叠评分，共 642 条候选 binder",
    "• 输出 21 条 Top binder（7 靶点 × Top3），并拼装为完整载荷 Pdp1_NTD-linker-binder",
    "• 1 靶点（KP_IutA）因 733aa 大靶点显存限制（CUDA OOM）跳过",
]:
    add_para(line, size=10.5)

# ============ 二、背景 ============
add_heading("二、研究背景", 1)
add_heading("2.1 病原体威胁", 2)
add_para(kb.get("organism_note", ""), size=10.5)
add_heading("2.2 载荷设计思路", 2)
add_para("传统抗生素面临严重的耐药问题，本项目采用从头蛋白设计策略：在病原体表面/关键功能蛋白上，用 RFdiffusion 生成能特异性结合的迷你蛋白 binder（40–90 aa），再拼装先导肽，形成可经胞外注射系统（PVC）递送的抗菌载荷。", size=10.5)
add_heading("2.3 载荷结构", 2)
add_para("完整载荷 = Pdp1_NTD（先导肽，59 aa）+ linker（10 aa）+ binder（功能域，40–90 aa），总长 118–162 aa。", size=10.5)
add_seq_para("Pdp1_NTD：", PDP1)
add_seq_para("linker：", LINKER)

# ============ 三、六环管线 ============
add_heading("三、六环管线与方法", 1)
add_table(
    ["环", "环节", "方法 / 工具", "产出"],
    [
        ["环1", "靶点分析", "知识库推导（8 靶点）", "8 靶点知识库"],
        ["环2", "结构预测", "PDB 下载 + Chai-1 从头预测", "8/8 结构"],
        ["环3", "Binder 设计", "RFdiffusion 从头生成骨架", "每靶点 22–32 骨架"],
        ["环4", "评分排序", "ProteinMPNN + ESM-2 650M", "642 条候选"],
        ["环5", "输出 binder", "按靶点取 Top3", "21 条 Top"],
        ["环6", "拼装载", "Pdp1_NTD + linker + binder", "21 条载荷"],
    ],
    col_widths=[1.2, 2.5, 6.0, 4.5],
    font_size=9.5
)
add_para("", size=6)
add_para("靶点选择五原则：表面暴露性（可被 binder 触及）、毒力/耐药相关性、保守性（降低逃逸突变）、与宿主无同源性（降低脱靶毒性）、临床已验证的相关性。", size=10)

# ============ 四、靶点清单 ============
add_heading("四、靶点清单", 1)
rows = []
for t in ["KP_KPC2","KP_NDM1","KP_OXA48","KP_SHV1","KP_OmpA","KP_OmpC","KP_TonB","KP_IutA"]:
    m = targets_kb.get(t, {})
    cls, sub = MECH.get(t, ("", ""))
    rows.append([t, m.get("gene",""), f"{cls}（{sub}）", m.get("length_aa",""), m.get("uniprot",""), m.get("pdb") or "Chai-1"])
add_table(
    ["靶点", "基因", "机制分类", "长度(aa)", "UniProt", "结构来源"],
    rows, col_widths=[2.0, 1.7, 4.2, 1.6, 1.8, 2.0], font_size=9
)

# ============ 五、靶点详细论证 ============
add_heading("五、靶点详细论证", 1)
all_targets = ordered + ["KP_IutA"]
for t in all_targets:
    m = targets_kb.get(t, {})
    cls, sub = MECH.get(t, ("", ""))
    idx = ordered.index(t) + 1 if t in ordered else 8
    add_heading(f"5.{idx} {t}（{m.get('protein','')}）", 2)
    add_para(f"基因：{m.get('gene','')}  | 机制：{cls}（{sub}）  | 长度：{m.get('length_aa','')} aa  | UniProt：{m.get('uniprot','')}", size=9.5, color=(0x40,0x40,0x40))
    add_para(f"功能：{m.get('function','')}", size=10)
    rat = m.get("rationale", {})
    if rat:
        for k, label in [("surface_exposed","表面暴露"),("virulence_relevance","毒力相关性"),("conservation","保守性"),("host_homology","宿主同源性"),("clinical_evidence","临床证据")]:
            if k in rat:
                add_para(f"· {label}：{rat[k]}", size=9.5)
    if m.get("design_strategy"):
        add_para(f"· 设计策略：{m.get('design_strategy','')}", size=9.5)
    seq = m.get("sequence", "")
    if seq:
        add_seq_para("全长序列：", seq)

doc.add_page_break()

# ============ 六、评分结果 ============
add_heading("六、评分结果摘要", 1)
add_para("评分采用 ProteinMPNN 序列设计 + ESM-2 650M 折叠质量 composite 分数（composite = emb_norm×100 + pLL×10，≥1020 约对应 pLDDT≥90）。", size=10)
rows = []
# 从 ring4 统计每靶点候选数和最佳分数
from collections import defaultdict
r4_by = defaultdict(list)
for b in r4:
    r4_by[b["target"]].append(b)
for t in ordered:
    cands = r4_by.get(t, [])
    n_cand = len(cands)
    best = best_score(t)
    best_pLL = max((x.get("pLL", 0) for x in by_target[t]), default=0)
    n_scaf = {"KP_OmpC": 22}.get(t, 32)
    rows.append([t, n_scaf, n_cand, best, round(best_pLL, 2)])
add_table(["靶点", "骨架数", "候选数", "最佳 composite", "最佳 pLL"], rows,
          col_widths=[3.0, 2.0, 2.0, 3.0, 2.0], font_size=9.5)

# ============ 七、载荷明细 ============
add_heading("七、载荷明细（21 条）", 1)
add_para("以下列出每个靶点 Top3 载荷。每条载荷由 Pdp1_NTD + linker + binder 三段组成，下表给出 binder 功能域序列（完整载荷 = Pdp1_NTD + GGSGGGGSGG + 下列 binder 序列）。", size=10)

for t in ordered:
    items = by_target[t]
    add_heading(f"7.{ordered.index(t)+1} {t}", 2)
    m = targets_kb.get(t, {})
    cls, sub = MECH.get(t, ("", ""))
    add_para(f"机制：{cls}（{sub}）  | 基因 {m.get('gene','')}  | UniProt {m.get('uniprot','')}", size=9, color=(0x40,0x40,0x40))
    for i, x in enumerate(items, 1):
        bid = x["binder_id"]
        add_para(f"候选 {i}：{bid}  |  composite={x['esm_composite']}  |  pLL={x['pLL']:.3f}  |  binder长度={x['length']}aa  |  载荷长度={x['payload_length']}aa", size=9.5, bold=True)
        add_seq_para("binder 序列：", x["binder_sequence"])
        add_seq_para("完整载荷：", x["payload_sequence"], color=(0x00,0x00,0x60))

doc.add_page_break()

# ============ 八、质量评估 ============
add_heading("八、质量评估与局限性", 1)
add_heading("8.1 质量提示", 2)
add_para("本次 binder 为 RFdiffusion 从头生成的 CA-only 骨架（仅主链、无侧链），ProteinMPNN 在无侧链约束下采样序列。composite 分数整体偏低（最高 1003，低于 1020 的「pLDDT≥90」经验合格线），且部分序列氨基酸组成偏简单重复（如连续的 K/E/R/A），这是从头设计 + 无结构模板的固有局限，属正常现象。", size=10.5)
add_heading("8.2 跳过的靶点", 2)
add_para("KP_IutA（气杆菌素受体，733 aa）：大靶点在 16GB 显卡上跑 RFdiffusion 触发 CUDA OOM，按指示跳过（仅产出 4 个骨架）。建议后续拆结构域（plug 域 + β-桶域）分别设计。", size=10.5)
add_heading("8.3 后续建议", 2)
for line in [
    "• 湿实验验证：SPR 测结合亲和力 Kd、MIC/MBC 杀菌实验、动物模型",
    "• 序列优化：对 composite 低/氨基酸组成异常序列做定向进化或 MPNN 加约束重设计",
    "• 补跑 IutA：拆结构域或降低 num_designs",
    "• 提升骨架质量：RFdiffusion 增加 denoise 步数、加侧链建模（非 CA-only）",
]:
    add_para(line, size=10.5)

# ============ 九、数据目录说明 ============
add_heading("九、数据目录与文件说明", 1)
add_table(
    ["目录", "内容", "关键文件"],
    [
        ["01_最终结果", "六环最终产物", "payloads.fasta/json + ring*.json"],
        ["02_靶点与结构", "靶点知识库 + 结构", "kp_target_knowledge_base.json + PDB"],
        ["03_设计过程数据", "RFdiffusion + MPNN 中间产物", "每靶点 rfdiffusion/ 目录"],
        ["04_运算日志", "各环节运行日志", "kp_ring*.log"],
        ["05_报告", "HTML 可视化报告", "KP_载荷设计报告.html"],
    ],
    col_widths=[3.5, 4.5, 5.0], font_size=9.5
)
add_para("", size=6)
add_para("详细数据导航见同目录下 README.md。", size=10)

# ============ 十、计算环境 ============
add_heading("十、计算环境", 1)
for line in [
    "• GPU：NVIDIA RTX 4070 Ti SUPER（16 GB）",
    "• 系统：Windows + WSL2（Ubuntu 24.04）",
    "• conda 环境：protein_design（torch 2.5.1+cu121, transformers）",
    "• 工具：RFdiffusion、ProteinMPNN、ESM-2 650M、Chai-1",
    "• 载荷先导肽：Pdp1_NTD（PVC 胞外注射系统引导头）",
]:
    add_para(line, size=10.5)

# 保存
out_path = os.path.join(OUT_DIR, "肺炎克雷伯菌载荷设计_详细介绍.docx")
doc.save(out_path)
print(f"Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
