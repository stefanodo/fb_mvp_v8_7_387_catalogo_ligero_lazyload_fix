#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(cd "$DIR/.." && pwd)"
exec "$PARENT/MANTENIMIENTO_SYSTEM_MAC.command" "$@"
