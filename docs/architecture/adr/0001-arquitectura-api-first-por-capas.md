# ADR-0001: Arquitectura API-First por capas

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (formaliza una decisión vigente desde Fase III)

## Contexto

El producto tiene una UI de escritorio (PyQt6) y necesita, además, exponer sus capacidades a terceros,
móviles y automatizaciones. Mezclar lógica de negocio en la UI o en los endpoints acopla la aplicación y
dificulta la evolución.

## Decisión

Adoptamos una arquitectura **API-First por capas** con dependencia estricta
`REST/GraphQL → servicios → dominio → datos`:

- `src/api/` expone la superficie HTTP (`/api/v1`) y **solo consume servicios** (`src/services/`), nunca
  la BD directamente.
- La lógica de negocio vive en `services/`; la UI (`src/gui/`) y la API solo **orquestan**.
- El acceso a datos se concentra en `src/db/` (pymysql) y las migraciones en `src/database/migraciones/`.

## Consecuencias

- (+) La misma lógica sirve a UI, API, SDK y agentes; testeable por capas.
- (+) La API es sustituible/versionable sin tocar el dominio.
- (−) Exige disciplina: prohibido SQL o reglas de negocio en la GUI/routers.

## Alternativas consideradas

- Lógica en la UI (monolito de escritorio): descartada por acoplamiento e imposibilidad de exponer API.
