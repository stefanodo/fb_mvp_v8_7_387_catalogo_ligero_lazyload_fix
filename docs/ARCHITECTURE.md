# Arquitectura y guía de despliegue

Este documento resume la arquitectura propuesta para System MAC · F&B MVP y aporta ejemplos de despliegue local (Docker Compose) y de Dockerfile para producción.

## Componentes principales
- Frontend: Vite + React (+ TypeScript recomendado) con Tailwind + Shadcn UI. Deploy: Vercel o CDN.
- Backend: FastAPI empaquetado en Docker (imagen reproducible). Exponer mediante Uvicorn/Gunicorn.
- Base de datos: PostgreSQL gestionado (Neon / Supabase / RDS).
- Almacenamiento: S3-compatible para archivos/uploads.
- OCR/IA: módulo `recipe_ai` que depende de tesseract/paddleocr; se recomienda ejecutar dentro del mismo contenedor o, mejor, en un worker/servicio separado si la carga es alta.
- Observabilidad: Sentry para errores, logs estructurados y métricas.

## Diagrama lógico

```mermaid
graph LR
  User[Usuario] -->|HTTP(S)| FE(Vite + React)
  FE -->|REST/JSON| API(FastAPI - Docker)
  API --> DB[(Postgres gestionado)]
  API --> S3[Almacenamiento S3]
  API --> IA[Servicios IA (OpenAI/Anthropic)]
  API --> OCR[OCR Worker (paddleocr/tesseract)]
  OCR --> S3
  API -->|logs| SENTRY[Sentry]
  API -->|metrics| MONITORING[Prometheus/CloudMetrics]
```

## Dockerfile (ubicado en `backend/Dockerfile`)

- El `Dockerfile` incluido en el repo está pensado para:
  - Incluir dependencias de sistema necesarias para OCR (`tesseract`, `poppler`, `ffmpeg`, etc.).
  - Instalar las dependencias Python desde `requirements.txt`.
  - Ejecutar `backend/migrate.py` en el arrancado si está presente `DATABASE_URL`.
  - Arrancar `uvicorn` para servir la aplicación.

Construcción desde la raíz del repo (ejemplo):

```bash
docker build -f backend/Dockerfile -t systemmac/backend:latest .
docker run -e DATABASE_URL="postgresql://user:pass@db:5432/fb_mvp" -p 8000:8000 systemmac/backend:latest
```

## Docker Compose (ejemplo para desarrollo local)

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

  redis:
    image: redis:7

volumes:
  pgdata:

```

## Recomendaciones de despliegue
- Para POC rápido: probar el `api/index.py` + `vercel.json` actual en Vercel si no se requieren dependencias nativas pesadas.
- Para producción con OCR: desplegar la imagen Docker en un servicio que permita contenedores (Render, Cloud Run, ECS) y configurar variables de entorno y secrets.
- Separar OCR/IA en workers si el tráfico es elevado; usar cola (Redis + RQ/Celery) para procesado asíncrono.

## CI/CD sugerido (resumen)
- Frontend → Deploy automático en Vercel desde `main`.
- Backend → GitHub Actions que construya la imagen, ejecute tests y despliegue (o push a registry + despliegue en host). Ejecutar migraciones controladas en pipeline.

## Notas operativas
- No exponer `~/Documents/F&B_MAC_RUNTIME/` tal cual en producción; usar bucket/volume gestionado.
- Mantener secretos fuera del repo (GitHub Secrets / Vercel Env / Provider Secrets).

---
Archivo: `docs/ARCHITECTURE.md` — creado automáticamente como plantilla de referencia.
