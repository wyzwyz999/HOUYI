#!/usr/bin/env bash
# 跑完一株菌后：打印质量摘要 + 自动打包结果
#
# 用法:
#   bash scripts/pack_result.sh "Mycobacterium simiae"
#   bash scripts/pack_result.sh "Mycobacterium simiae" /root/autodl-tmp   # 指定输出目录
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source scripts/houyi_env.sh

SP="${1:?用法: bash scripts/pack_result.sh \"菌名\" [输出目录]}"
OUT_DIR="${2:-/root/autodl-tmp}"

SLUG=$(/root/miniconda3/bin/python - "$SP" <<'PY'
import sys
sys.path.insert(0, "scripts")
from hoyi.config import Config
c = Config()
c.set_organism(sys.argv[1])
print(c.organism_slug)
PY
)

D="results/by_organism/$SLUG"
if [ ! -d "$D" ]; then
    echo "找不到结果目录: $D"
    echo "提示: 先跑 bash scripts/run_species.sh \"$SP\""
    exit 1
fi

echo "=== 质量摘要: $SP ($SLUG) ==="
/root/miniconda3/bin/python - "$D" <<'PY'
import json
import os
import sys

d = sys.argv[1]

s = os.path.join(d, "run_summary.json")
if os.path.exists(s):
    x = json.load(open(s, encoding="utf-8"))
    print("overall_status :", x.get("overall_status"))
    bad = x.get("blocked_or_failed") or []
    print("blocked/failed :", bad if bad else "无")
    q = x.get("quality") or {}
    print("fiber_tier     :", q.get("fiber_tier"), "| counts:", q.get("fiber_tier_counts"))
    print("nanosyringes   :", q.get("nanosyringes"),
          "| complete:", q.get("nanosyringes_complete"),
          "| complete_strict:", q.get("nanosyringes_complete_strict"))
else:
    print("(无 run_summary.json：可能是 v2 之前跑的结果)")

j = os.path.join(d, "ring7_fiber_targets.json")
if os.path.exists(j):
    r7 = json.load(open(j, encoding="utf-8"))
    if r7:
        print("ring7 #1       :", r7[0].get("fiber_target"),
              "|", (r7[0].get("protein") or "")[:48],
              "| tier:", r7[0].get("quality_tier"))
PY

TS=$(date +%Y%m%d)
TAR="$OUT_DIR/${SLUG}_results_${TS}.tar.gz"
echo
echo "=== 打包 ==="
tar -czf "$TAR" -C results/by_organism "$SLUG" || {
    echo "打包失败（检查磁盘空间: df -h /root/autodl-tmp）"
    exit 1
}
SRC=$(du -sh "$D" | cut -f1)
SIZE=$(du -h "$TAR" | cut -f1)
N=$(tar -tzf "$TAR" | wc -l)
echo "原始大小: $SRC   压缩包: $SIZE   条目数: $N"
echo "压缩包路径: $TAR"
echo
echo "下载方式: AutoDL 控制台 → 文件存储 → $OUT_DIR"
