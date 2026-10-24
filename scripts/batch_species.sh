#!/usr/bin/env bash
# HOUYI 批量跑物种：单个失败不中断；靶点类失败自动用 --allow-unreviewed 重试一次。
#
# 用法:
#   bash scripts/batch_species.sh species.txt
#
# species.txt 每行一个菌名，# 后为注释，空行忽略。
# 支持写别名改写（左边只做记录，右边才是真正传给管线的 UniProt 标准名）：
#   Adherent-invasive Escherichia coli => Escherichia coli
set -uo pipefail

cd /root/autodl-tmp/HOUYI_git

LIST="${1:-}"
if [ -z "$LIST" ] || [ ! -f "$LIST" ]; then
    echo "用法: bash scripts/batch_species.sh species.txt"
    exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="logs/batch_${STAMP}"
mkdir -p "$OUTDIR"

OK_LIST="$OUTDIR/ok.txt"
FAIL_LIST="$OUTDIR/fail.txt"
: > "$OK_LIST"
: > "$FAIL_LIST"

LAST_LOG=""
safe_name() { echo "$1" | tr ' /:' '___'; }

run_one() {
    local label="$1"; shift
    local org="$1"; shift
    LAST_LOG="$OUTDIR/$(safe_name "$label").log"
    echo "[$(date '+%H:%M:%S')] RUN   $label (organism=$org) $*"
    bash scripts/run_species.sh "$org" "$@" >>"$LAST_LOG" 2>&1
}

is_target_failure() {
    # 只有"靶点/网络"类失败才值得重跑，否则只是浪费一倍机时。
    grep -qE "UNIPROT_" "$LAST_LOG" 2>/dev/null && return 0
    grep -qE "环1 无可用靶点" "$LAST_LOG" 2>/dev/null || return 1
    # 菌名根本不合法（reviewed 与 TrEMBL 都是 0 条）时，重跑也救不了
    grep -qE "均为 0 条|完全查不到记录" "$LAST_LOG" 2>/dev/null && return 1
    return 0
}

# 端到端容错版管线即使某环失败也返回 exit 0（会写 run_summary.json），
# 所以批量判断成功/失败必须看日志里的"运行总结"，不能只看退出码。
run_status() {
    if grep -q "运行总结: COMPLETED" "$LAST_LOG" 2>/dev/null; then
        echo "COMPLETED"
    elif grep -q "运行总结: PARTIAL" "$LAST_LOG" 2>/dev/null; then
        echo "PARTIAL"
    elif grep -q "运行总结: FAILED" "$LAST_LOG" 2>/dev/null; then
        echo "FAILED"
    elif grep -q "\[FATAL\]" "$LAST_LOG" 2>/dev/null; then
        echo "FAILED"
    else
        echo "UNKNOWN"
    fi
}

while IFS= read -r raw; do
    sp="$(echo "$raw" | sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [ -z "$sp" ] && continue

    if [[ "$sp" == *"=>"* ]]; then
        org="$(echo "${sp#*=>}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    else
        org="$sp"
    fi

    run_one "$sp" "$org" || true
    st="$(run_status)"

    if [ "$st" = "COMPLETED" ]; then
        echo "OK           $sp" | tee -a "$OK_LIST"
        continue
    fi

    if [ "$st" = "PARTIAL" ]; then
        # 跑完了但有环节失败/被跳过：仍算产出，但单独列出便于复核
        echo "OK(PARTIAL)  $sp" | tee -a "$OK_LIST"
        echo "PARTIAL      $sp" >> "$OUTDIR/partial.txt"
        continue
    fi

    if is_target_failure; then
        echo "[$(date '+%H:%M:%S')] RETRY $sp --allow-unreviewed（TrEMBL 兜底）"
        run_one "$sp" "$org" --allow-unreviewed || true
        st2="$(run_status)"
        if [ "$st2" = "COMPLETED" ] || [ "$st2" = "PARTIAL" ]; then
            echo "OK($st2)   $sp" | tee -a "$OK_LIST"
            [ "$st2" = "PARTIAL" ] && echo "PARTIAL      $sp" >> "$OUTDIR/partial.txt"
            continue
        fi
    else
        echo "[$(date '+%H:%M:%S')] SKIP-RETRY $sp（非靶点类失败，见日志）"
    fi

    echo "FAIL($st)   $sp" | tee -a "$FAIL_LIST"
done < "$LIST"

echo
echo "===== 汇总 ====="
echo "成功: $(wc -l < "$OK_LIST")  失败: $(wc -l < "$FAIL_LIST")"
if [ -s "$OUTDIR/partial.txt" ]; then
    echo "其中部分完成（有环节失败/被跳过，见 run_summary.json）:"
    cat "$OUTDIR/partial.txt"
fi
echo "日志目录: $OUTDIR"
if [ -s "$FAIL_LIST" ]; then
    echo
    echo "失败物种（原因见 $OUTDIR/<物种>.log 末尾）:"
    cat "$FAIL_LIST"
    echo
    echo "原因归类:"
    grep -h "环1 无可用靶点\|UNIPROT_\|No such file\|Traceback" "$OUTDIR"/*.log 2>/dev/null \
        | sed -e 's/^[[:space:]]*//' | sort | uniq -c | sort -rn | head -20
fi
