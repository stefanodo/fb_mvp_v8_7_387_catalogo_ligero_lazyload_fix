#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(cd "$DIR/.." && pwd)"
exec "$PARENT/CONFIGURAR_IA_OPENAI.command" "$@"
