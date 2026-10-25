#!/usr/bin/env bash
# 排队：等当前 pipeline 结束后，自动启动指定菌株
set -uo pipefail
cd /root/autodl-tmp/HOUYI_git || exit 1
source scripts/houyi_env.sh

SP="${1:?用法: queue_species.sh \"菌名\"}"
QLOG="logs/queue.log"
mkdir -p logs

ts() { date '+%Y-%m-%d %H:%M:%S'; }

{
  echo "[$(ts)] 排队任务: $SP"
  echo "[$(ts)] 等待当前 pipeline 结束..."
} >> "$QLOG"

# 等所有 pipeline 进程退出
while pgrep -f "scripts/pipeline.py" > /dev/null 2>&1; do
  sleep 60
done

# 给 GPU / 文件写入留出收尾时间
sleep 120

RUNLOG="logs/${SP// /_}_$(date +%Y%m%d_%H%M%S).log"
echo "[$(ts)] 队列开始: $SP（日志 $RUNLOG）" >> "$QLOG"

nohup bash scripts/run_species.sh "$SP" > "$RUNLOG" 2>&1 &
PID=$!
echo "[$(ts)] 已启动 PID=$PID  log=$RUNLOG" >> "$QLOG"

wait $PID
RC=$?
echo "[$(ts)] 结束: $SP  exit=$RC" >> "$QLOG"

# 自动打包
if [ -f scripts/pack_result.sh ]; then
  bash scripts/pack_result.sh "$SP" >> "$QLOG" 2>&1 || true
  echo "[$(ts)] 已尝试打包（详见 $QLOG）" >> "$QLOG"
fi
