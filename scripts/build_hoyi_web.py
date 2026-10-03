#!/usr/bin/env python3
"""生成后羿 HOUYI 增强版交互网页（单文件，数据内嵌）。

把 data/web_data.json 的真实数据注入 HTML 模板，产出可交互的单页 Web 应用。
"""
import json
import os

BASE = r"H:\eazyclaw\saved\MASA3"

def main():
    data = json.load(open(os.path.join(BASE, "data", "web_data.json"), encoding="utf-8"))
    data_json = json.dumps(data, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("/*__DATA__*/null", "const DATA = " + data_json)

    out = os.path.join(BASE, "reports", "HOUYI_交互界面.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"生成完成: {out}")
    print(f"大小: {len(html)} bytes")


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>后羿 HOUYI · 交互式抗菌 Binder 设计平台</title>
<style>
  :root{
    --bg:#0a0f1e; --panel:#12192e; --panel2:#1a2340; --line:#2a3555;
    --txt:#e6ecff; --muted:#8b9ac2; --accent:#5b8cff; --accent2:#00d4aa;
    --gold:#ffc94d; --red:#ff6b6b; --green:#3ddc97; --violet:#b482ff;
  }
  *{box-sizing:border-box; margin:0; padding:0;}
  body{font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    background:linear-gradient(160deg,#0a0f1e,#0c1226); color:var(--txt); line-height:1.7; min-height:100vh;}
  a{color:var(--accent2); text-decoration:none;}

  /* ===== 顶部 ===== */
  header{padding:36px 24px 28px; text-align:center; border-bottom:1px solid var(--line);
    background:radial-gradient(ellipse at 50% -30%,#1e2f66 0%,transparent 55%);}
  header .logo{width:64px;height:64px;margin:0 auto 14px;border-radius:18px;
    background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;
    font-size:28px;font-weight:900;color:#fff;box-shadow:0 6px 24px rgba(91,140,255,.4);}
  header h1{font-size:36px;font-weight:900;letter-spacing:1px;
    background:linear-gradient(90deg,#fff,#9db8ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
  header .cn{font-size:18px;font-weight:700;letter-spacing:6px;color:var(--gold);margin-top:2px;}
  header .full{font-size:12px;color:var(--muted);margin-top:8px;letter-spacing:1px;}
  header .sub{font-size:13px;color:var(--muted);margin-top:8px;}

  .container{max-width:1200px;margin:0 auto;padding:24px;}

  /* ===== 统计卡片 ===== */
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:28px;}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;text-align:center;}
  .stat .n{font-size:26px;font-weight:800;}
  .stat .l{font-size:12px;color:var(--muted);letter-spacing:1px;margin-top:4px;}
  .stat .n.a{color:var(--accent);} .stat .n.g{color:var(--green);} .stat .n.gold{color:var(--gold);} .stat .n.v{color:var(--violet);}

  /* ===== 筛选栏 ===== */
  .toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:20px;}
  .toolbar input[type=text]{flex:1;min-width:200px;background:var(--panel);border:1px solid var(--line);
    border-radius:10px;padding:10px 14px;color:var(--txt);font-size:14px;}
  .toolbar input:focus{outline:none;border-color:var(--accent);}
  .toolbar select{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:10px 14px;color:var(--txt);font-size:14px;cursor:pointer;}

  .filter-tags{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;}
  .ftag{padding:5px 14px;border-radius:16px;font-size:12px;font-weight:600;cursor:pointer;
    border:1px solid var(--line);background:var(--panel);color:var(--muted);transition:.15s;}
  .ftag:hover{border-color:var(--accent);color:var(--txt);}
  .ftag.active{background:var(--accent);color:#fff;border-color:var(--accent);}

  /* ===== 靶点卡片 ===== */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;}
  .tcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;
    cursor:pointer;transition:.15s;position:relative;}
  .tcard:hover{border-color:var(--accent);transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.3);}
  .tcard.sel{border-color:var(--accent2);box-shadow:0 0 0 1px var(--accent2);}
  .tcard .id{font-weight:800;font-size:15px;}
  .tcard .prot{color:var(--muted);font-size:13px;margin-top:2px;}
  .tcard .meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;}
  .pill{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;}
  .pill.tox{background:rgba(255,107,107,.15);color:var(--red);}
  .pill.adh{background:rgba(255,201,77,.15);color:var(--gold);}
  .pill.res{background:rgba(91,140,255,.15);color:var(--accent);}
  .pill.qs{background:rgba(0,212,170,.15);color:var(--accent2);}
  .pill.cw{background:rgba(139,154,194,.15);color:var(--muted);}
  .pill.iron{background:rgba(180,130,255,.15);color:var(--violet);}
  .pill.bio{background:rgba(255,150,80,.15);color:#ff9650;}
  .tcard .foot{display:flex;justify-content:space-between;align-items:center;margin-top:12px;font-size:12px;color:var(--muted);}
  .mic-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;
    background:rgba(0,212,170,.15);color:var(--accent2);}

  /* ===== 详情面板 ===== */
  .detail{margin-top:24px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:24px;display:none;}
  .detail.show{display:block;}
  .detail h2{font-size:20px;margin-bottom:6px;}
  .detail .prot{color:var(--muted);margin-bottom:16px;}
  .detail .kv{display:grid;grid-template-columns:120px 1fr;gap:8px 12px;margin-bottom:16px;}
  .detail .kv .k{color:var(--muted);font-size:13px;}
  .detail .kv .v{font-size:13px;}
  .seq{font-family:"SF Mono",Consolas,monospace;font-size:12px;color:#9fd3ff;
    background:#0a1120;border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-top:8px;word-break:break-all;line-height:1.5;}
  .copy-btn{background:var(--panel2);border:1px solid var(--line);border-radius:8px;color:var(--accent2);
    padding:4px 10px;font-size:11px;cursor:pointer;margin-left:8px;}
  .copy-btn:hover{border-color:var(--accent2);}
  .rationale{margin-top:16px;padding:14px;background:rgba(91,140,255,.05);border-radius:10px;}
  .rationale h3{font-size:13px;color:var(--accent2);margin-bottom:8px;}
  .rationale li{font-size:13px;color:var(--muted);padding:3px 0;list-style:none;}
  .rationale li b{color:var(--txt);}
  .clinical{color:var(--gold);}

  .empty{text-align:center;color:var(--muted);padding:40px;grid-column:1/-1;}
  footer{text-align:center;color:var(--muted);font-size:12px;padding:40px 0;}
  @media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr);}.grid{grid-template-columns:1fr;}}
</style>
</head>
<body>

<header>
  <div class="logo">H</div>
  <h1>HOUYI</h1>
  <div class="cn">后羿</div>
  <div class="full">Holistic Omni-target Universal Yield-Intelligence for de novo Antibacterial binder design</div>
  <div class="sub">自收缩物理穿刺注射 · 杀菌 AI 设计模型 —— 交互式靶点浏览器</div>
</header>

<div class="container">

  <div class="stats">
    <div class="stat"><div class="n a" id="stat-targets">—</div><div class="l">靶点</div></div>
    <div class="stat"><div class="n g" id="stat-binders">—</div><div class="l">Binder 变体</div></div>
    <div class="stat"><div class="n gold" id="stat-classes">—</div><div class="l">机制类别</div></div>
    <div class="stat"><div class="n v" id="stat-mic">—</div><div class="l">有 MIC 数据靶点</div></div>
  </div>

  <div class="toolbar">
    <input type="text" id="search" placeholder="搜索靶点 / 蛋白 / 基因（如 PBP2a、hla、毒素）..." oninput="render()">
    <select id="sort" onchange="render()">
      <option value="id">按名称排序</option>
      <option value="binders">按 Binder 数量排序</option>
      <option value="length">按蛋白长度排序</option>
    </select>
  </div>

  <div class="filter-tags" id="classTags"></div>

  <div class="grid" id="grid"></div>

  <div class="detail" id="detail"></div>

</div>

<footer>
  后羿 HOUYI · 交互式靶点浏览器 · 数据来自 MASA³ 真实管线产出 · Generated 2026-10-01
</footer>

<script>
const DATA = /*__DATA__*/null;

let activeClass = null;   // 当前选中的机制类别（null=全部）
let selected = null;      // 当前选中的靶点 id

// 机制类别 → pill 颜色映射
const CLASS_STYLE = {
  "毒素（成孔毒素）":"tox", "毒素（双组分杀白细胞素）":"tox",
  "粘附素（MSCRAMM）":"adh", "铁摄取（营养免疫逃逸）":"iron",
  "生物膜":"bio", "耐药（β-内酰胺耐药决定因子）":"res", "耐药（甲氧西林耐药辅助因子）":"res",
  "群体感应（Agr 信号）":"qs", "群体感应（转录调控）":"qs",
  "双组分系统（细胞壁稳态）":"cw", "细胞壁合成（脂磷壁酸）":"cw",
  "细胞壁合成（肽聚糖前体）":"cw", "细胞分裂":"cw"
};
function clsStyle(c){ return CLASS_STYLE[c] || "cw"; }

function micOf(tid){
  const m = { "E5_FemABX":"FemABX", "E3_Ddl":"Ddl", "E2_LtaS":"LtaS" };
  return DATA.mic[m[tid]] || null;
}

function init(){
  // 统计
  document.getElementById("stat-targets").textContent = Object.keys(DATA.targets).length;
  document.getElementById("stat-binders").textContent = Object.values(DATA.binder_counts).reduce((a,b)=>a+b,0);
  document.getElementById("stat-classes").textContent = new Set(Object.values(DATA.targets).map(t=>t.mechanism_class)).size;
  document.getElementById("stat-mic").textContent = Object.keys(DATA.mic).length;

  // 机制类别标签
  const classes = [...new Set(Object.values(DATA.targets).map(t=>t.mechanism_class))];
  const tags = document.getElementById("classTags");
  classes.forEach(c => {
    const el = document.createElement("span");
    el.className = "ftag " + clsStyle(c);
    el.textContent = c;
    el.onclick = () => {
      activeClass = (activeClass === c) ? null : c;
      document.querySelectorAll(".ftag").forEach(t=>t.classList.remove("active"));
      if(activeClass) el.classList.add("active");
      render();
    };
    tags.appendChild(el);
  });

  render();
}

function getFiltered(){
  let entries = Object.entries(DATA.targets);
  const q = document.getElementById("search").value.trim().toLowerCase();
  if(q){
    entries = entries.filter(([id,t]) =>
      (id+" "+t.protein+" "+t.gene+" "+t.function+" "+t.mechanism_class).toLowerCase().includes(q));
  }
  if(activeClass){
    entries = entries.filter(([id,t]) => t.mechanism_class === activeClass);
  }
  const sort = document.getElementById("sort").value;
  if(sort === "binders") entries.sort((a,b)=>(DATA.binder_counts[b[0]]||0)-(DATA.binder_counts[a[0]]||0));
  else if(sort === "length") entries.sort((a,b)=>b[1].length_aa-a[1].length_aa);
  else entries.sort((a,b)=>a[0].localeCompare(b[0]));
  return entries;
}

function render(){
  const grid = document.getElementById("grid");
  const entries = getFiltered();
  grid.innerHTML = "";

  if(entries.length === 0){
    grid.innerHTML = '<div class="empty">没有匹配的靶点</div>';
    return;
  }

  entries.forEach(([id,t]) => {
    const card = document.createElement("div");
    card.className = "tcard" + (selected===id ? " sel" : "");
    const mic = micOf(id);
    const nb = DATA.binder_counts[id] || 0;
    card.innerHTML = `
      <div class="id">${id}</div>
      <div class="prot">${t.protein}</div>
      <div class="meta">
        <span class="pill ${clsStyle(t.mechanism_class)}">${t.mechanism_class}</span>
        <span class="pill cw">${t.length_aa} aa</span>
        ${t.pdb ? `<span class="pill qs">PDB ${t.pdb}</span>` : `<span class="pill cw">Chai-1</span>`}
        ${mic ? `<span class="mic-badge">MIC ${mic.mic50}</span>` : ""}
      </div>
      <div class="foot">
        <span>${nb} 条 binder</span>
        <span>基因 ${t.gene}</span>
      </div>
    `;
    card.onclick = () => { selected = id; render(); showDetail(id); };
    grid.appendChild(card);
  });

  if(selected) showDetail(selected);
  else document.getElementById("detail").classList.remove("show");
}

function showDetail(id){
  const t = DATA.targets[id];
  const mic = micOf(id);
  const samples = DATA.binder_samples[id] || [];
  const nb = DATA.binder_counts[id] || 0;
  const d = document.getElementById("detail");
  d.classList.add("show");

  const rationale = t.rationale || {};
  let html = `
    <h2>${id} <span style="font-size:14px;color:var(--muted)">· ${t.protein}</span></h2>
    <div class="prot">基因 <b style="color:var(--accent2)">${t.gene}</b> · ${t.mechanism_class} · ${t.length_aa} aa</div>
    <div class="kv">
      <div class="k">功能</div><div class="v">${t.function}</div>
      <div class="k">设计策略</div><div class="v">${t.design_strategy}</div>
      <div class="k">结构来源</div><div class="v">${t.pdb ? "已知 PDB "+t.pdb : "Chai-1 从头预测"}</div>
      <div class="k">湿实验状态</div><div class="v">${t.wetlab_status || "—"}</div>
      ${mic ? `<div class="k">MIC₅₀</div><div class="v" style="color:var(--accent2);font-weight:700">${mic.mic50} μg/mL（MBC ${mic.mbc}）</div>` : ""}
    </div>
    <div class="rationale">
      <h3>为什么是好靶点（科学论证）</h3>
      ${rationale.virulence_relevance ? `<li>🔬 <b>毒力相关性：</b>${rationale.virulence_relevance}</li>` : ""}
      ${rationale.conservation ? `<li>🧬 <b>保守性：</b>${rationale.conservation}</li>` : ""}
      ${rationale.host_homology !== undefined ? `<li>🧍 <b>宿主同源：</b>${rationale.host_homology ? "有" : "无（降低脱靶风险）"}</li>` : ""}
      ${rationale.clinical_evidence ? `<li class="clinical">💊 <b>临床证据：</b>${rationale.clinical_evidence}</li>` : ""}
    </div>
    <div class="rationale" style="margin-top:12px">
      <h3>Top Binder 序列示例（共 ${nb} 条，展示前 ${samples.length} 条）</h3>
      ${samples.map(s => `
        <div style="margin-top:10px">
          <span style="font-size:12px;color:var(--muted)">${s.id} · ${s.len} aa</span>
          <button class="copy-btn" onclick="copySeq('${s.seq}')">复制</button>
          <div class="seq">${s.seq}</div>
        </div>
      `).join("")}
    </div>
  `;
  d.innerHTML = html;
}

function copySeq(seq){
  navigator.clipboard.writeText(seq).then(()=>{
    alert("序列已复制到剪贴板");
  }).catch(()=>{
    // fallback
    const ta = document.createElement("textarea");
    ta.value = seq; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); document.body.removeChild(ta);
    alert("序列已复制");
  });
}

init();
</script>
</body>
</html>
'''

if __name__ == "__main__":
    main()
