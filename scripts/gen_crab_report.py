"""生成鲍曼不动杆菌载荷设计报告 HTML（output CRAB 目录）。
读取 payloads.json + ab_target_knowledge_base.json，输出自包含 HTML。
"""
import json, os, html

BASE = r"H:\eazyclaw\saved\MASA3"
OUT_DIR = os.path.join(BASE, "output CRAB")
os.makedirs(OUT_DIR, exist_ok=True)

p = json.load(open(os.path.join(BASE, "results", "payloads.json"), encoding="utf-8"))
kb = json.load(open(os.path.join(BASE, "data", "antigens", "ab_target_knowledge_base.json"), encoding="utf-8"))

targets_meta = kb["targets"]

# 靶点机制/功能摘要
MECH = {
    "AB_OmpA": ("外膜蛋白", "毒力/粘附/凋亡/耐药"),
    "AB_BauA": ("铁摄取", "TonB依赖外膜受体"),
    "AB_BasE": ("铁摄取", "铁载体合成 NRPS"),
    "AB_CarO": ("孔蛋白", "碳青霉烯耐药"),
    "AB_Omp33": ("孔蛋白", "凋亡/耐药"),
    "AB_CsuAB": ("菌毛/粘附", "Csu 菌毛亚基"),
    "AB_CsuE": ("菌毛/粘附", "Csu 菌毛顶端黏附素"),
    "AB_Ata": ("粘附", "自转运粘附素"),
    "AB_AdeB": ("耐药", "RND 外排泵"),
    "AB_LpxC": ("必需", "LPS 合成必需酶"),
    "AB_PmrC": ("耐药", "colistin 耐药 PetN 转移酶"),
}

PDP1 = "MPRYANYQINPKQNIKNSHGKSSSSDFSSGYLSFSNNSLDDPFIRQQVKREFIWEGHMKEIEEASRL"
LINKER = "GGSGGGGSGG"

# 按靶点分组
by_target = {}
for x in p:
    by_target.setdefault(x["target"], []).append(x)

# 靶点排序：按 best composite 降序
def best_score(t):
    return max(x["esm_composite"] for x in by_target[t])
ordered = sorted(by_target.keys(), key=best_score, reverse=True)

# 统计
n_total = len(p)
n_targets = len(by_target)
comps = [x["esm_composite"] for x in p]
lens = [x["payload_length"] for x in p]

# 生成靶点卡片
target_cards = []
for t in ordered:
    items = by_target[t]
    best = best_score(t)
    cls, sub = MECH.get(t, ("", ""))
    meta = targets_meta.get(t, {})
    uniprot = meta.get("uniprot", "")
    func = meta.get("function", "")
    rows = []
    for i, x in enumerate(items, 1):
        rows.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td><code>{html.escape(x['binder_id'])}</code></td>
          <td class="num">{x['esm_composite']}</td>
          <td class="num">{x['pLL']:.3f}</td>
          <td class="num">{x['length']}</td>
          <td class="num">{x['payload_length']}</td>
          <td class="seq">{html.escape(x['binder_sequence'])}</td>
        </tr>""")
    target_cards.append(f"""
    <div class="target-card">
      <div class="target-head">
        <h3>{html.escape(t)}</h3>
        <span class="badge">{html.escape(cls)}</span>
        <span class="badge sub">{html.escape(sub)}</span>
        <span class="uniprot">UniProt: {html.escape(uniprot)}</span>
        <span class="best">best composite = {best}</span>
      </div>
      <p class="func">{html.escape(func)}</p>
      <table class="seq-table">
        <thead><tr><th>#</th><th>Binder ID</th><th>Composite</th><th>pLL</th><th>binder</th><th>载荷</th><th>Binder 序列</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>""")

# 载荷 FASTA 全文
fasta_lines = []
for t in ordered:
    for x in by_target[t]:
        bid = x["binder_id"].split(" len=")[0]
        fasta_lines.append(f">&gt;{t}|{bid} len={x['payload_length']} payload\n{x['payload_sequence']}")
fasta_text = "\n".join(fasta_lines)

html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>后羿 HOUYI · 鲍曼不动杆菌（CRAB）抗菌载荷设计报告</title>
<style>
:root {{
  --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --muted: #8b949e; --accent: #58a6ff; --green: #3fb950; --orange: #d29922; --red: #f85149;
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:32px 24px; }}
h1 {{ font-size:28px; margin:0 0 4px; }}
h2 {{ font-size:20px; margin:40px 0 12px; border-bottom:1px solid var(--border); padding-bottom:8px; color:var(--accent); }}
.subtitle {{ color:var(--muted); font-size:14px; margin-bottom:24px; }}
.meta-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:20px 0; }}
.metric {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; }}
.metric .val {{ font-size:28px; font-weight:700; color:var(--accent); }}
.metric .lbl {{ font-size:13px; color:var(--muted); }}
.callout {{ background:#1c2128; border-left:4px solid var(--orange); border-radius:8px; padding:14px 18px; margin:16px 0; font-size:14px; }}
.callout.green {{ border-left-color:var(--green); }}
.callout.red {{ border-left-color:var(--red); }}
.target-card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; margin:18px 0; }}
.target-head {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; }}
.target-head h3 {{ margin:0; font-size:18px; }}
.badge {{ background:#1f6feb33; color:var(--accent); border:1px solid #1f6feb66; border-radius:20px; padding:2px 10px; font-size:12px; }}
.badge.sub {{ background:#d2992233; color:var(--orange); border-color:#d2992266; }}
.uniprot {{ color:var(--muted); font-size:12px; }}
.best {{ margin-left:auto; font-weight:600; color:var(--green); font-size:13px; }}
.func {{ color:var(--muted); font-size:13px; margin:10px 0; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
.seq-table th {{ text-align:left; padding:8px; border-bottom:1px solid var(--border); color:var(--muted); font-weight:600; }}
.seq-table td {{ padding:8px; border-bottom:1px solid var(--border); vertical-align:top; }}
.rank {{ color:var(--green); font-weight:700; }}
.num {{ text-align:right; white-space:nowrap; }}
.seq {{ font-family:'SF Mono',Consolas,monospace; font-size:11px; word-break:break-all; color:var(--muted); }}
code {{ font-family:'SF Mono',Consolas,monospace; font-size:11px; }}
pre.fasta {{ background:#0d1117; border:1px solid var(--border); border-radius:8px; padding:16px; overflow-x:auto; font-size:11px; color:#7ee787; white-space:pre-wrap; word-break:break-all; }}
.footer {{ margin-top:48px; padding-top:16px; border-top:1px solid var(--border); color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">

<h1>后羿 HOUYI · 抗菌载荷设计报告</h1>
<div class="subtitle">靶菌：鲍曼不动杆菌 <em>Acinetobacter baumannii</em>（CRAB / ESKAPE / WHO 关键优先病原体）</div>

<div class="callout red">
  <strong>菌株背景：</strong>{html.escape(kb.get("organism_note", ""))}
</div>

<h2>一、项目概览</h2>
<div class="meta-grid">
  <div class="metric"><div class="val">{n_total}</div><div class="lbl">载荷总数</div></div>
  <div class="metric"><div class="val">{n_targets}</div><div class="lbl">覆盖靶点</div></div>
  <div class="metric"><div class="val">{max(comps)}</div><div class="lbl">最高 composite</div></div>
  <div class="metric"><div class="val">{min(lens)}–{max(lens)}</div><div class="lbl">载荷长度 (aa)</div></div>
  <div class="metric"><div class="val">1</div><div class="lbl">跳过靶点 (BasE)</div></div>
</div>

<h2>二、六环管线与方法</h2>
<table class="seq-table">
  <thead><tr><th>环</th><th>环节</th><th>方法 / 工具</th><th>产出</th></tr></thead>
  <tbody>
    <tr><td>环1</td><td>靶点分析</td><td>UniProt 检索 + 五原则筛选（表面暴露/毒力耐药/保守/无宿主同源/临床证据）</td><td>11 个靶点知识库</td></tr>
    <tr><td>环2</td><td>结构预测</td><td>PDB 下载（4G88）+ Chai-1 从头预测（无 PDB 靶点）</td><td>11/11 结构就绪</td></tr>
    <tr><td>环3</td><td>Binder 设计</td><td>RFdiffusion 从头生成骨架（binder 40–90aa）</td><td>每靶点 5–16 骨架</td></tr>
    <tr><td>环4</td><td>评分排序</td><td>ProteinMPNN 序列设计 + ESM-2 650M 折叠质量评分</td><td>423 条候选 binder</td></tr>
    <tr><td>环5</td><td>输出 binder</td><td>按靶点+骨架去重，取 Top3</td><td>30 条 Top binder</td></tr>
    <tr><td>环6</td><td>拼装载</td><td>Pdp1_NTD + linker + binder</td><td>30 条完整载荷</td></tr>
  </tbody>
</table>

<div class="callout green">
  <strong>载荷结构：</strong>Pdp1_NTD（先导肽 59aa，N 端引导头，装进 PVC 胞外注射系统）— linker（GGSGGGGSGG，10aa）— binder（功能域，结合靶点）。完整载荷为纯氨基酸序列，总长 119–163 aa。
</div>

<h2>三、靶点清单与载荷明细</h2>
<p style="color:var(--muted);font-size:13px;">共 {n_targets} 个靶点成功产出载荷，按最佳 composite 降序排列。每靶点 3 条不同骨架的 Top binder。</p>
{''.join(target_cards)}

<h2>四、质量评估与说明</h2>
<div class="callout">
  <strong>⚠️ 质量提示（重要）：</strong>本次 binder 为 RFdiffusion 从头生成的 <strong>CA-only 骨架</strong>（仅主链、无侧链），ProteinMPNN 在无侧链约束下采样序列。composite 分数整体偏低（最高 1004，低于 1020 的「pLDDT≥90」经验合格线），且部分序列氨基酸组成偏简单重复——这是<strong>从头设计 + 无结构模板</strong>的固有局限，属正常现象。<br><br>
  这些序列应视为<strong>优化起点</strong>，真正获得高亲和力、强杀伤的 binder 需经湿实验（SPR 测 Kd、MIC/MBC 杀菌实验、动物模型）筛选与迭代。
</div>
<div class="callout red">
  <strong>跳过的靶点：</strong>AB_BasE（铁载体合成 NRPS，542aa）。因 500aa 级大靶点在 16GB 显卡上跑 RFdiffusion 吃力，且未生成骨架，按用户指示跳过，后续可拆结构域或降 num_designs 补跑。
</div>

<h2>五、载荷序列（FASTA）</h2>
<pre class="fasta">{fasta_text}</pre>

<div class="footer">
  生成：后羿 HOUYI 端到端抗菌载荷设计平台 · 鲍曼不动杆菌（Acinetobacter baumannii）· 2026-10-02<br>
  产物文件：results/payloads.fasta · results/payloads.json
</div>

</div>
</body>
</html>
"""

out_path = os.path.join(OUT_DIR, "CRAB_载荷设计报告.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html_doc)

# 同时输出纯 FASTA 和 JSON 副本
import shutil
shutil.copy(os.path.join(BASE, "results", "payloads.fasta"),
            os.path.join(OUT_DIR, "payloads.fasta"))
shutil.copy(os.path.join(BASE, "results", "payloads.json"),
            os.path.join(OUT_DIR, "payloads.json"))

print("报告已生成:", out_path)
print("FASTA 副本:", os.path.join(OUT_DIR, "payloads.fasta"))
print("JSON 副本:", os.path.join(OUT_DIR, "payloads.json"))
