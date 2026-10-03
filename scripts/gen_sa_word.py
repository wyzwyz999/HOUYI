"""生成金黄色葡萄球菌（Staphylococcus aureus）载荷设计详细 Word 介绍文档。
读取 output SA 下的 payloads.json / ring1_targets.json / 知识库，动态生成。
适配金葡菌数据结构（15 靶点，MASA² 体系）。
"""
import json, os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = r"H:\eazyclaw\saved\MASA3"
OUT_DIR = os.path.join(BASE, "output SA")

payloads = json.load(open(os.path.join(OUT_DIR, "06_最终载荷", "payloads.json"), encoding="utf-8"))
kb = json.load(open(os.path.join(BASE, "data", "antigens", "target_knowledge_base.json"), encoding="utf-8"))
r1 = json.load(open(os.path.join(OUT_DIR, "02_靶点序列", "ring1_targets.json"), encoding="utf-8"))
tmeta = r1.get("target_meta", {})
targets_kb = kb.get("targets", {})

PDP1 = "MPRYANYQINPKQNIKNSHGKSSSSDFSSGYLSFSNNSLDDPFIRQQVKREFIWEGHMKEIEEASRL"
LINKER = "GGSGGGGSGG"

# 按靶点分组载荷（保持 payloads 原始顺序）
by_target = {}
for x in payloads:
    by_target.setdefault(x["target"], []).append(x)

# 靶点顺序：按知识库 targets 顺序（15 靶点）
ordered = list(targets_kb.keys())
# 只保留有 payload 的靶点（避免 keyerror）
ordered_payload = [t for t in ordered if t in by_target]

def payload_seq(x):
    return x.get("binder_sequence") or x.get("sequence", "")

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
run = p.add_run("金黄色葡萄球菌（Staphylococcus aureus / MRSA）\n抗菌载荷端到端设计报告")
set_run_font(run, size=15, bold=True)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("详细技术介绍与数据说明")
set_run_font(run, size=11, color=(0x80,0x80,0x80))

add_para("", size=6)
meta = [
    ("病原菌", "Staphylococcus aureus（金黄色葡萄球菌 / MRSA）"),
    ("平台", "后羿 HOUYI（端到端抗菌载荷设计平台，MASA² 载荷库）"),
    ("交付物", "45 条抗菌载荷（15 靶点 × Top3）"),
    ("生成日期", "2026-10-02"),
    ("数据目录", os.path.join(OUT_DIR, "")),
]
for k, v in meta:
    add_para(f"{k}：{v}", size=10, color=(0x40,0x40,0x40))

doc.add_page_break()

# ============ 一、执行摘要 ============
add_heading("一、执行摘要", 1)
add_para("本项目利用后羿（HOUYI）端到端抗菌载荷设计平台，针对金黄色葡萄球菌（Staphylococcus aureus）——MRSA 这一 WHO 高度优先级耐药病原体，完成了从靶点分析到载荷拼装的全自动设计流程（基于 MASA² 胞内抗金葡菌载荷库）。")
add_para("核心成果：")
for line in [
    "• 分析并论证 15 个抗菌靶点（粘附素、毒素、耐药决定因子、群体感应、细胞壁合成、铁摄取、生物膜、细胞分裂等机制类别）",
    "• 完成结构准备（12 个 PDB 下载 + 3 个 Chai-1 从头预测）",
    "• RFdiffusion 从头设计 binder 骨架，ProteinMPNN 序列设计 + ESM-2 折叠评分",
    "• 输出 45 条 Top binder（15 靶点 × Top3），并拼装为完整载荷 Pdp1_NTD-linker-binder",
]:
    add_para(line, size=10.5)

# ============ 二、背景 ============
add_heading("二、研究背景", 1)
add_heading("2.1 病原体威胁", 2)
add_para(kb.get("organism_note", ""), size=10.5)
add_heading("2.2 载荷设计思路", 2)
add_para("传统抗生素面临严重的耐药问题（MRSA 对 β-内酰胺类耐药的核心机制即 PBP2a/MecA）。本项目采用从头蛋白设计策略：在病原体表面/关键功能蛋白上，用 RFdiffusion 生成能特异性结合的迷你蛋白 binder，再拼装先导肽，形成可经胞外注射系统（PVC）递送的抗菌载荷。", size=10.5)
add_heading("2.3 载荷结构", 2)
add_para("完整载荷 = Pdp1_NTD（先导肽，59 aa）+ linker（10 aa）+ binder（功能域，约 40–90 aa）。", size=10.5)
add_seq_para("Pdp1_NTD：", PDP1)
add_seq_para("linker：", LINKER)

# ============ 三、六环管线 ============
add_heading("三、管线与方法", 1)
add_table(
    ["环", "环节", "方法 / 工具", "产出"],
    [
        ["环1", "靶点分析", "UniProt 检索 + 五原则筛选", "15 靶点知识库"],
        ["环2", "结构预测", "PDB 下载 + Chai-1 从头预测", "15 结构"],
        ["环3", "Binder 设计", "RFdiffusion 从头生成骨架", "每靶点多骨架"],
        ["环4", "评分排序", "ProteinMPNN + ESM-2", "候选 binder"],
        ["环5", "输出 binder", "按靶点取 Top3", "45 条 Top"],
        ["环6", "拼装载", "Pdp1_NTD + linker + binder", "45 条载荷"],
    ],
    col_widths=[1.2, 2.5, 6.0, 4.5],
    font_size=9.5
)
add_para("", size=6)
principles = kb.get("target_selection_principles", [])
if principles:
    add_para("靶点选择五原则：", size=10, bold=True)
    if isinstance(principles, list):
        for pr in principles:
            add_para(f"• {pr}", size=9.5)
    else:
        add_para(str(principles), size=9.5)

# ============ 四、靶点清单 ============
add_heading("四、靶点清单", 1)
rows = []
for t in ordered:
    m = targets_kb.get(t, {})
    rows.append([t, m.get("gene",""), m.get("mechanism_class",""), m.get("length_aa",""), m.get("pdb") or "Chai-1"])
add_table(
    ["靶点", "基因", "机制分类", "长度(aa)", "结构来源"],
    rows, col_widths=[2.6, 2.0, 4.6, 1.8, 2.0], font_size=9
)

# ============ 五、靶点详细论证 ============
add_heading("五、靶点详细论证", 1)
for i, t in enumerate(ordered, 1):
    m = targets_kb.get(t, {})
    add_heading(f"5.{i} {t}（{m.get('protein','')}）", 2)
    add_para(f"基因：{m.get('gene','')}  | 机制：{m.get('mechanism_class','')}  | 长度：{m.get('length_aa','')} aa  | 结构：{m.get('pdb') or 'Chai-1 预测'}", size=9.5, color=(0x40,0x40,0x40))
    add_para(f"功能：{m.get('function','')}", size=10)
    rat = m.get("rationale", {})
    if isinstance(rat, dict):
        for k, label in [("surface_exposed","表面暴露"),("virulence_relevance","毒力相关性"),("conservation","保守性"),("host_homology","宿主同源性"),("clinical_evidence","临床证据")]:
            if k in rat and rat[k]:
                add_para(f"· {label}：{rat[k]}", size=9.5)
    if m.get("design_strategy"):
        add_para(f"· 设计策略：{m.get('design_strategy','')}", size=9.5)
    if m.get("wetlab_status"):
        add_para(f"· 湿实验状态：{m.get('wetlab_status','')}", size=9.5, color=(0x00,0x50,0x00))
    seq = m.get("sequence", "")
    if seq:
        add_seq_para("全长序列（截断）：", seq[:200] + ("..." if len(seq) > 200 else ""))

doc.add_page_break()

# ============ 六、评分结果 ============
add_heading("六、评分结果摘要", 1)
add_para("评分采用 ProteinMPNN 序列设计 + ESM-2 折叠质量评分。MASA² 载荷库为早期产物，部分靶点 binder 以序列长度等启发式指标初筛（scorer=length），后续经 ESM-2 composite 分数复核排序。", size=10)
rows = []
for t in ordered_payload:
    items = by_target[t]
    n = len(items)
    rows.append([t, n, payload_seq(items[0])[:20] + "…" if payload_seq(items[0]) else ""])
add_table(["靶点", "载荷数", "Top1 binder 前缀"], rows,
          col_widths=[3.5, 2.0, 7.5], font_size=9.5)

# ============ 七、载荷明细 ============
add_heading("七、载荷明细（45 条）", 1)
add_para("以下列出每个靶点 Top3 载荷。每条载荷由 Pdp1_NTD + linker + binder 三段组成，下表给出 binder 功能域序列（完整载荷 = Pdp1_NTD + GGSGGGGSGG + 下列 binder 序列）。", size=10)

for i, t in enumerate(ordered_payload, 1):
    items = by_target[t]
    m = targets_kb.get(t, {})
    add_heading(f"7.{i} {t}", 2)
    add_para(f"机制：{m.get('mechanism_class','')}  | 基因 {m.get('gene','')}  | 结构 {m.get('pdb') or 'Chai-1'}", size=9, color=(0x40,0x40,0x40))
    for j, x in enumerate(items, 1):
        bid = x.get("binder_id", "")
        bseq = payload_seq(x)
        add_para(f"候选 {j}：{bid}  |  binder长度={x.get('length','')}aa  |  载荷长度={x.get('payload_length','')}aa  |  来源={x.get('source','')}", size=9.5, bold=True)
        add_seq_para("binder 序列：", bseq)
        add_seq_para("完整载荷：", x.get("payload_sequence",""), color=(0x00,0x00,0x60))

doc.add_page_break()

# ============ 八、质量评估 ============
add_heading("八、质量评估与局限性", 1)
add_heading("8.1 质量提示", 2)
add_para("MASA² 阶段 binder 为 RFdiffusion 从头生成的骨架，ProteinMPNN 在无侧链约束下采样序列。部分序列氨基酸组成偏简单重复（如连续的 K/E/R/A），这是从头设计 + 无结构模板的固有局限。后续已用 ESM-2 composite 分数进行折叠质量复核（详见 MASA2_ESM_FOLDING_RANKING 报告）。", size=10.5)
add_heading("8.2 结构缺失靶点", 2)
add_para("B5_SdrD、B7_SasG、E3_Ddl 三个靶点无实验 PDB 结构，采用 Chai-1 从头预测。其中 E3_Ddl 的 Chai-1 预测结果已纳入结构目录。", size=10.5)
add_heading("8.3 后续建议", 2)
for line in [
    "• 湿实验验证：SPR 测结合亲和力 Kd、MIC/MBC 杀菌实验、动物模型（已有部分靶点 wetlab_status=已验证）",
    "• 序列优化：对氨基酸组成异常序列做定向进化或 MPNN 加约束重设计",
    "• 补全结构：SdrD/SasG 大蛋白可拆结构域分别设计",
    "• 提升骨架质量：RFdiffusion 增加 denoise 步数、加侧链建模（非 CA-only）",
]:
    add_para(line, size=10.5)

# ============ 九、数据目录说明 ============
add_heading("九、数据目录与文件说明", 1)
add_table(
    ["目录", "内容", "关键文件"],
    [
        ["01_靶点知识库", "15 靶点科学论证", "target_knowledge_base.json"],
        ["02_靶点序列", "靶点全长序列", "15_targets_final.json / ring1_targets.json"],
        ["03_结构预测", "15 个 PDB 结构", "*.pdb + ring2_structure.json"],
        ["04_Binder骨架", "RFdiffusion 骨架", "每靶点 .pdb/.trb"],
        ["05_评分结果", "候选评分", "ring4_scored.json + per_target_esm_scores/"],
        ["06_最终载荷", "45 条载荷", "payloads.json/fasta + top_binders"],
        ["07_运算日志", "各环节日志说明", "README_日志说明.md"],
        ["08_脚本", "运行脚本 + 核心代码", "pipeline.py + hoyi/"],
        ["09_报告", "HTML 报告", "7 个 MASA² + 后羿报告"],
    ],
    col_widths=[3.5, 4.5, 5.0], font_size=9.5
)
add_para("", size=6)
add_para("详细数据导航见同目录下 README_数据说明.md。", size=10)

# ============ 十、计算环境 ============
add_heading("十、计算环境", 1)
for line in [
    "• GPU：NVIDIA RTX 4070 Ti SUPER（16 GB）",
    "• 系统：Windows + WSL2（Ubuntu 24.04）",
    "• conda 环境：protein_design（torch 2.5.1+cu121, transformers 4.28.0）",
    "• 工具：RFdiffusion、ProteinMPNN、ESM-2、Chai-1",
    "• 载荷先导肽：Pdp1_NTD（PVC 胞外注射系统引导头）",
]:
    add_para(line, size=10.5)

# 保存
out_path = os.path.join(OUT_DIR, "金黄色葡萄球菌载荷设计_详细介绍.docx")
doc.save(out_path)
print(f"Saved: {out_path} ({os.path.getsize(out_path)} bytes)")
