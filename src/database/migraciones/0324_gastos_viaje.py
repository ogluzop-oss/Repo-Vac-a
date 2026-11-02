"""
Migración 0324 — Gestión de Gastos de Viaje / notas de gastos (petición explícita, flujo completo:
escaneo de ticket por OCR en móvil → nota de gastos → aprobación → reembolso en nómina). ADITIVA,
idempotente, reversible.

Auditoría previa: no existía ningún concepto de gasto de empleado/nota de gastos en el repo (el
único OCR de documentos existente, `services/contabilidad/factura_ocr_ia.py`, lee FACTURAS DE
PROVEEDOR para contabilidad — dominio distinto). El reembolso NO crea un motor de nómina paralelo:
se inyecta como importe adicional en el concepto `dietas` ya existente del motor de nómina
(`services.rrhh.nominas_pro.preparar_datos_nomina`, mismo patrón que la cuota de anticipos).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0324"
DESCRIPCION = "Gastos de viaje / notas de gastos (gastos_viaje)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS gastos_viaje (
            id                BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa        CHAR(36)     NOT NULL DEFAULT '{emp}',
            codigo            VARCHAR(20)  NOT NULL,
            id_empleado       BIGINT       NOT NULL,
            id_proyecto       INT                   DEFAULT NULL,
            fecha_gasto       DATE         NOT NULL,
            categoria         VARCHAR(20)  NOT NULL DEFAULT 'otros',
                               -- transporte|alojamiento|dietas|otros
            concepto          VARCHAR(255)          DEFAULT NULL,
            importe           DECIMAL(10,2) NOT NULL DEFAULT 0,
            moneda            VARCHAR(3)   NOT NULL DEFAULT 'EUR',
            ruta_ticket       VARCHAR(255)          DEFAULT NULL,
            ocr_origen        TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 si los datos vinieron de OCR IA
            estado            VARCHAR(12)  NOT NULL DEFAULT 'pendiente',
                               -- pendiente|aprobado|rechazado|reembolsado
            aprobado_por      VARCHAR(120)          DEFAULT NULL,
            fecha_aprobacion  DATETIME              DEFAULT NULL,
            motivo_rechazo    VARCHAR(255)          DEFAULT NULL,
            id_nomina_reembolso BIGINT              DEFAULT NULL,
            fecha_creacion    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_gv_codigo (id_empresa, codigo),
            INDEX idx_gv_empleado (id_empresa, id_empleado, estado),
            CONSTRAINT fk_gv_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS gastos_viaje")
