"""从 MASA 三线报告 HTML 提取胞内菌壁攻击三线（GGEP/SrtA/SpA）Top 候选，
落成 output SA/10_胞内菌壁攻击三线/ 目录的 json + fasta + README。
"""
import re, json, os

SRC = r"H:\eazyclaw\saved\MASA\Antimicrobial_Cargo_Final_Report.html"
OUT = r"H:\eazyclaw\saved\MASA3\output SA\10_胞内菌壁攻击三线"
os.makedirs(OUT, exist_ok=True)

html = open(SRC, encoding='utf-8').read()
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
parsed = []
for r in rows:
    seq_m = re.search(r'class="seq">([A-Z]+)</td>', r)
    if not seq_m:
        continue
    seq = seq_m.group(1)
    tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
    cand = plddt = ptm = ''
    for td in tds:
        txt = re.sub(r'<[^>]+>', '', td).strip()
        if not txt:
            continue
        if re.match(r'^(top|spa_|srtA_)', txt):
            cand = txt
        elif re.match(r'^\d+\.\d+$', txt):
            if not plddt:
                plddt = txt
            elif not ptm:
                ptm = txt
    if cand and seq:
        parsed.append({'candidate': cand, 'pLDDT': plddt, 'pTM': ptm, 'sequence': seq})

# 三线分类
def line_of(c):
    if c.startswith('top'):
        return 'A_GGEP'
    if c.startswith('spa'):
        return 'C_SpA'
    if c.startswith('srtA'):
        return 'B_SrtA'
    return 'unknown'

LINES = {
    'A_GGEP': {'name': 'A线 GGEP 微型内溶素', 'target': '五甘氨酸交联桥 (Lysostaphin GGEP 域)',
               'mechanism': '酶切肽聚糖 G5 交联桥 → 细胞壁裂解', 'length_note': '101 aa'},
    'C_SpA': {'name': 'C线 Protein A 阻断剂', 'target': 'Protein A IgG Fc 结合位点',
              'mechanism': '占据 SpA IgG 结合位点 → 阻断免疫逃逸', 'length_note': '80-120 aa'},
    'B_SrtA': {'name': 'B线 Sortase A 抑制剂', 'target': 'Sortase A Cys184 活性位点',
               'mechanism': '阻断毒力因子锚定 → 毒力全废', 'length_note': '80-120 aa'},
}

# 结构化输出
structured = {
    'title': '胞内抗金葡菌载荷库 — 三线胞内菌壁攻击设计（Top 候选）',
    'source': 'MASA/Antimicrobial_Cargo_Final_Report.html (2026-06-06)',
    'note': '完整 169 条候选序列未单独持久化，本文件仅提取报告内嵌的 Top 候选（A线5 + C线10 + B线5 = 20 条）',
    'lines': {},
}
for p in parsed:
    ln = line_of(p['candidate'])
    structured['lines'].setdefault(ln, []).append(p)

json.dump(structured, open(os.path.join(OUT, 'three_line_top_candidates.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

# 分线 fasta + 汇总 fasta
all_fa = []
for ln, items in structured['lines'].items():
    info = LINES[ln]
    fa_path = os.path.join(OUT, f'three_line_{ln}.fasta')
    with open(fa_path, 'w', encoding='utf-8') as f:
        for p in items:
            f.write(f">{p['candidate']} pLDDT={p['pLDDT']} pTM={p['pTM']}\n{p['sequence']}\n")
            all_fa.append(f">{ln}_{p['candidate']} pLDDT={p['pLDDT']} pTM={p['pTM']}\n{p['sequence']}\n")
with open(os.path.join(OUT, 'three_line_all_top20.fasta'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(all_fa) + '\n')

# README
readme = """# 10_胞内菌壁攻击三线

## 这是什么

本目录归置 MASA 早期（2026-06-06）的「胞内菌壁攻击三线」计算设计成果，
与 output SA 主体的「16 靶点表面 binder 库」是**两个互补的设计维度**。

| 维度 | 16 靶点表面 binder（04/05/06 目录） | 本目录三线 |
|------|----------------------------------|-----------|
| 策略 | 结合阻断表面/功能蛋白 | 溶壁 + 抗毒力锚定 + 抗免疫逃逸 |
| 靶点 | B3_ClfA / C3_PBP2a / D2_Hla 等 16 个 | GGEP / SrtA / SpA 三条线 |
| 载荷类型 | binder（40-90 aa） | 内溶素（101 aa）+ 微型 binder（80-120 aa） |
| 数量 | 45 条 payloads | 169 条候选（本目录提取 Top 20） |
| 阶段 | MASA² | MASA 早期 |

## 三线机制（三重正交攻击，几乎不可能产生耐药）

- **A线 GGEP 内溶素**：来源于 Lysostaphin GGEP 域（aa280-380），切割金葡菌五甘氨酸
  交联桥 → 细胞壁裂解致死。大肠杆菌无 G5 桥、真核无肽聚糖，故对宿主安全。
- **C线 SpA 阻断剂**：微型 binder 占据 Protein A 的 IgG Fc 结合位点 → 金葡菌无法
  结合抗体 → 暴露于调理吞噬 + 补体。
- **B线 SrtA 抑制剂**：微型 binder 阻断 Sortase A Cys184 活性位点 → 表面蛋白
  （Protein A / ClfA / FnBP 等）无法锚定 → 毒力全废。

## 文件说明

- `three_line_top_candidates.json` — 结构化 Top 20 候选（含 pLDDT/pTM/序列）
- `three_line_A_GGEP.fasta` — A线 Top5（内溶素 101 aa）
- `three_line_C_SpA.fasta` — C线 Top10（SpA 阻断剂）
- `three_line_B_SrtA.fasta` — B线 Top5（SrtA 抑制剂）
- `three_line_all_top20.fasta` — 三线汇总

## 数据来源与完整性说明

序列数据提取自 `MASA/Antimicrobial_Cargo_Final_Report.html`（与 09_报告 里的
「胞内抗金葡菌载荷库 — 三线设计完整报告.html」为同一工作的两个版本）。

⚠️ 完整 169 条候选序列在早期 MASA 阶段**未单独持久化**（只内嵌在 HTML 表格里），
本目录仅保留报告内嵌的 Top 候选（A线5 + C线10 + B线5 = 20 条）。如需完整 169 条，
需回溯早期计算工作目录或重跑三线设计管线。
"""
open(os.path.join(OUT, 'README_三线说明.md'), 'w', encoding='utf-8').write(readme)

print(f"Done. 目录：{OUT}")
for f in os.listdir(OUT):
    print(' ', f, os.path.getsize(os.path.join(OUT, f)))
