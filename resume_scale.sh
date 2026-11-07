#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
[ -f "$HOME/.csj_keys" ] && source "$HOME/.csj_keys"
export PYTHONUNBUFFERED=1
mkdir -p "$HOME/tmp"

termux-wake-lock 2>/dev/null || true
tmux kill-session -t scale_a 2>/dev/null || true
rm -f "$HOME/tmp/scale_a.done"
sleep 1

tmux new-session -d -s scale_a '
cd ~/corpus_corte_suprema
source ~/.csj_keys
export PYTHONUNBUFFERED=1
{
for year in 2022 2023 2025 2026; do
  echo ""
  echo "===== $(date +%H:%M:%S) | $year (all salas, 25 docs) ====="
  timeout 900 python3 -u m062_crawler_byid.py \
      --type sentencia --sala all --year $year --max-docs 25 || true
  echo "  (fin $year  $(date +%H:%M:%S))  manifest: $(wc -l < ~/corpus_corte_suprema/manifest.jsonl)"
done
echo ""
echo "===== Incremental rebuild ====="
python3 -u m062_rebuild_incremental.py 2>&1 | tail -15
echo ""
echo "===== DONE ====="
touch ~/tmp/scale_a.done
termux-wake-unlock 2>/dev/null || true
} 2>&1 | tee ~/corpus_corte_suprema/scale_a.log
'
echo "Crawl lanzado: 25 docs/año (equilibrio velocidad/cobertura)"
