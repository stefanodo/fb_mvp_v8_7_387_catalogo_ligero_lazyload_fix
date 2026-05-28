# Guía de Implementación — Plantillas y Diagrama

Este documento reúne las plantillas y diagramas necesarios para implantar System MAC · F&B MVP. Está pensado como referencia técnica (solo `.md`): incluye ejemplos de `Dockerfile`, `entrypoint`, `docker-compose`, y un diagrama Mermaid que explica la arquitectura propuesta.

---

## 1. Resumen rápido
- Backend: FastAPI modular (ya presente en `backend/app/main.py`).
- Frontend: SPA propuesta con Vite + React + TypeScript + Tailwind + Shadcn UI + React Router + MobX.
- DB: PostgreSQL gestionado en producción; SQLite local para desarrollo.
- Storage: S3-compatible para uploads.
- OCR/IA: `recipe_ai` requiere `tesseract` / `paddleocr` y dependencias nativas — empaquetar en contenedor.

## 2. Variables de entorno críticas
- `DATABASE_URL` — Postgres connection string (production).
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — proveedores IA.
- `FB_MVP_RUNTIME_DIR` — directorio runtime uploads (mapear a S3/volume en prod).
- `RECIPE_AI_ALLOW_COMMIT` — habilita conversión borrador→receta (usar con cuidado).
- `PORT` — puerto del contenedor (por defecto 8000).

---

## 3. Dockerfile (plantilla — ejemplo)
Incluye dependencias nativas necesarias para OCR y procesamiento de imágenes.

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       ca-certificates \
       tesseract-ocr \
       libtesseract-dev \
       libleptonica-dev \
       poppler-utils \
       ffmpeg \
       libgl1 \
       libglib2.0-0 \
       libsm6 \
       libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend
ENV PYTHONPATH=/app/backend

RUN useradd -m appuser || true \
    && chown -R appuser:appuser /app

USER appuser

COPY backend/entrypoint.sh /app/backend/entrypoint.sh
RUN chmod +x /app/backend/entrypoint.sh

EXPOSE 8000
CMD ["/app/backend/entrypoint.sh"]
```

> Nota: en entornos con restricciones a binarios (serverless) puede ser necesario desplegar en un servicio que acepte imágenes Docker (Cloud Run, Render, ECS, etc.).

---

## 4. Entrypoint sugerido (ejemplo)
Este script ejecuta migraciones opcionales (si `DATABASE_URL` existe) y arranca Uvicorn.

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] starting..."

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] DATABASE_URL detected — running migrate.py"
  python /app/backend/migrate.py || echo "[entrypoint] migrate.py exited non-zero (continuing)"
fi

echo "[entrypoint] starting uvicorn"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
```

---

## 5. Docker Compose (desarrollo — ejemplo)

```yaml
version: '3.8'
services:
  web:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/fb_mvp
      - FB_MVP_RUNTIME_DIR=/data
    volumes:
      - ./backend:/app/backend
      - ./uploads:/data/uploads

  db:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: fb_mvp
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## 6. Diagrama de arquitectura (Mermaid)

```mermaid
graph LR
  User[Usuario] -->|HTTP(S)| FE[Vite + React SPA]
  FE -->|REST/JSON| API[FastAPI (contenedor)]
  API --> DB[(Postgres gestionado)]
  API --> S3[(S3 uploads)]
  API --> IA[OpenAI / Anthropic]
  API --> OCR[OCR Worker (tesseract/paddleocr)]
  OCR --> S3
  API -->|logs| SENTRY[Sentry]
  API -->|metrics| MONITORING[Prometheus/Cloud Metrics]
```

---

## 7. CI/CD — ejemplos y recomendaciones
- Separar pipelines: `ci.yml` para linters/tests; `deploy-backend.yml` para build/push/deploy; `deploy-frontend.yml` para build y deploy del frontend.

Ejemplo (resumen) de `deploy-backend.yml` (construir y push a registry):

```yaml
name: Build and push backend
on:
  push:
    branches: [ main ]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v2
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      - name: Login to registry
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: backend/Dockerfile
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
```

> Nota: el despliegue final puede integrar la imagen en el servicio seleccionado (Render, Cloud Run). Para Vercel, la integración suele ser más sencilla para el frontend; para backend con binarios nativos preferir un host que soporte contenedores.

---

## 8. Frontend — pasos de scaffolding (comandos)

```bash
# Crear proyecto Vite + React + TypeScript
npm create vite@latest frontend -- --template react-ts
cd frontend
# Instalar dependencias
npm install
# Tailwind
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
# Shadcn UI (sigue su guía oficial)
npx shadcn@latest init
# Router + MobX
npm install react-router-dom mobx mobx-react-lite
```

Estructura recomendada del frontend:
- `src/components` — componentes UI.
- `src/pages` — vistas/ rutas.
- `src/stores` — `mobx` stores (authStore, uiStore, dataStore).
- `src/services/api.ts` — cliente HTTP (fetch/axios) con baseURL apuntando al backend.

---

## 9. Migraciones de BD
- Recomendación: migrar de script ad-hoc a Alembic (control de versiones). Pasos básicos:
  1. `pip install alembic`
  2. `alembic init alembic` en `backend/`.
  3. Ajustar `alembic/env.py` para usar la URL de `DATABASE_URL` o crear un engine a partir de la configuración existente.
  4. Generar revisiones: `alembic revision --autogenerate -m "Initial schema"`.
  5. Aplicar: `alembic upgrade head`.

El script `backend/migrate.py` puede mantenerse como runbook inicial, pero Alembic facilita cambios incrementales y rollbacks.

---

## 10. Checklist mínimo para MVP
- [ ] Decidir host backend (Vercel con container / Render / Cloud Run).
- [ ] Proteger `main` y establecer flujo de ramas (`feature/*`, `hotfix/*`).
- [ ] Configurar GitHub Actions para CI.
- [ ] Preparar imagen Docker y probar localmente.
- [ ] Provisionar Postgres gestionado y pasar datos si aplica.
- [ ] Crear scaffold frontend con Shadcn UI y ejemplo de integración de API.
- [ ] Integrar observabilidad (Sentry) y monitorización básica.

---

## 11. Próximos pasos (si quieres que los ejecute)
- Generar este contenido como un Issue con checklist en GitHub.
- Crear PR con `Dockerfile` y `entrypoint` (si decides permitir archivos no-MD).
- Scaffold del frontend (si quieres que lo genere en el repo).

Si quieres, genero ahora un archivo README corto con los pasos de prueba local en `.md` o convierto partes de esta guía en issues/plantillas para Jira.
