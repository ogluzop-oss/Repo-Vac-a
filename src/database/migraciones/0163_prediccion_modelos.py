"""
Migración 0163 — Registro/versionado persistente de modelos predictivos (IA · Fase 6). ADITIVA, reversible.

NO es un motor de IA paralelo: es la CAPA DE PERSISTENCIA del ciclo de vida de los modelos que el motor de
forecasting existente (`services/prediccion/forecasting.py`, Fase 5) ya calcula en memoria. Guarda los
metadatos y métricas REALES (MAE/RMSE/WAPE), el estado del ciclo de vida y un hash de integridad. Aislado
por tenant (`id_empresa`). No almacena secretos ni modelos serializados corruptos.
"""

VERSION = "0163"
DESCRIPCION = "IA: tabla prediccion_modelos (registro/versionado/ciclo de vida de modelos predictivos)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prediccion_modelos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            model_id VARCHAR(40) NOT NULL,
            id_empresa VARCHAR(36) DEFAULT NULL,
            entidad VARCHAR(60) NOT NULL,
            entidad_id VARCHAR(64) DEFAULT NULL,
            algoritmo VARCHAR(40) NOT NULL,
            tipo_modelo VARCHAR(20) NOT NULL,          -- heuristica | estadistica | ml
            version INT NOT NULL DEFAULT 1,
            n_observaciones INT DEFAULT 0,
            mae DECIMAL(18,4) DEFAULT NULL,
            rmse DECIMAL(18,4) DEFAULT NULL,
            wape DECIMAL(18,6) DEFAULT NULL,
            calidad_datos VARCHAR(40) DEFAULT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'VALIDATED',  -- TRAINING|VALIDATED|ACTIVE|DEPRECATED|FAILED
            hash_integridad VARCHAR(64) DEFAULT NULL,
            fecha_entrenamiento DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_activacion DATETIME DEFAULT NULL,
            fecha_desactivacion DATETIME DEFAULT NULL,
            creado DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_model (model_id),
            INDEX idx_pm_emp_ent (id_empresa, entidad, entidad_id),
            INDEX idx_pm_estado (id_empresa, entidad, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS prediccion_modelos")
