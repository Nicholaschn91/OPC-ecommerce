#!/usr/bin/env bash
# design-plan 后台批处理：独立 profile，与 aistudio MCP 并行不冲突
PY="C:/Users/nicho/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
if [ ! -f "$PY" ]; then PY="C:/Users/nicho/.workbuddy/binaries/python/versions/3.13.12/python.exe"; fi
NODE="C:/Users/nicho/.workbuddy/binaries/node/versions/22.22.2/node.exe"
SKILL="/c/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-design-plan/scripts"
cd "$SKILL"
mkdir -p dp_run
LOG="dp_run/batch1.log"
echo "BATCH1 START $(date)" | tee -a "$LOG"

RECORDS="recvoVJts0pFcW recvoXJjGbNjgZ recvoXJ68f0fWc"

for rid in $RECORDS; do
  echo "===== [$rid] fetch =====" | tee -a "$LOG"
  "$PY" fetch_input.py "$rid" -o "./dp_run/input_$rid.txt" 2>&1 | tee -a "$LOG"

  echo "===== [$rid] design-plan (isolated profile) =====" | tee -a "$LOG"
  "$NODE" aistudio_design_plan.cjs \
    --input  "./dp_run/input_$rid.txt" \
    --out    "./dp_run/design_$rid.md" \
    --shot   "./dp_run/shot_$rid.png" \
    --gen-timeout 300000 2>&1 | tee -a "$LOG"
  rc=$?
  echo "===== [$rid] cli exit=$rc =====" | tee -a "$LOG"

  if [ -f "./dp_run/design_$rid.md" ]; then
    echo "===== [$rid] write 设计方案 -> feishu =====" | tee -a "$LOG"
    "$PY" dp_write_feishu.py "$rid" "./dp_run/design_$rid.md" 2>&1 | tee -a "$LOG"
  else
    echo "===== [$rid] NO OUTPUT MD, skip feishu write =====" | tee -a "$LOG"
  fi
done

echo "BATCH1 DONE $(date)" | tee -a "$LOG"
