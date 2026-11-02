"""
Migración 0325 — Gestión de Redes Sociales Corporativas (petición explícita, módulo nuevo completo:
bandeja omnicanal, calendario de contenidos, analítica cruzada, monitorización de reputación con
escalado automático a Incidencias). ADITIVA, idempotente, reversible.

Auditoría previa (ver conversación): NO existe ninguna integración de Instagram/Facebook Shopping en
el repo (solo TikTok Shop, un conector de CATÁLOGO/pedidos sin relación con mensajería) — así que
todo este módulo es motor nuevo, salvo lo que SÍ se reutiliza tal cual: `utils.cripto`/
`secret_manager` para cifrar tokens OAuth (mismo patrón que `rrhh_empleados.iban`/
`tesoreria.cuentas_bancarias`), `db.documentos` para adjuntos, `services.eventos` (catálogo abierto,
sin registro previo necesario) y la taxonomía de errores de integración ya existente
(`services.marketplace.integraciones_comerciales.motor.errores`).

También extiende `incidencias_internas` (migr. 0323): el escalado automático de reputación necesita
crear tickets SIN un empleado solicitante humano — se añade `origen` y se relaja
`id_usuario_solicitante` a NULL-able (el código de negocio sigue exigiéndolo para tickets de origen
'manual', ver `services.incidencias_internas.tickets`).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0325"
DESCRIPCION = "Redes Sociales Corporativas (cuentas/bandeja/calendario/métricas/reputación) + origen en incidencias_internas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID

    # ── Cuentas conectadas (OAuth) ──────────────────────────────────────────
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_cuentas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            plataforma          VARCHAR(20)  NOT NULL,  -- instagram|facebook|tiktok|youtube|x
            nombre_cuenta       VARCHAR(160)          DEFAULT NULL,
            id_externo          VARCHAR(120)          DEFAULT NULL,  -- page_id/account_id/channel_id
            access_token        TEXT                  DEFAULT NULL,  -- SIEMPRE cifrado (utils.cripto)
            refresh_token       TEXT                  DEFAULT NULL,  -- SIEMPRE cifrado
            token_expira        DATETIME              DEFAULT NULL,
            estado              VARCHAR(16)  NOT NULL DEFAULT 'desconectada',
                                 -- desconectada|conectada|error|expirada
            ultimo_error        VARCHAR(255)          DEFAULT NULL,
            conectado_por       VARCHAR(120)          DEFAULT NULL,
            fecha_conexion      DATETIME              DEFAULT NULL,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rsc_cuenta (id_empresa, plataforma, id_externo),
            INDEX idx_rsc_empresa (id_empresa, plataforma)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Bandeja omnicanal: conversaciones (hilo) ───────────────────────────
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_conversaciones (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_cuenta           BIGINT       NOT NULL,
            plataforma          VARCHAR(20)  NOT NULL,
            tipo                VARCHAR(12)  NOT NULL DEFAULT 'dm',  -- dm|comentario|mencion
            externo_id          VARCHAR(160)          DEFAULT NULL,  -- id de hilo/comentario en la plataforma
            remitente_nombre    VARCHAR(160)          DEFAULT NULL,
            remitente_handle    VARCHAR(160)          DEFAULT NULL,
            remitente_externo_id VARCHAR(160)         DEFAULT NULL,
            id_cliente          INT                   DEFAULT NULL,  -- vínculo opcional a clientes.id
            estado              VARCHAR(20)  NOT NULL DEFAULT 'pendiente_respuesta',
                                 -- pendiente_respuesta|respondida|resuelta|archivada
            prioridad           VARCHAR(10)  NOT NULL DEFAULT 'media',  -- baja|media|alta|urgente
            fecha_ultimo_mensaje DATETIME             DEFAULT NULL,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rsconv_externo (id_empresa, id_cuenta, externo_id),
            INDEX idx_rsconv_empresa_estado (id_empresa, estado),
            INDEX idx_rsconv_cliente (id_cliente),
            CONSTRAINT fk_rsconv_cuenta FOREIGN KEY (id_cuenta)
                REFERENCES redes_sociales_cuentas(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Bandeja omnicanal: mensajes dentro de un hilo ──────────────────────
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_mensajes (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_conversacion     BIGINT       NOT NULL,
            direccion           VARCHAR(10)  NOT NULL DEFAULT 'entrante',  -- entrante|saliente
            autor               VARCHAR(160)          DEFAULT NULL,
            cuerpo              TEXT                  DEFAULT NULL,
            id_documento_adjunto VARCHAR(40)          DEFAULT NULL,  -- documentos_registro.id_documento
            externo_id          VARCHAR(160)          DEFAULT NULL,
            generado_por_ia     TINYINT(1)   NOT NULL DEFAULT 0,
            leido               TINYINT(1)   NOT NULL DEFAULT 0,
            fecha               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rsmsg_conversacion (id_conversacion, fecha),
            CONSTRAINT fk_rsmsg_conversacion FOREIGN KEY (id_conversacion)
                REFERENCES redes_sociales_conversaciones(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Calendario de contenidos / publicaciones ───────────────────────────
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_publicaciones (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_cuenta           BIGINT       NOT NULL,
            plataforma          VARCHAR(20)  NOT NULL,
            titulo              VARCHAR(160)          DEFAULT NULL,
            contenido           TEXT                  DEFAULT NULL,
            tipo_contenido      VARCHAR(12)  NOT NULL DEFAULT 'texto',  -- imagen|video|carrusel|texto
            ruta_adjunto        VARCHAR(255)          DEFAULT NULL,
            estado              VARCHAR(12)  NOT NULL DEFAULT 'borrador',
                                 -- borrador|programada|publicada|fallida
            fecha_programada    DATETIME              DEFAULT NULL,
            fecha_publicada     DATETIME              DEFAULT NULL,
            externo_id          VARCHAR(160)          DEFAULT NULL,  -- id del post ya publicado
            error_publicacion   VARCHAR(255)          DEFAULT NULL,
            creado_por          VARCHAR(120)          DEFAULT NULL,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rspub_empresa_estado (id_empresa, estado, fecha_programada),
            CONSTRAINT fk_rspub_cuenta FOREIGN KEY (id_cuenta)
                REFERENCES redes_sociales_cuentas(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Métricas por publicación (sincronizadas desde la plataforma) ──────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS redes_sociales_metricas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_publicacion      BIGINT       NOT NULL,
            impresiones         INT          NOT NULL DEFAULT 0,
            alcance             INT          NOT NULL DEFAULT 0,
            interacciones       INT          NOT NULL DEFAULT 0,
            likes               INT          NOT NULL DEFAULT 0,
            comentarios         INT          NOT NULL DEFAULT 0,
            compartidos         INT          NOT NULL DEFAULT 0,
            clics               INT          NOT NULL DEFAULT 0,
            fecha_captura       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rsmet_publicacion (id_publicacion, fecha_captura),
            CONSTRAINT fk_rsmet_publicacion FOREIGN KEY (id_publicacion)
                REFERENCES redes_sociales_publicaciones(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Reglas de monitorización de reputación ─────────────────────────────
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_reglas_reputacion (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            nombre              VARCHAR(120) NOT NULL,
            palabras_clave      TEXT         NOT NULL,  -- CSV de términos/expresiones (minúsculas)
            prioridad_ticket    VARCHAR(10)  NOT NULL DEFAULT 'alta',
            activa              TINYINT(1)   NOT NULL DEFAULT 1,
            creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rsregla_empresa (id_empresa, activa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Alertas de reputación detectadas + enlace al ticket de Incidencias ─
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS redes_sociales_alertas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_mensaje          BIGINT                DEFAULT NULL,
            id_conversacion     BIGINT                DEFAULT NULL,
            id_regla            BIGINT                DEFAULT NULL,
            plataforma          VARCHAR(20)  NOT NULL,
            texto_detectado     TEXT                  DEFAULT NULL,
            id_ticket_incidencia BIGINT               DEFAULT NULL,
            estado              VARCHAR(12)  NOT NULL DEFAULT 'escalada',  -- escalada|descartada
            fecha_creacion      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_rsalerta_empresa (id_empresa, fecha_creacion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # ── Extensión de Incidencias (migr. 0323): escalado automático sin
    # solicitante humano ────────────────────────────────────────────────────
    cur.execute("ALTER TABLE incidencias_internas ADD COLUMN IF NOT EXISTS origen "
               "VARCHAR(24) NOT NULL DEFAULT 'manual'")
    cur.execute("ALTER TABLE incidencias_internas MODIFY COLUMN id_usuario_solicitante INT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE incidencias_internas MODIFY COLUMN id_usuario_solicitante INT NOT NULL")
    cur.execute("ALTER TABLE incidencias_internas DROP COLUMN IF EXISTS origen")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_alertas")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_reglas_reputacion")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_metricas")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_publicaciones")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_mensajes")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_conversaciones")
    cur.execute("DROP TABLE IF EXISTS redes_sociales_cuentas")
