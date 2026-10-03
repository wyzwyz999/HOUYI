"""生成肺炎克雷伯菌（Klebsiella pneumoniae）载荷设计报告 HTML。

读取 payloads.json + kp_target_knowledge_base.json，输出自包含 HTML。
"""
import json, os, html

BASE = r"H:\eazyclaw\saved\MASA3"
OUT_DIR = os.path.join(BASE, "output KP")
os.makedirs(OUT_DIR, exist_ok=True)

p = json.load(open(os.path.join(BASE, "results", "payloads.json"), encoding="utf-8"))
kb = json.load(open(os.path.join(BASE, "data", "antigens", "kp_target_knowledge_base.json"), encoding="utf-8"))

targets_meta = kb["targets"]

MECH = {
    "KP_KPC2": ("碳青霉烯酶（A类）", "CRKP 超级耐药核心决定因子，水解碳青霉烯"),
    "KP_NDM1": ("金属β内酰胺酶（B类）", "泛耐药核心机制，几乎无药可治"),
    "KP_OXA48": ("碳青霉烯酶（D类）", "第三大碳青霉烯酶家族，质粒传播极广"),
    "KP_SHV1": ("广谱β内酰胺酶（A类）", "染色体固有耐药决定子，ESBL 来源"),
    "KP_OmpA": ("外膜蛋白", "毒力/粘附/生物膜/免疫逃逸"),
    "KP_OmpC": ("外膜孔蛋白", "OmpK36 同源，孔蛋白缺失致最高水平耐药"),
    "KP_TonB": ("铁摄取", "能量转导，驱动铁载体主动转运"),
}

PDP1 = "MPRYANYQINPKQNIKNSHGKSSSSDFSSGYLSFSNNSLDDPFIRQQVKREFIWEGHMKEIEEASRL"
LINKER = "GGSGGGGSGG"

by_target = {}
for x in p:
    by_target.setdefault(x["target"], []).append(x)

def best_score(t):
    return max(x["esm_composite"] for x in by_target[t])
ordered = sorted(by_target.keys(), key=best_score, reverse=True)

n_total = len(p)
n_targets = len(by_target)
comps = [x["esm_composite"] for x in p]
lens = [x["payload_length"] for x in p]

target_cards = []
for t in ordered:
    items = by_target[t]
    meta = targets_meta.get(t, {})
    mech_cat, mech_desc = MECH.get(t, ("", ""))
    rows = ""
    for x in items:
        seq_short = x["binder_sequence"][:60] + ("..." if len(x["binder_sequence"]) > 60 else "")
        rows += f"""
        <tr>
          <td class="mono">{html.escape(x['binder_id'])}</td>
          <td>{x['length']}</td>
          <td><b>{x['esm_composite']}</b></td>
          <td>{x['pLL']:.2f}</td>
          <td class="mono">{html.escape(seq_short)}</td>
        </tr>"""
    card = f"""
    <div class="card">
      <h3>{html.escape(t)} <span class="badge">{html.escape(mech_cat)}</span></h3>
      <p class="desc">{html.escape(mech_desc)}</p>
      <p class="meta">基因 {html.escape(meta.get('gene',''))} · UniProt {html.escape(meta.get('uniprot',''))} · PDB {html.escape(str(meta.get('pdb',''))) or 'Chai-1 预测'} · 最佳 composite <b>{best_score(t)}</b></p>
      <table>
        <thead><tr><th>binder</th><th>长度</th><th>composite</th><th>pLL</th><th>序列（前60aa）</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""
    target_cards.append(card)

# 载荷 FASTA 全文
payload_fasta = ""
for x in p:
    payload_fasta += f">&gt;{x['target']}|{x['binder_id']} len={x['payload_length']}\n{x['payload_sequence']}\n"

html_doc = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>肺炎克雷伯菌（Klebsiella pneumoniae）抗菌载荷设计报告</title>
<style>
body{{font-family:-apple-system,'Segoe UI',Roboto,'PingFang SC',sans-serif;margin:0;background:#f5f6fa;color:#2d3436}}
header{{background:linear-gradient(135deg,#6c5ce7,#a29bfe);color:#fff;padding:32px 40px}}
header h1{{margin:0 0 8px;font-size:26px}}
header p{{margin:4px 0;opacity:.9}}
.container{{max-width:1100px;margin:0 auto;padding:24px}}
.stats{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}
.stat{{background:#fff;border-radius:12px;padding:18px 24px;flex:1;min-width:140px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.stat .num{{font-size:28px;font-weight:700;color:#6c5ce7}}
.stat .lbl{{font-size:13px;color:#636e72;margin-top:4px}}
.card{{background:#fff;border-radius:12px;padding:20px 24px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.card h3{{margin:0 0 4px;font-size:18px}}
.badge{{display:inline-block;background:#6c5ce7;color:#fff;font-size:12px;padding:2px 10px;border-radius:20px;margin-left:8px;vertical-align:middle}}
.desc{{color:#636e72;margin:4px 0}}
.meta{{font-size:13px;color:#b2bec3;margin:4px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;color:#636e72;font-weight:600}}
.mono{{font-family:ui-monospace,Consolas,monospace;font-size:12px}}
pre{{background:#2d3436;color:#dfe6e9;padding:16px;border-radius:8px;overflow-x:auto;font-size:12px;line-height:1.6}}
h2{{font-size:20px;margin-top:32px;border-left:4px solid #6c5ce7;padding-left:12px}}
</style>
</head>
<body>
<header>
<h1>肺炎克雷伯菌（Klebsiella pneumoniae）抗菌载荷设计报告</h1>
<p>后羿 HOUYI · 端到端抗菌载荷设计平台</p>
<p>High-order Omni-target Universal Yielding Antibacterial Injector Intelligence</p>
</header>
<div class="container">
<div class="stats">
  <div class="stat"><div class="num">{n_targets}</div><div class="lbl">设计靶点数</div></div>
  <div class="stat"><div class="num">{n_total}</div><div class="lbl">最终载荷数（Top3×靶点）</div></div>
  <div class="stat"><div class="num">{max(comps)}</div><div class="lbl">最高 composite</div></div>
  <div class="stat"><div class="num">{min(comps)}~{max(comps)}</div><div class="lbl">composite 范围</div></div>
  <div class="stat"><div class="num">{min(lens)}~{max(lens)}</div><div class="lbl">载荷长度范围（aa）</div></div>
</div>

<h2>靶点载荷总览</h2>
<p style="color:#636e72">载荷结构 = Pdp1_NTD（先导肽 59aa）+ linker（GGSGGGGSGG 10aa）+ binder（40-90aa 从头设计），用于装入胞外收缩注射系统（PVC/eCIS）物理穿刺杀菌。</p>
{''.join(target_cards)}

<h2>载荷序列全文（FASTA）</h2>
<pre>{payload_fasta}</pre>

<h2>说明</h2>
<div class="card">
<p><b>靶点选择策略：</b>覆盖三大类——①耐药酶（KPC-2/NDM-1/OXA-48/SHV-1，打击 CRKP 碳青霉烯耐药核心）；②表面抗原（OmpA/OmpC，毒力粘附 + 孔蛋白耐药协同）；③营养摄取（TonB，铁摄取能量中枢）。</p>
<p><b>评分标准：</b>composite = emb_norm×100 + pLL×10（ESM-2 650M 折叠质量代理分数，≥1020 对应 pLDDT≥90）。当前 composite 980-1003，与结核杆菌/鲍曼不动杆菌同水平，需后续 AlphaFold2 验证 + 迭代优化。</p>
<p><b>跳过的靶点：</b>KP_IutA（气杆菌素受体，733aa 大蛋白，RFdiffusion 显存受限，已跳过，建议后续用结构域分割后重新设计）。</p>
</div>
</div>
</body>
</html>"""

out_path = os.path.join(OUT_DIR, "KP_载荷设计报告.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html_doc)

print("报告已生成:", out_path)
print(f"  靶点数: {n_targets}, 载荷数: {n_total}")
print(f"  composite 范围: {min(comps)}~{max(comps)}")
print(f"  载荷长度范围: {min(lens)}~{max(lens)}")
