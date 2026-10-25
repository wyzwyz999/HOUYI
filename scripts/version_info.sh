#!/usr/bin/env bash
# HOUYI 版本指纹：在任何实例上执行，输出可直接跨机器对比
# 用法: bash scripts/version_info.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR" || exit 1

echo "===== HOUYI version fingerprint ====="
echo "time        : $(date '+%Y-%m-%d %H:%M:%S')"
echo "host        : $(hostname)"
echo "code_dir    : $DIR"

# git（如果目录是仓库）
if [ -d .git ]; then
    echo "git_branch  : $(git branch --show-current 2>/dev/null)"
    echo "git_commit  : $(git log --oneline -1 2>/dev/null)"
    echo "git_dirty   : $(git status --porcelain 2>/dev/null | wc -l) 个未提交文件"
else
    echo "git_branch  : (不是 git 仓库)"
    echo "git_commit  : (无)"
fi

# 关键文件的指纹
echo
echo "--- 关键文件 md5 ---"
for f in \
    scripts/pipeline.py \
    scripts/run_species.sh \
    scripts/batch_species.sh \
    scripts/pack_result.sh \
    scripts/hoyi/__init__.py \
    scripts/hoyi/ring7.py \
    scripts/hoyi/ring10.py \
    scripts/hoyi/auto_target_discovery.py \
    scripts/hoyi/interpro_receptor_rules.py \
    data/antigens/fiber_target_knowledge_base.json
do
    if [ -f "$f" ]; then
        printf "%-52s %s  %s\n" "$f" "$(md5sum "$f" | cut -d' ' -f1)" "$(date -r "$f" '+%m-%d %H:%M')"
    else
        printf "%-52s %s\n" "$f" "[MISSING]"
    fi
done

# 功能标记
echo
echo "--- 功能标记（>0 表示有）---"
mark() {
    local label="$1" pattern="$2" file="$3"
    if [ -f "$file" ]; then
        local n
        n=$(grep -c "$pattern" "$file" 2>/dev/null || true)
        printf "%-34s %s\n" "$label" "${n:-0}"
    else
        printf "%-34s %s\n" "$label" "[no file]"
    fi
}
mark "run_species: 自动降级"      "AUTO_REVIEW_FALLBACK"      scripts/run_species.sh
mark "run_species: 参数透传"      '"\$@"'                     scripts/run_species.sh
mark "pipeline: allow-unreviewed" "allow-unreviewed"          scripts/pipeline.py
mark "ring7: 质量分层"            "quality_tier"              scripts/hoyi/ring7.py
mark "ring7: 家族优先"            "family_match"              scripts/hoyi/ring7.py
mark "ring7: InterPro"            "interpro_receptor_rules"   scripts/hoyi/ring7.py
mark "pipeline: 容错/总结"        "run_summary"               scripts/hoyi/__init__.py
mark "pack_result 存在"           "pack_result"               scripts/pack_result.sh

# 运行环境
echo
echo "--- 运行环境 ---"
PYBIN="${HOUYI_PYTHON:-/root/miniconda3/bin/python}"
if [ -x "$PYBIN" ]; then
    "$PYBIN" - <<'PY' 2>/dev/null || true
import sys
print("python      :", sys.version.split()[0])
try:
    import torch
    print("torch       :", torch.__version__, "| cuda:", torch.cuda.is_available(),
          "|", (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-"))
except Exception as e:
    print("torch       : (不可用)", e)
PY
else
    echo "python      : $PYBIN 不存在"
fi

# 结果规模
echo
echo "--- 结果 ---"
if [ -d results/by_organism ]; then
    echo "species_dirs: $(find results/by_organism -mindepth 1 -maxdepth 1 -type d | wc -l)"
    echo "run_summary : $(find results/by_organism -name run_summary.json | wc -l) 个"
else
    echo "species_dirs: 0"
fi
echo "====================================="
