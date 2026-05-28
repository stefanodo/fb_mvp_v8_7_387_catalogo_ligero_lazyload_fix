# Informe de la Solución — System MAC · F&B MVP

Fecha: 2026-05-27

## Resumen ejecutivo
Este documento describe la solución técnica propuesta y el estado actual del repositorio para el proyecto System MAC · F&B MVP. Está basado en la inspección de los archivos clave del repositorio (ej. `backend/app/main.py`, `api/index.py`, `backend/migrate.py`, `vercel.json`, `requirements.txt`, `backend/app/recipe_ai/` y `AGENTS.md`) y en las instrucciones iniciales recibidas. El objetivo final es mantener el backend en Python/FastAPI, desplegarlo de forma segura en la nube (Vercel como primer destino posible) y desarrollar un frontend moderno con Vite + React + Shadcn UI + React Router + MobX, manteniendo GitHub como SCM y usando Jira para el flujo de trabajo.

## Estado actual (qué hay en el repositorio)
- `backend/app/main.py`: entrada principal FastAPI que monta routers, templates Jinja2 y archivos estáticos; maneja arranque para SQLite en local y salto a Postgres en producción.
- `api/index.py`: wrapper para Vercel que importa `app` desde `backend/app/main.py` y lo exporta para el runtime de Vercel.
- `vercel.json`: configuración de Vercel. Actualmente configura `@vercel/python` con `api/index.py` como destino y `buildCommand` = `cd backend && python migrate.py`.
- `backend/migrate.py`: script grande e idempotente que crea/ajusta el esquema PostgreSQL para muchas tablas de dominio (recipes, ingredients, pos, tpv, recipe_import_drafts, etc.). Está pensado para inicializar esquema en despliegue.
- `backend/app/recipe_ai/`: módulo AI con `models.py`, `storage_service.py`, `commit_service.py`, `ai_provider_service.py`, `router.py`, etc. `commit_service.py` contiene la lógica para pasar borradores IA a recetas maestras, con guardas (env `RECIPE_AI_ALLOW_COMMIT`).
- `requirements.txt`: dependencias (FastAPI, uvicorn, Jinja2, Pillow, pytesseract, paddleocr, psycopg2-binary, python-dotenv, etc.).
- `AGENTS.md` y `VERSION_BUILD.txt`: documentación del proyecto y convenciones (BUILD_ID, DB local vs prod, variables de entorno, rutas de runtime).

## Observaciones técnicas relevantes
- Arquitectura backend: monolítica por routers en FastAPI con plantillas Jinja2 — la UI del sistema está mayoritariamente server-rendered actualmente.
- Dual-mode DB: en local usa SQLite (ruta runtime fuera del repo); en producción usa PostgreSQL si `DATABASE_URL` está presente (`db_config.py` maneja la conmutación).
- Migraciones: `backend/migrate.py` es un script ad-hoc que realiza muchas `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE` idempotentes. No hay control de versiones de migraciones (Alembic) en el repo.
- IA y OCR: el módulo `recipe_ai` depende de librerías pesadas (paddleocr, tesseract) y de proveedores API (OpenAI/Anthropic). Estas dependencias suelen necesitar binarios/sistema (no solo pip) y pueden no funcionar o llevar a fallos en un entorno serverless sin sistema operativo personalizado.
- Vercel config actual: apunta a `@vercel/python` con `api/index.py`. Esto puede funcionar para endpoints ligeros, pero tiene riesgos: tiempo de arranque, dependencias nativas (OCR), y limits de ejecución en serverless. El `buildCommand` ejecuta `migrate.py` en build time.

## Requisitos y restricciones detectadas
- Mantener compatibilidad con el comportamiento actual: plantillas Jinja2, endpoints existentes y la base de datos con el esquema esperado por la lógica del negocio.
- El módulo OCR y dependencias nativas sugieren preferir un contenedor con sistema operativo controlado o un servicio que permita instalar dependencias nativas (Docker en Cloud Run/Render/Vercel mediante imagen).
- Las rutas legacy y la expectativa de archivos en `~/Documents/F&B_MAC_RUNTIME/` implican documentar y migrar datos runtime a almacenamiento en cloud (S3-compatible) o volumen persistente en el entorno de producción.

## Propuesta de solución (alta fidelidad)

**Arquitectura general**

mermaid
```mermaid
graph LR
  User[Usuario] -->|HTTP| FE[Frontend: Vite + React + Shadcn UI]
  FE -->|REST/JSON| BE[Backend: FastAPI (Docker) / API server]
  BE --> DB[(Postgres gestionado)]
  BE --> S3[(S3-compatible uploads)]
  BE --> IA[OpenAI / Anthropic]
  BE -->|Logs| OBS[Observabilidad: Sentry / Logs]
```

Descripción:
- Frontend: Single Page App (Vite + React + TypeScript), Tailwind + Shadcn UI para componentes, `react-router-dom` para rutas, `mobx` para stores y `src/services/api.ts` para llamadas al backend.
- Backend: conservar FastAPI y la estructura modular; empaquetar en Docker para controlar dependencias nativas (pytesseract, paddleocr). Exponer la app vía Uvicorn/Gunicorn dentro del contenedor.
- DB: Postgres gestionado (Neon, Supabase, RDS). Ejecutar migraciones controladas (ver más abajo).
- Storage: S3-compatible para uploads. Mapear `UPLOADS_DIR`/`FB_MVP_RUNTIME_DIR` a bucket en producción.
- Despliegue: Vercel puede usarse para frontend y, si se desea, para backend mediante contenedor (imagen Docker) o via serverless wrapper `api/index.py` sólo para endpoints ligeros; alternativa preferida para backend con OCR es Render/Cloud Run/Azure Container Apps si Vercel no permite sus binarios.

**Migraciones y esquema**
- Mantener `backend/migrate.py` como runbook de inicialización, pero migrar a Alembic para control de versiones de schema y rollbacks. El script actual crea un esquema de forma idempotente (útil para POC), pero Alembic facilitará evolución.

**CI/CD**
- GitHub Actions:
  - `ci.yml`: linter, tests unitarios (pytest), checks estáticos.
  - `build-and-push-backend.yml`: build Docker image, push a registry privado (GitHub Packages / Docker Hub), desplegar a target (Vercel/Render).
  - `build-and-deploy-frontend.yml`: build Vite app y deploy a Vercel (o a CDN/hosting estático).

**Jira / Flujo de trabajo**
- Flujo sugerido: To Do → In Progress → In Review → QA → Done.
- Vinculación GitHub ↔ Jira (App) para mover issues por eventos de PR/merge y anexar claves de Jira en ramas y PRs.

**Autenticación**
- Mantener endpoints en backend para login (JWT) y sesiones; el frontend guarda token en `authStore` (MobX) y protege rutas mediante guards.

## Consideraciones operativas y de seguridad
- Variables sensibles (OPENAI_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL, RECIPE_AI_ALLOW_COMMIT, etc.) deben guardarse en Secrets del proveedor de despliegue (Vercel Environment Variables o GitHub Secrets + registry).
- No guardar la base de datos `~/Documents/F&B_MAC_RUNTIME/` en el repo; documentar la migración de datos locales a la nueva instancia Postgres antes de producción.
- Si el contenedor incluye OCR (paddleocr/tesseract), incluir en Dockerfile la instalación de librerías de sistema necesarias (libtesseract, paquetes OS para paddle) y probar localmente.

## Riesgos y mitigaciones
- Dependencias nativas (paddleocr, tesseract): riesgo de incompatibilidad en serverless. Mitigación: usar contenedor controlado o externalizar OCR a un microservicio gestionado.
- Tiempo de cold start en serverless: si se mantiene serverless, limitar cargas pesadas a rutas asíncronas procesadas por workers.
- Migraciones manuales: riesgo de desincronización. Mitigación: migrar a Alembic y ejecutar migraciones en CI/CD antes de promover a producción.

## Qué está hecho (resumen, detectado en repo)
- Backend FastAPI modular funcionando: `backend/app/main.py`.
- Wrapper Vercel: `api/index.py` y `vercel.json` con configuración inicial.
- Script de migración exhaustivo: `backend/migrate.py`.
- Módulo AI integrado: `backend/app/recipe_ai/` con storage, commit y router.
- Dependencias declaradas en `requirements.txt`.

## Qué falta o qué se recomienda añadir (alto nivel)
- Adoptar un esquema de migraciones versionado (Alembic).
- Crear Dockerfile para `backend/` que incluya dependencias nativas y un entrypoint robusto (uvicorn/gunicorn).
- Scaffold frontend `frontend/` con Vite + React + TypeScript + Tailwind + Shadcn UI + MobX + React Router.
- GitHub Actions para CI/CD y publicación de artefactos/containers.
- Documentar runbooks: despliegue, rollback, restauración y restauración de DB.
- Plan de observabilidad: integrar Sentry (errors), logs estructurados y métricas básicas.

## Conclusión
El repositorio contiene una base sólida para llevar System MAC a producción: un backend modular en FastAPI, un módulo IA preparado y un script de migración que cubre el esquema necesario. Sin embargo, para un despliegue robusto y reproducible en la nube (especialmente considerando OCR y librerías nativas) es recomendable empaquetar el backend en un contenedor Docker, versionar las migraciones (Alembic), y desplegar con CI/CD desde GitHub. El frontend se beneficiará de un rediseño SPA moderno con Vite + React + Shadcn UI y MobX para stores. Para Vercel como primer destino, se puede probar la configuración serverless actual (wrapper `api/index.py`) como POC, pero el camino menos arriesgado para producción es la imagen Docker o un servicio que permita binarios nativos.

Fin del informe
