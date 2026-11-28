#!/usr/bin/env bash
# Inicializa/actualiza el esquema de base de datos — ÚNICO paso correcto, tanto para
# un despliegue NUEVO (BD vacía) como para aplicar migraciones pendientes en uno ya
# existente. Pensado para ejecutarse DESPUÉS de `docker compose up -d`.
#
# Por qué es el ÚNICO paso necesario (no llamar nada más a mano antes): la migración
# "0001" ya detecta una BD nueva (ausencia de la tabla `usuarios`) y en ese caso invoca
# automáticamente `ensure_schema()` (src/db/conexion.py) — el esquema COMPLETO
# (`clientes`, columnas id_empresa/id_tienda en `movimientos_stock`, etc.), no solo el
# mínimo de `bootstrap_mariadb.sql`. Llamar a `asegurar_base_de_datos()` (o ejecutar
# bootstrap_mariadb.sql) por separado ANTES de este paso crea la tabla `usuarios` por
# su cuenta, lo que hace que el migrador SELLE la "0001" en vez de ejecutarla — dejando
# el esquema a medias. Ver el aviso en `src/database/bootstrap_mariadb.sql` y en el
# docstring de `asegurar_base_de_datos()` (src/db/conexion.py) para el detalle completo.
set -euo pipefail

DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$DIR_SCRIPT/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_DIR/docker-compose.prod.yml}"

docker compose -f "$COMPOSE_FILE" --env-file "$REPO_DIR/.env.production" exec backend python -c "
from src.db import migrador
r = migrador.aplicar_pendientes()
print(r)
if r.get('error'):
    raise SystemExit(1)
"
