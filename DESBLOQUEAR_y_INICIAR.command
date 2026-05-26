#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
chmod +x "$DIR"/*.command 2>/dev/null || true
chmod +x "$DIR"/tools/*.command 2>/dev/null || true
exec /bin/bash "$DIR/INICIAR_F&B_MVP.command"
