#!/bin/bash
pkill -f "uvicorn.*127.0.0.1:8000" 2>/dev/null
pkill -f "uvicorn.*0.0.0.0:8000" 2>/dev/null
echo "Servidor F&B detenido."
read -n 1 -s -r -p "Pulsa una tecla para cerrar..."
echo
