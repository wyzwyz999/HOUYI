#!/usr/bin/env python3
"""从 payloads.json 提取 27 条 binder 单链序列为 FASTA。"""
import json

BASE = r"H:\eazyclaw\saved\MASA3\output data TB\1_最终结果"
payloads = json.load(open(BASE + r"\payloads.json", encoding='utf-8'))

lines = []
for p in payloads:
    lines.append(f">{p['binder_id']}")
    lines.append(p["binder_sequence"])

out = BASE + r"\binder_27.fasta"
with open(out, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines) + "\n")

print(f"已生成 {len(payloads)} 条 binder FASTA ->", out)
