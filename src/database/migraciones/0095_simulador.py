"""
Migracion 0095 — Simulador Empresarial / What-If (Paquete Enterprise 9). ADITIVA, idempotente,
reversible. El simulador NUNCA toca datos reales: trabaja sobre el Gemelo Digital como estado base.
Estas tablas SOLO persisten los ESCENARIOS virtuales (hipotesis, variables modificadas y resultados
calculados), jamas entidades operativas (nunca pedidos/facturas/stock/contratos reales).

  - sim_escenarios : definicion del escenario (empresa, usuario, descripcion, estado, foto base).
  - sim_variables  : variables alteradas virtualmente dentro del escenario (precio/salario/stock...).
  - sim_resultados : resultados calculados por metrica (base vs simulado, delta, confianza).

Multiempresa/multitienda/SaaS. Todo el contenido es VIRTUAL y reversible (borrar el escenario no
afecta a nada real).
"""

VERSION = "0095"
DESCRIPCION = "Simulador Empresarial: sim_escenarios, sim_variables, sim_resultados"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("sim_escenarios", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'BORRADOR',
        base_json MEDIUMTEXT DEFAULT NULL,
        confianza VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_sim_esc (id_empresa, estado, creado)"""),

    ("sim_variables", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_escenario BIGINT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        dominio VARCHAR(30) NOT NULL,
        variable VARCHAR(40) NOT NULL,
        operacion VARCHAR(16) NOT NULL DEFAULT 'delta_pct',
        valor DECIMAL(16,4) NOT NULL DEFAULT 0,
        params_json MEDIUMTEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_sim_var (id_escenario)"""),

    ("sim_resultados", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_escenario BIGINT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        dominio VARCHAR(30) DEFAULT NULL,
        metrica VARCHAR(40) NOT NULL,
        valor_base DECIMAL(18,4) DEFAULT NULL,
        valor_sim DECIMAL(18,4) DEFAULT NULL,
        delta DECIMAL(18,4) DEFAULT NULL,
        delta_pct DECIMAL(10,4) DEFAULT NULL,
        confianza VARCHAR(12) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_sim_res (id_escenario, metrica)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
