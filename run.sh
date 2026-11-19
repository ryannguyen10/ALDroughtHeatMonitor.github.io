#!/bin/bash
# Runs both notebooks inside the Azure Container Instance.
# Files come from the mounted file share at /mnt/s2s.
set -e

mkdir -p /work /mnt/s2s/runs
cp /mnt/s2s/*.ipynb /mnt/s2s/*.py /mnt/s2s/map_template.html /work/
cd /work   # notebooks run with --cwd /mnt/s2s so the calibration library and outputs persist on the share

pip install --quiet papermill ipykernel

# Weekly update: newest Monday forecast, its single-date test and report, web pages.
# Set S2S_RUN_MODE=full instead to rebuild the seasonal calibration library.
export S2S_RUN_MODE="${S2S_RUN_MODE:-daily}"
export S2S_WEB_DIR="${S2S_WEB_DIR:-/mnt/s2s/alabama_s2s_web}"
mkdir -p "$S2S_WEB_DIR"

STAMP=$(date +%Y-%m-%d_%H%M)
for T in sm20 sm100; do
    echo "=== Running $T ==="
    papermill "Alabama_County_s2s_${T}.ipynb" "/mnt/s2s/runs/${T}_${STAMP}.ipynb" --cwd /mnt/s2s
done
echo "=== Done ==="
