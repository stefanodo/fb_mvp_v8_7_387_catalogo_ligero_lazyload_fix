#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(cd "$DIR/.." && pwd)"
exec "$PARENT/PONER_STOCK_PEDIDOS_PRODUCCIONES_A_CERO.command" "$@"
