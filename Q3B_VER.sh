#!/usr/bin/env bash
# Uso: bash Q3B_VER.sh N     (N = 1..50)
# Muestra el bloque de la pregunta N del workbook, paginado.

set -eu
N="${1:-}"
if [ -z "$N" ]; then
    echo "Uso: bash Q3B_VER.sh N   (N = 1..50)"
    echo ""
    echo "Ejemplos:"
    echo "  bash Q3B_VER.sh 1     # ver bloque de pregunta 1 (SC056-2026)"
    echo "  bash Q3B_VER.sh 13    # ver bloque de pregunta 13 (SC444-2023)"
    echo "  bash Q3B_VER.sh 17    # ver bloque de pregunta 17 (STC16132-2022)"
    exit 1
fi

case "$N" in
    ''|*[!0-9]*) echo "⛔ '$N' no es un número válido"; exit 1 ;;
esac

if [ "$N" -lt 1 ] || [ "$N" -gt 50 ]; then
    echo "⛔ N debe estar entre 1 y 50. Recibido: $N"
    exit 1
fi

WB="Q3B_WORKBOOK.md"
if [ ! -f "$WB" ]; then
    echo "⛔ Falta $WB en el directorio actual"
    exit 1
fi

START=$(grep -n "^## Pregunta ${N} — " "$WB" | head -1 | cut -d: -f1)
if [ -z "$START" ]; then
    echo "⛔ Pregunta ${N} no encontrada en ${WB}"
    exit 1
fi

END=$(awk -v s="$START" 'NR > s && /^## Pregunta [0-9]+/ {print NR; exit}' "$WB")
if [ -z "$END" ]; then
    END=$(wc -l < "$WB")
    END=$((END + 1))
fi

LAST=$((END - 1))

if command -v less >/dev/null 2>&1; then
    sed -n "${START},${LAST}p" "$WB" | less
else
    sed -n "${START},${LAST}p" "$WB"
fi
