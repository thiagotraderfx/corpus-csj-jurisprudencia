#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "═══ $(date '+%H:%M:%S') ═══"

# Proceso
if pgrep -f crawl_500.py > /dev/null; then
    P=$(pgrep -f crawl_500.py | head -1)
    echo "Proceso: ✓ PID $P ($(ps -p $P -o etime= 2>/dev/null | tr -d ' ') transcurrido)"
else
    echo "Proceso: ✗ NO CORRIENDO"
fi

# Checkpoint
if [ -f crawl_500.checkpoint.json ]; then
    python3 -c "
import json
from pathlib import Path
s = json.loads(Path('crawl_500.checkpoint.json').read_text())
cells = s.get('cells', {})
done = sum(c.get('crawled', 0) for c in cells.values())
ok = sum(1 for c in cells.values() if c.get('status') == 'ok')
fail = sum(1 for c in cells.values() if str(c.get('status', '')).startswith('fail'))
target = 329
pct = 100 * done / target if target else 0
print('Progreso: %d/329 (%.1f%%) · %d celdas OK · %d fallos' % (done, pct, ok, fail))
for k, v in sorted(cells.items()):
    mark = '✓' if v.get('status') == 'ok' else '✗' if 'fail' in str(v.get('status')) else '…'
    print('  %s %-20s %3d  %s' % (mark, k, v.get('crawled', 0), v.get('status', '?')))
"
else
    echo "Checkpoint: (aún no creado — primera celda en progreso)"
fi

# Manifest
echo "Manifest: $(wc -l < manifest.jsonl) docs · Disco: $(df -h ~ | tail -1 | awk '{print $4}') libres"

# Último evento
echo "Último evento:"
tail -1 crawl_500.log 2>/dev/null | python3 -c "
import json, sys
line = sys.stdin.read().strip()
if line:
    try:
        e = json.loads(line)
        print('  [%s] %s' % (e.get('event'), e.get('ts', '')[:19]))
    except: pass
"
