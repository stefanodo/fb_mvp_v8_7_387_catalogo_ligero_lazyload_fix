**Informe: Plan de Acción y Conclusiones**

**Resumen**
- **Proyecto:** System MAC · F&B MVP (repositorio local).
- **Stack actual (observado):** Backend en Python (FastAPI + Jinja2), scripts de migración en `backend/migrate.py`, módulo AI en `backend/app/recipe_ai/`, `requirements.txt` en la raíz, `vercel.json` presente.
- **Objetivo:** Preparar despliegue backend en cloud (Vercel como primer destino), mantener GitHub como SCM, integrar flujo de trabajo en Jira, y crear frontend moderno con Vite + React + Shadcn UI + React Router + MobX.

**Qué hay implementado / observaciones iniciales**
- Código backend FastAPI con múltiples routers (ej. [backend/app/recipe_ai/commit_service.py](backend/app/recipe_ai/commit_service.py)).
- Script de migración: [backend/migrate.py](backend/migrate.py).
- Configuración y docs internos abundantes (AGENTS.md, varios INFORME_CAMBIOS). Ver [VERSION_BUILD.txt](VERSION_BUILD.txt) y [requirements.txt](requirements.txt).

**Recomendación de Stack (resumen)**
- Backend: mantener FastAPI; empaquetar con Docker (imagen con Uvicorn/Gunicorn) para portabilidad.
- Base de datos: Postgres gestionado (Neon, Supabase, RDS). `DATABASE_URL` ya usado en código — aprovecharlo.
- Storage: S3-compatible para uploads (o Vercel Storage / Cloud provider bucket).
- Frontend: Vite + React (+ TypeScript recomendado) + Tailwind + Shadcn UI + React Router + MobX.
- CI/CD: GitHub Actions para lint/tests/build; despliegues automáticos a Vercel (frontend) y a Vercel/Cloud Run/Render (backend) vía Docker/GitHub Actions.
- Observabilidad: Sentry para errores + logs estructurados + métricas básicas (Prometheus/Cloud provider).

**Jira — Flujo de trabajo sugerido**
- Proyecto: utilizar Board Scrum o Kanban según ritmo del equipo.
- Tipos de issue: Epic / Story / Task / Bug / Spike.
- Estados: To Do → In Progress → In Review → QA / Testing → Done.
- Reglas de automatización sugeridas:
  - Al cerrar PR con clave JIRA: mover issue a In Review.
  - Al mergear en `main`: crear Release y mover issue a QA.
  - Etiquetas: `blocking`, `hotfix`, `release`, `ops`.
- Integración: configurar GitHub ↔ Jira (Apps) para vincular commits/PRs con issues.

**GitHub — Convenciones y CI**
- Branching: `main` protegido, `develop` (opcional), `feature/*`, `bugfix/*`, `hotfix/*`.
- PR template: checklist (lint, tests, migraciones, variables env, impacto DB).
- Actions sugeridas:
  - `ci.yml`: install, lint, unit tests (run on PRs).
  - `build-and-deploy-frontend.yml`: build Vite app, deploy to Vercel (via Vercel Git Integration or CLI).
  - `build-and-deploy-backend.yml`: build Docker image, run migrations, deploy to target (Vercel/Cloud Run/Render).

**Despliegue Backend (Vercel como primer destino) — Opciones**
1) POC Rápido (recomendado): crear Dockerfile en `backend/` y usar despliegue por imagen (Vercel soporta despliegues de contenedores). Esto evita reescribir APIs para serverless.
2) Alternativa: adaptar endpoints críticos a funciones serverless si se quiere aprovechar invocación por request (requerirá reestructura).

Pasos POC Docker → Vercel:
 - Añadir `backend/Dockerfile` (multi-stage, instalar deps desde `requirements.txt`, crear usuario no-root, exponer puerto uvicorn).
 - Añadir `vercel.json` o confirmar existente para usar imagen o build step.
 - En Vercel: configurar `DATABASE_URL`, `OPENAI_API_KEY`, `FB_MVP_RUNTIME_DIR` y otros secrets.
 - Configurar healthcheck y readiness probe si el host lo soporta.
 - Ejecutar migraciones al arrancar o por job (`backend/migrate.py` o Alembic).

**Base de datos y migraciones**
- Migraciones: migrar a Alembic si no está (o documentar `backend/migrate.py` como runbook de migración).
- Entorno: crear instancia Postgres gestionada, configurar `DATABASE_URL` en Vercel/entorno.

**Frontend — Scaffolding y librerías**
Pasos iniciales (local/POC):
 - Crear app Vite (recomiendo TypeScript): `npm create vite@latest frontend -- --template react-ts`.
 - Configurar Tailwind CSS.
 - Instalar Shadcn UI (requiere Tailwind + Radix; seguir su guía para Vite). CLI: `npx shadcn@latest init` (ajustar si cambia la herramienta).
 - Router: `npm i react-router-dom` y crear `src/router` con rutas principales.
 - Stores: `npm i mobx mobx-react-lite`, crear `src/stores` y ejemplo `uiStore` / `authStore`.
 - Estructura sugerida: `src/components`, `src/pages`, `src/stores`, `src/services/api.ts`.

**Autenticación**
- Opciones: JWT emitido por backend (login/password) o integración OAuth (provider). Para el frontend, usar `authStore` con MobX y proteger rutas con guards.

**Observabilidad y Operaciones**
- Integrar Sentry (backend + frontend).
- Logs estructurados (JSON) y agregador (Cloud provider / Logflare / Datadog).
- Alertas básicas y runbook de incidencias.

**Tests**
- Unit: `pytest` (backend), `vitest`/`jest` (frontend).
- Integration: scripts que validen endpoints principales.
- E2E: Playwright o Cypress para flujos críticos (login, subida de receta, commit de receta).

**Prioridades y entregables (MVP)**
1. POC despliegue backend en Vercel con Docker + migraciones (1–3 días).
2. Scaffold frontend Vite + Shadcn + routing + ejemplo de integración API (2–4 días).
3. Autenticación básica y stores MobX (1–2 días).
4. CI: lint, tests y deploy automáticos en PR/merge (1–2 días).
5. Observabilidad y runbooks (1–2 días).

**Checklist rápido (archivos clave y acciones inmediatas)**
- Revisar y documentar `backend/migrate.py` — decidir migraciones automáticas o manuales ([backend/migrate.py](backend/migrate.py)).
- Añadir `backend/Dockerfile` (nuevo).
- Crear `frontend/` con Vite + Shadcn.
- Crear `/.github/workflows/ci.yml` y `deploy-*.yml`.
- Configurar Jira project + plantillas (issue, PR to Jira linking).

**Siguientes pasos que puedo ejecutar**
- A: Crear `INFORME_PLAN_DE_ACCION.md` (hecho).
- B: Generar `backend/Dockerfile` de ejemplo y PR.
- C: Scaffolding automático del `frontend/` (Vite + Tailwind + Shadcn) y PR.
- D: Esqueleto de GitHub Actions (CI + deploy) y PR.
- E: Plantillas de issues/PR y guía para configurar Jira ↔ GitHub.

Si quieres, procedo con B y C (creo Dockerfile de backend y scaffolding del frontend) y abro PRs con los cambios propuestos.
