"""
Migración 0319 — Tráfico exterior / Capture Rate (sensores de conteo de personas). ADITIVA,
idempotente, reversible.

Auditoría previa (sin infraestructura de ingesta de sensores ya existente en el repo — ni tabla, ni
concepto de "tráfico"/"aforo"/"passerby" en ningún sitio): se crea la ÚNICA pieza de esquema nueva
estrictamente necesaria — `tiendas.zona_horaria` (no existía NINGUNA columna de huso horario por
tienda; el resto de la app asume DATETIME naive en hora local del servidor, así que esta columna
permite convertir el `timestamp` que manda cada sensor a la hora LOCAL de SU tienda antes de agregar
en buckets, sin tocar el resto del esquema ni introducir UTC en el resto de la app) y la tabla de
lecturas agregadas `trafico_sensores_buckets` (tráfico exterior/passerby + entradas efectivas, por
tienda y por intervalo de tiempo — 15/60 min).
"""

VERSION = "0319"
DESCRIPCION = "tiendas.zona_horaria + trafico_sensores_buckets (Capture Rate)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Huso horario por tienda (petición explícita: "manejo correcto de zonas horarias según la
    # ubicación de cada tienda"). Por defecto Europe/Madrid — mismo huso que ya asumen implícitamente
    # el resto de DATETIME naive de la app (fiscalidad AEAT, fichajes, etc.).
    cur.execute("ALTER TABLE tiendas ADD COLUMN IF NOT EXISTS zona_horaria VARCHAR(64) "
               "NOT NULL DEFAULT 'Europe/Madrid'")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trafico_sensores_buckets (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)  NOT NULL,
            id_tienda       INT       NOT NULL,
            -- Inicio del bucket en hora LOCAL de la tienda (naive, mismo criterio que el resto del
            -- esquema) — NO en UTC, para que agregue/filtre de forma consistente con `ventas.fecha`.
            bucket_inicio   DATETIME  NOT NULL,
            bucket_minutos  SMALLINT  NOT NULL DEFAULT 15,
            passerby_count  INT       NOT NULL DEFAULT 0,
            entry_count     INT       NOT NULL DEFAULT 0,
            fuente          VARCHAR(80) DEFAULT NULL,
            creado          DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado     DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_trafico_bucket (id_empresa, id_tienda, bucket_inicio, bucket_minutos),
            KEY idx_trafico_rango (id_empresa, id_tienda, bucket_inicio)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS trafico_sensores_buckets")
    cur.execute("ALTER TABLE tiendas DROP COLUMN IF EXISTS zona_horaria")
