#!/bin/bash
set -e

SPECIES="${1:?请提供菌种目录名}"

cd /root/autodl-tmp/HOUYI_git

PY=/root/miniconda3/bin/python

"$PY" tools/audit_houyi_results.py --species "$SPECIES"
"$PY" tools/classify_houyi_status.py --species "$SPECIES"
"$PY" tools/export_houyi_audit.py --species "$SPECIES"

echo "HOUYI_POSTRUN_OK"
