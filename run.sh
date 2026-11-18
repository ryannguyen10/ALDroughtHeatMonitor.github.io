#!/bin/bash
# Runs both notebooks inside the Azure Container Instance.
# Files come from the mounted file share at /mnt/s2s.
set -e

mkdir -p /work /mnt/s2s/runs
cp /mnt/s2s/*.ipynb /mnt/s2s/*.py /mnt/s2s/map_template.html /work/
cd /work

pip install --quiet papermill ipykernel

STAMP=$(date +%Y-%m-%d_%H%M)
for T in sm20 sm100; do
    echo "=== Running $T ==="
    papermill "Alabama_County_s2s_${T}.ipynb" "/mnt/s2s/runs/${T}_${STAMP}.ipynb" --cwd /work
done
echo "=== Done ==="
