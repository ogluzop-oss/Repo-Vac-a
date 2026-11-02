"""
Migración 0278 — Memoria/Cuentas Anuales: registro de Operaciones con Partes Vinculadas.

La Memoria (nota legal obligatoria del PGC) exige informar de las operaciones con partes
vinculadas (administradores, socios significativos, sus familiares cercanos, u otras empresas
del grupo) del ejercicio. Hoy NADA en el sistema registra esto (confirmado: no existe ninguna
tabla ni concepto "parte vinculada"/"related party" en todo el repositorio) — es un hueco real,
no una duplicidad de otro motor.

Esta migración da de alta `contab_partes_vinculadas`: un registro MANUAL y DELIBERADO (no se
infiere de ningún otro dato: quién es "parte vinculada" es una decisión legal/societaria que solo
un administrador puede declarar) — un libro de divulgación, no un motor contable paralelo. Lo
consume `services.contabilidad.partes_vinculadas` y, a través de él, `memoria_anual.generar_memoria`.
Multiempresa (`id_empresa` CHAR(36), igual que `empresas.id_empresa`), auditado vía
`log_auditoria` en la capa de servicio (no aquí).

ADITIVA, idempotente, reversible.
"""

VERSION = "0278"
DESCRIPCION = "Alta de contab_partes_vinculadas (registro de divulgación para la Memoria)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contab_partes_vinculadas (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      VARCHAR(36)   NOT NULL,
            anio            INT           NOT NULL,
            nombre          VARCHAR(255)  NOT NULL,
            relacion        VARCHAR(30)   NOT NULL,
            descripcion     TEXT          DEFAULT NULL,
            importe         DECIMAL(14,2) NOT NULL DEFAULT 0,
            fecha           DATE          DEFAULT NULL,
            creado_por      VARCHAR(120)  DEFAULT NULL,
            fecha_registro  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pv_empresa_anio (id_empresa, anio)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS contab_partes_vinculadas")
