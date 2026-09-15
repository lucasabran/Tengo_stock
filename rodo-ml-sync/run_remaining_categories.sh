#!/bin/bash
set -x
declare -A CATS=(
  [696]="mes_infancias"
  [512]="ofertas"
  [495]="celulares"
  [210]="deporte_aire_libre"
  [32]="informatica"
  [35]="climatizacion"
  [33]="telefonia"
  [503]="lg"
)
for id in "${!CATS[@]}"; do
  name="${CATS[$id]}"
  echo "=== Categoria $id ($name) ==="
  python scraper_manual.py --category-id "$id" --out "${name}.xlsx"
  python ml_upload.py --in "${name}.xlsx" --publish-status active
done
